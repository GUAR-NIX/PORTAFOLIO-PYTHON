"""Genera los 4 notebooks del proyecto (luego se ejecutan con nbconvert).

Los textos no llevan cifras fijas: las celdas de código las leen de reports/ o las calculan, así
los notebooks no se desfasan de los resultados.

    python scripts/crear_notebooks.py
    jupyter nbconvert --to notebook --execute --inplace notebooks/*.ipynb
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

DIR = Path(__file__).resolve().parents[1] / "notebooks"

INICIO = """import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from IPython.display import Image, display

RAIZ = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(RAIZ / "src"))
pd.set_option("display.max_columns", 30)
pd.set_option("display.width", 160)
pd.set_option("display.float_format", lambda v: f"{v:,.3f}")

from nyc311.config import ARCHIVO_LIMPIO, ARCHIVO_RESULTADOS, DIR_FIGURAS, DIR_TABLAS

res = json.loads(ARCHIVO_RESULTADOS.read_text(encoding="utf-8"))
tabla = lambda nombre: pd.read_csv(DIR_TABLAS / f"{nombre}.csv")
figura = lambda nombre: display(Image(filename=str(DIR_FIGURAS / nombre)))"""


def md(texto: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(texto.strip())


def code(texto: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(texto.strip())


NOTEBOOKS = {
    "01_ingesta_y_calidad.ipynb": [
        md("""
# 1. Ingesta y calidad de datos del 311

**Pregunta del proyecto:** ¿cuánto tarda Nueva York en resolver las solicitudes ciudadanas del 311 y qué lo explica?

Este notebook revisa la descarga (API Socrata de NYC Open Data, dataset `erm2-nwe9`), las reglas de limpieza y,
sobre todo, cómo se definen el **evento** (cierre) y la **censura** (solicitud abierta en la fecha de corte).
"""),
        code(INICIO),
        md("""
## 1.1 Qué se descargó

La descarga (`python descargar_datos.py`) pide solo 10 columnas, un mes por tarea, en páginas de 50.000 filas
ordenadas por `unique_key`, con reintentos y caché por página (reanudable). La **fecha de corte** queda fija en el
manifiesto: es la `created_date` más reciente publicada al empezar la descarga.
"""),
        code("""
manifiesto = json.loads((RAIZ / "data" / "raw" / "manifiesto_descarga.json").read_text(encoding="utf-8"))
{k: v for k, v in manifiesto.items() if k != "columnas"}
"""),
        code("""
cal = res["calidad"]
pd.Series({k: v for k, v in cal.items() if not isinstance(v, dict)}, name="valor").to_frame()
"""),
        md("""
## 1.2 Reglas de limpieza

| Problema | Decisión | Por qué |
| --- | --- | --- |
| `closed_date` < `created_date` | Se descarta | La duración sería negativa: no hay forma de saber la verdadera |
| `status = Closed` sin `closed_date` | Se descarta | Sabemos que cerró, pero no cuándo |
| Fecha de cierre con estado abierto | Censura al corte | El estado es lo más reciente: probablemente se reabrió |
| Cierre posterior al corte | Censura al corte | En la fecha de corte todavía estaba abierta |
| Cierre en el mismo segundo | Se conserva (duración 0) | Son cierres administrativos reales (p. ej. derivaciones) |
| Borough `Unspecified`, ZIP fuera de NYC | Se conservan con «SIN DATO» / nulo | Solo se excluyen de los análisis territoriales |
"""),
        code("""
pd.Series(cal["cierre_antes_de_apertura_por_agencia"], name="cierres antes de la apertura").to_frame()
"""),
        md("""
## 1.3 La tabla analítica: duración y censura

Cada fila tiene `duracion_dias` y `evento` (1 = cerrada, 0 = censurada). Para una censurada la duración es
`fecha_corte − creada`: solo sabemos que tardó **al menos** eso.
"""),
        code("""
df = pd.read_parquet(ARCHIVO_LIMPIO, columns=["unique_key", "creada", "cerrada", "agencia", "tipo_queja", "borough",
                                              "canal", "estado", "duracion_dias", "evento"])
print(f"{len(df):,} solicitudes · {df['evento'].mean():.2%} cerradas al corte")
df.sample(6, random_state=1)
"""),
        code("""
from nyc311.limpieza import validar_tabla
validar_tabla(df)  # lista vacía = sin duplicados, sin duraciones negativas, eventos coherentes
"""),
        code("""
por_agencia = (df.groupby("agencia", observed=True)["evento"]
                 .agg(solicitudes="size", pct_censuradas=lambda e: 100 * (1 - e.mean()))
                 .sort_values("solicitudes", ascending=False))
por_agencia.head(12)
"""),
        md("""
La censura global es baja, pero **no se reparte igual**: en las agencias lentas (Parques, TLC, EDC) una parte
grande sigue abierta. Promediar solo las cerradas de esas agencias descarta justo los casos más lentos: ese es el
sesgo que el notebook 2 cuantifica.

La censura aquí es **administrativa**: solo la produce el corte. Ninguna solicitud «desaparece» antes, así que la
censura es no informativa (supuesto clave de Kaplan-Meier y Cox).
"""),
        code('figura("01_calidad_y_censura.png")'),
    ],
    "02_kaplan_meier.ipynb": [
        md("""
# 2. Kaplan-Meier: tiempos de resolución con casos censurados

1. Por qué el promedio de las cerradas está sesgado (experimento con un corte ficticio).
2. Curvas de Kaplan-Meier por agencia, tipo de queja, borough y canal, con medianas e IC 95 %.
3. Pruebas log-rank.
"""),
        code(INICIO),
        code("""
from nyc311.supervivencia import kaplan_meier, mediana_con_ic, logrank, tiempo_medio_restringido, evaluar
df = pd.read_parquet(ARCHIVO_LIMPIO, columns=["creada", "cerrada", "agencia", "tipo_queja", "borough", "canal",
                                              "duracion_dias", "evento"])
g = res["global"]
print(f"Mediana KM: {g['mediana_km_horas']:.2f} h (IC 95 %: {g['mediana_ic_inf_horas']:.2f}–{g['mediana_ic_sup_horas']:.2f})")
print(f"Promedio ingenuo de las cerradas: {g['promedio_ingenuo_cerradas_dias']:.2f} días")
print(f"% cerradas en 1 / 7 / 30 días: {g['pct_cerradas_1d']:.1f} / {g['pct_cerradas_7d']:.1f} / {g['pct_cerradas_30d']:.1f}")
"""),
        md("""
## 2.1 La implementación propia coincide con lifelines

Con 7,5 M de filas y duraciones al segundo, `nyc311.supervivencia` agrega por tiempo único con numpy.
Las pruebas (`tests/test_supervivencia.py`) la comparan con lifelines y con el ejemplo de Freireich (leucemia).
Aquí, una comprobación rápida en una muestra:
"""),
        code("""
from lifelines import KaplanMeierFitter
m = df.sample(50_000, random_state=311)
propia = kaplan_meier(m["duracion_dias"], m["evento"])
kmf = KaplanMeierFitter().fit(m["duracion_dias"], m["evento"])
print("mediana propia:", mediana_con_ic(propia)[0], "· lifelines:", kmf.median_survival_time_)
dif = np.abs(evaluar(propia, kmf.timeline) - kmf.survival_function_.iloc[:, 0].to_numpy()).max()
print(f"diferencia máxima entre curvas: {dif:.2e}")
"""),
        md("""
## 2.2 ¿Por qué no usar el promedio de las cerradas?

Experimento con datos reales: tomamos las solicitudes creadas en oct–dic 2024 y **fingimos** que la descarga se
hizo el 15-ene-2025. Comparamos lo que habríamos estimado entonces con la «verdad» que conocemos hoy (casi 2 años
de seguimiento).
"""),
        code("""
exp = tabla("sesgo_corte_retrospectivo")
cols = ["grupo", "n", "pct_abiertas_corte_ficticio", "mediana_ingenua_ficticio", "mediana_km_ficticio",
        "mediana_verdad", "promedio_ingenuo_ficticio", "promedio_verdad_cerradas"]
exp[cols]
"""),
        code("""
for _, r in exp.loc[exp["grupo"].isin(["DOB", "DPR", "TLC"])].iterrows():
    print(f"{r['grupo']}: mediana ingenua {r['mediana_ingenua_ficticio']:.1f} d · KM {r['mediana_km_ficticio']:.1f} d · "
          f"verdad {r['mediana_verdad']:.1f} d · promedio ingenuo {r['promedio_ingenuo_ficticio']:.1f} d "
          f"vs promedio real {r['promedio_verdad_cerradas']:.1f} d")
"""),
        md("""
**Lectura.** El promedio (o la mediana) de las cerradas solo ve a las que alcanzaron a cerrarse antes del corte:
por construcción descarta las lentas, y el sesgo es mayor donde más censura hay. Tratar las abiertas como si
cerraran en el corte tampoco sirve: las acorta. Kaplan-Meier usa la información parcial de las abiertas («llevaba
al menos X días») y recupera la mediana real. Cuando la mediana KM queda en «inf» (EDC) es honesto: con el
seguimiento disponible todavía no cerró la mitad.
"""),
        code('figura("02_sesgo_promedio_vs_kaplan_meier.png")'),
        md("## 2.3 Kaplan-Meier por agencia, borough, canal y tipo de queja"),
        code("""
tabla("km_agencias")[["agencia", "n", "pct_censuradas", "mediana_km_dias", "mediana_ic_inf", "mediana_ic_sup",
                       "pct_cerradas_1d", "pct_cerradas_7d", "pct_cerradas_30d", "promedio_ingenuo_cerradas_dias"]]
"""),
        code('figura("03_kaplan_meier_agencias.png")'),
        code("""
tabla("km_boroughs")[["borough", "n", "mediana_km_dias", "mediana_ic_inf", "mediana_ic_sup", "pct_cerradas_7d"]]
"""),
        code("""
tabla("km_canales")[["canal", "n", "mediana_km_dias", "mediana_ic_inf", "mediana_ic_sup", "pct_cerradas_7d"]]
"""),
        code('figura("04_kaplan_meier_borough_y_canal.png")'),
        code("""
from nyc311.etiquetas import tipo_es
t = tabla("km_tipos_queja").head(20)
t.insert(1, "tipo_es", t["tipo_queja"].map(tipo_es))
t[["tipo_queja", "tipo_es", "n", "pct_censuradas", "mediana_km_dias", "mediana_ic_inf", "mediana_ic_sup",
   "promedio_ingenuo_cerradas_dias"]]
"""),
        code('figura("05_medianas_por_tipo_de_queja.png")'),
        md("""
## 2.4 Log-rank

H0: todas las curvas del grupo son iguales. Con millones de filas cualquier diferencia mínima es «significativa»;
la prueba confirma que las diferencias no son azar, pero **el tamaño** se lee en las medianas y en los HR.
"""),
        code("""
lr = tabla("logrank")
lr.assign(p_valor=lr["p_valor"].map(lambda p: f"{p:.1e}"))
"""),
    ],
    "03_cox.ipynb": [
        md("""
# 3. Modelo de Cox de riesgos proporcionales

El riesgo (*hazard*) es la tasa instantánea de **cierre**. HR > 1: la solicitud se cierra más rápido que la
referencia; HR < 1, más lento. Dos modelos (lifelines, muestra aleatoria fija de 200.000 solicitudes):

* **A (descriptivo):** agencia + borough + canal + fin de semana + franja nocturna.
* **B (equidad):** estratificado por tipo de queja (cada tipo con su propio riesgo base) + borough + canal + horario.
"""),
        code(INICIO),
        code("""
cox = res["cox"]
print(f"Muestra: {cox['n_muestra']:,} solicitudes ({cox['eventos_muestra']:,} cierres)")
print(f"Concordancia A: {cox['modelo_A']['concordancia']:.3f} · B: {cox['modelo_B']['concordancia']:.3f}")
tabla("cox_modelo_A")
"""),
        code("tabla('cox_modelo_B')"),
        code('figura("06_cox_hazard_ratios.png")'),
        md("""
## 3.1 Cómo se ajusta (demostración en una muestra pequeña)

El pipeline usa 200.000 filas; aquí 30.000 para que el notebook corra rápido. Los HR deben parecerse.
"""),
        code("""
from nyc311 import cox as mcox
df = pd.read_parquet(ARCHIVO_LIMPIO)
muestra = mcox.muestra_modelo(df, n=30_000)
del df
cph = mcox.ajustar(mcox.matriz_modelo(muestra, "B"), "B")
cph.summary[["exp(coef)", "exp(coef) lower 95%", "exp(coef) upper 95%", "p"]]
"""),
        md("""
## 3.2 ¿Se cumple el supuesto de riesgos proporcionales?

Cox supone que el HR es constante en el tiempo. Tres comprobaciones:

1. **Prueba de Grambsch-Therneau** (residuos de Schoenfeld escalados, tiempo en rangos) en 40.000 filas.
2. **Curvas log(−log S)** por borough: con PH serían paralelas.
3. **HR por ventana de tiempo**: reajustar el modelo B solo con las solicitudes aún abiertas al inicio de cada
   ventana (0–1 día, 1–7, 7–30, > 30). Si el HR cambia mucho, el HR global es un promedio que esconde dinámica.
"""),
        code("tabla('supuesto_ph_modelo_A').head(10)"),
        code("tabla('supuesto_ph_modelo_B')"),
        code("""
v = tabla("cox_hr_por_ventana")
v.loc[v["covariable"].str.startswith("borough"), ["ventana", "covariable", "hr", "ic_inf", "ic_sup", "n_en_riesgo"]]
"""),
        code('figura("07_supuesto_riesgos_proporcionales.png")'),
        md("""
**Conclusión sobre PH.** El supuesto **no se cumple** para agencia (por eso el modelo B estratifica por tipo de
queja en lugar de estimar un HR por agencia) ni del todo para borough: el Bronx cierra mucho más lento durante el
primer día y, entre las que siguen abiertas tras una semana, cierra más rápido que Manhattan. El HR global del
modelo B debe leerse como un **promedio ponderado en el tiempo**, dominado por las primeras horas, donde ocurre
la mayoría de los cierres. Por eso el análisis de equidad se complementa con una medida sin supuesto PH (O/E a 7 días).
"""),
        md("""
## 3.3 Lectura en lenguaje de negocio
"""),
        code("""
for fila in res["cox"]["modelo_B"]["hr"]:
    print(f"{fila['covariable']:<26} HR {fila['hr']:.2f} → {fila['lectura']}")
"""),
    ],
    "04_hallazgos.ipynb": [
        md("""
# 4. Hallazgos: equidad territorial y evolución en el tiempo

* ¿Se resuelven más lento las quejas en ciertos boroughs o códigos postales **controlando por tipo de queja**?
* ¿Mejora o empeora el tiempo de resolución mes a mes?
"""),
        code(INICIO),
        md("""
## 4.1 Equidad territorial (estandarización indirecta)

Resultado: «cerrada en ≤ 7 días», observado para todas las solicitudes (la cohorte termina 26 días antes del corte
y la censura es solo administrativa). Esperado = tasa de toda la ciudad en su celda tipo de queja × descriptor.
O/E < 1: se cierran menos de lo que su mezcla de quejas predice.
"""),
        code("""
eq = tabla("equidad_boroughs")
eq[["borough", "n", "pct_cerradas_7d", "pct_esperado_7d", "o_entre_e", "ic_inf", "ic_sup"]]
"""),
        md("""
El mismo O/E a horizontes cortos muestra **dónde** está la brecha: el Bronx cierra menos de lo esperado en la primera
hora y alcanza lo esperado hacia las 24 horas. Es lo mismo que mostraban los HR por ventana del modelo de Cox, ahora
sin el supuesto PH.
"""),
        code("""
tabla("equidad_boroughs_horizontes").pivot(index="borough", columns="horizonte", values="o_entre_e")[
    ["1 h", "3 h", "8 h", "1 día", "7 días"]]
"""),
        code("""
z = tabla("equidad_zip")
e = res["equidad"]
print(f"ZIP analizados (≥ 1.000 solicitudes): {e['n_zip_analizados']} · significativos con FDR 5 %: {e['n_zip_significativos']}")
print(f"Más lentos de lo esperado: {e['n_zip_lentos']} · más rápidos: {e['n_zip_rapidos']}")
print(f"O/E entre el percentil 5 y el 95: {e['oe_zip_p05']:.3f} – {e['oe_zip_p95']:.3f}")
z.head(8)[["zip", "borough", "n", "pct_cerradas_7d", "pct_esperado_7d", "o_entre_e", "ic_inf", "ic_sup"]]
"""),
        code('figura("08_equidad_territorial.png")'),
        md("""
**Limitaciones (correlación no es causalidad).** Un O/E bajo puede deberse a menos recursos, pero también a
casos más difíciles dentro de la misma celda (edificios más viejos, problemas recurrentes), a duplicados que se
cierran juntos, a diferencias en cómo cada agencia registra el «cierre» o a quién reporta (el 311 mide demanda
reportada, no necesidad real). No se usan datos socioeconómicos, así que no se puede atribuir la diferencia a
ingreso o composición étnica.
"""),
        md("## 4.2 Evolución mensual"),
        code("""
m = tabla("evolucion_mensual")
m[["mes", "n", "mediana_km_dias", "pct_cerradas_7d", "pct_esperado_7d", "o_entre_e"]].assign(
    mediana_horas=lambda d: 24 * d["mediana_km_dias"])
"""),
        code("""
ev = res["evolucion"]
pd.DataFrame(ev["periodos"]).T
"""),
        code("tabla('evolucion_agencias_anual')"),
        code('figura("09_evolucion_mensual.png")'),
        md("""
**Lectura.** La mediana sube cada invierno porque cambia la **mezcla**: las quejas de calefacción y agua caliente
(HPD), que tardan días, se disparan con el frío. Por eso la tendencia se juzga con el O/E ajustado por tipo ×
descriptor, que compara cada mes con lo que su mezcla de quejas predice.
"""),
    ],
}


def main() -> None:
    DIR.mkdir(exist_ok=True)
    for nombre, celdas in NOTEBOOKS.items():
        nb = nbf.v4.new_notebook()
        nb["cells"] = celdas
        nb["metadata"]["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
        nbf.write(nb, DIR / nombre)
        print(f"creado notebooks/{nombre}")


if __name__ == "__main__":
    main()
