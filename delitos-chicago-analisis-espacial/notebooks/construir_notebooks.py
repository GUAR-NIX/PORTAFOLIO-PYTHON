"""Construye y ejecuta los 4 notebooks del proyecto (python notebooks/construir_notebooks.py).

Los notebooks se escriben desde aquí para que su contenido quede versionado como código y se
ejecutan con nbclient de punta a punta; si una celda falla, el script falla.
"""
from __future__ import annotations

import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient

CARPETA = Path(__file__).resolve().parent

INICIO = """\
import json
import warnings
import matplotlib.pyplot as plt
import pandas as pd
from IPython.display import Image, display
from delitos_chicago.config import FIGURAS, PROCESADOS, REPORTES
import delitos_chicago.pipeline  # los módulos fijan el backend Agg al importarse; después se activa el inline
%matplotlib inline
warnings.filterwarnings("ignore", category=UserWarning)
pd.set_option("display.width", 140)
pd.set_option("display.max_columns", 20)"""

CARGA = """\
from delitos_chicago.pipeline import cargar_datos
from delitos_chicago.pronostico import ultimo_mes_completo
df, renombres, conteos = cargar_datos(PROCESADOS / "delitos_parquet")
mes_completo = ultimo_mes_completo(df["fecha"].max())
anio_completo = mes_completo.year if mes_completo.month == 12 else mes_completo.year - 1
completos = df[df["anio"] <= anio_completo]
print(f"{len(df):,} registros · último dato {df['fecha'].max():%Y-%m-%d} · último mes completo {mes_completo:%Y-%m} · años completos 2001–{anio_completo}")"""

NOTEBOOKS = {
    "01_ingesta_y_calidad.ipynb": [
        ("md", """# 01 · Ingesta, calidad y armonización de categorías

El portal de Chicago publica *Crimes – 2001 to Present* (`ijzp-q8t2`). `descargar_datos.py` baja un CSV por año y `ingesta.py` los convierte con DuckDB en Parquet particionado por año. Este notebook revisa:

1. La **trazabilidad** de los archivos fuente (URL, fecha, filas y SHA-256).
2. La **auditoría de calidad** de la ingesta (duplicados, fechas, coordenadas).
3. La **armonización de categorías**: un tipo de delito cambió de nombre y, si no se corrige, aparece como un salto falso.

La ingesta completa (2,4 GB de CSV) no se repite aquí: se leen sus resultados en `reports/calidad.json`."""),
        ("code", INICIO),
        ("md", "## 1. Manifiesto de la fuente"),
        ("code", """\
manifiesto = json.loads((PROCESADOS.parent / "manifiesto_fuente.json").read_text(encoding="utf-8"))
archivos = pd.DataFrame(manifiesto["archivos"])
archivos["sha256"] = archivos["sha256"].str[:16] + "…"
print(f"Consulta a la API: {manifiesto['consultado_utc']} · conteo oficial {manifiesto['conteo_api']:,}")
print(f"Filas en los CSV descargados: {archivos['filas'].sum():,.0f}")
archivos[["archivo", "fecha_descarga_utc", "filas", "bytes", "sha256"]]"""),
        ("md", "Las filas de los 26 CSV suman exactamente el conteo que devolvió la API el día de la descarga."),
        ("md", "## 2. Auditoría de calidad de la ingesta"),
        ("code", """\
calidad = json.loads((REPORTES / "calidad.json").read_text(encoding="utf-8"))
pd.Series({k: v for k, v in calidad.items() if k != "distribucion_anios"}, name="valor").to_frame()"""),
        ("code", """\
import duckdb
patron = (PROCESADOS / "delitos_parquet" / "**" / "*.parquet").as_posix()
por_anio = duckdb.sql(f\"\"\"
    SELECT CAST(anio AS INTEGER) AS anio, count(*) AS delitos,
           avg(CASE WHEN latitud IS NULL THEN 1 ELSE 0 END) * 100 AS pct_sin_coordenadas
    FROM read_parquet('{patron}', hive_partitioning=true) GROUP BY 1 ORDER BY 1\"\"\").df()
fig, ax = plt.subplots(figsize=(11, 3.5))
ax.bar(por_anio["anio"], por_anio["pct_sin_coordenadas"], color="#757575")
ax.set_ylabel("% sin coordenadas")
ax.set_title("Registros sin coordenadas por año (se excluyen solo del análisis espacial)")
plt.show()"""),
        ("md", """Los registros sin coordenadas se concentran en los primeros años. No se borran: entran al análisis temporal y policial y solo se excluyen del espacial.

## 3. Armonización de categorías

`armonizacion.detectar_renombres` busca las categorías que dejan de aparecer y comprueba si sus códigos IUCR (que no dependen de la etiqueta) se siguen registrando después bajo otra categoría."""),
        ("code", """\
from delitos_chicago.armonizacion import comparar_antes_despues, detectar_renombres, mapa_renombres
conteos = duckdb.sql(f\"\"\"
    SELECT CAST(anio AS INTEGER) AS anio, tipo_primario, codigo_iucr, count(*) AS conteo
    FROM read_parquet('{patron}', hive_partitioning=true) GROUP BY ALL\"\"\").df()
tabla = detectar_renombres(conteos, anio_ultimo=int(conteos["anio"].max()) - 1)
tabla"""),
        ("code", """\
serie = (conteos[conteos["tipo_primario"].isin(["CRIM SEXUAL ASSAULT", "CRIMINAL SEXUAL ASSAULT"])]
         .groupby(["anio", "tipo_primario"])["conteo"].sum().unstack(fill_value=0))
serie = serie[serie.index <= 2025]
fig, ax = plt.subplots(figsize=(11, 4))
serie.plot(ax=ax, marker="o")
ax.plot(serie.index, serie.sum(axis=1), color="black", linestyle="--", label="Suma (armonizada)")
ax.set_ylabel("Registros por año")
ax.set_title("La etiqueta cambia entre 2018 y 2020; la suma se mantiene")
ax.legend()
plt.show()"""),
        ("code", "comparar_antes_despues(conteos, mapa_renombres(tabla), 2019, 2024)"),
        ("md", """Sin armonizar, `CRIMINAL SEXUAL ASSAULT` parece subir más del 100 % entre 2019 y 2024; con las dos etiquetas sumadas el cambio es prácticamente nulo. El pipeline aplica el mapa de renombres en la propia consulta de DuckDB, así que todo el análisis (tendencias, cambios por tipo, arrestos, app) usa las categorías armonizadas."""),
    ],
    "02_analisis_temporal.ipynb": [
        ("md", """# 02 · Análisis temporal

Tendencia anual (con el año en curso marcado como parcial), patrón hora × día, descomposición STL del hurto y una **serie temporal interrumpida** para medir el cambio con el COVID-19 contra un contrafactual ajustado solo con datos anteriores a marzo de 2020."""),
        ("code", INICIO),
        ("code", CARGA),
        ("md", "## 1. Tendencia anual"),
        ("code", """\
anual = df.groupby("anio").size()
colores = ["#BDBDBD" if a > anio_completo else "#1565C0" for a in anual.index]
fig, ax = plt.subplots(figsize=(12, 4))
ax.bar(anual.index, anual.values / 1000, color=colores)
ax.set_ylabel("Miles de delitos")
ax.set_title(f"Delitos por año (gris: {anio_completo + 1}, año parcial)")
plt.show()
print(f"Máximo: {anual.idxmax()} ({anual.max():,}) · {anio_completo}: {anual[anio_completo]:,} "
      f"({(anual[anio_completo] / anual.max() - 1) * 100:+.1f} %)")"""),
        ("md", "## 2. Hora × día de la semana"),
        ("code", """\
import seaborn as sns
from delitos_chicago.temporal import mapa_calor_hora_dia, patron_horario
tabla = mapa_calor_hora_dia(completos)
fig, ax = plt.subplots(figsize=(14, 4))
sns.heatmap(tabla, cmap="YlOrRd", ax=ax)
ax.set_xlabel("Hora")
plt.show()
{k: v for k, v in patron_horario(completos).items() if k != "por_hora"}"""),
        ("md", """La franja de cuatro horas con más delitos se busca sin la medianoche, porque las 00:00 concentran registros sin hora exacta. Es la misma cifra que cita el README.

## 3. Descomposición STL del hurto"""),
        ("code", """\
from delitos_chicago.temporal import descomposicion_stl, resumen_estacionalidad
stl = descomposicion_stl(df, "THEFT", hasta=str(mes_completo.date()))
fig, axes = plt.subplots(4, 1, figsize=(12, 8), sharex=True)
for ax, (nombre, datos) in zip(axes, stl.items()):
    ax.plot(datos, linewidth=0.8)
    ax.set_ylabel(nombre)
plt.show()
resumen_estacionalidad(stl)"""),
        ("md", """## 4. COVID-19: serie temporal interrumpida

Modelo OLS del logaritmo de la media diaria mensual con tendencia lineal y 11 indicadores de mes, ajustado entre 2015-01 y 2020-02. El contrafactual se proyecta a 2020-03 – 2021-12 y los intervalos de predicción (95 %) se obtienen simulando coeficientes y ruido residual."""),
        ("code", """\
from delitos_chicago.temporal import efecto_covid_por_serie, serie_interrumpida, serie_mensual
mensual = serie_mensual(df)
mensual = mensual[mensual.index <= mes_completo]
its = serie_interrumpida(mensual)
t = its["tabla"]
ventana = mensual["2015":"2021"]
fig, ax = plt.subplots(figsize=(12, 4.5))
ax.plot(ventana.index, ventana.values, color="black", label="Observado")
ax.plot(t["mes"], t["contrafactual"], "--", label="Contrafactual")
ax.fill_between(t["mes"], t["pi_inf"], t["pi_sup"], alpha=0.2, label="IP 95 %")
ax.axvline(pd.Timestamp("2020-03-01"), color="red", linewidth=1)
ax.legend()
plt.show()
its["resumen"]"""),
        ("code", """\
series = {
    "Todos": mensual,
    "THEFT": serie_mensual(df, df["tipo_primario"] == "THEFT"),
    "BATTERY": serie_mensual(df, df["tipo_primario"] == "BATTERY"),
    "Violencia doméstica": serie_mensual(df, df["domestico"] == True),
}
efecto_covid_por_serie({k: v[v.index <= mes_completo] for k, v in series.items()})"""),
        ("md", """La caída es clara y fuera del intervalo de predicción en todos los meses evaluados. No es un efecto causal aislado: en 2020 coincidieron el confinamiento, las protestas y cambios en el patrullaje.

## 5. Cambio de composición 2019 → 2024 (categorías armonizadas)"""),
        ("code", """\
from delitos_chicago.temporal import cambio_porcentual_por_tipo
cambio = cambio_porcentual_por_tipo(df, 2019, 2024)
cambio[cambio["conteo_2019"] >= 100]"""),
    ],
    "03_analisis_espacial.ipynb": [
        ("md", """# 03 · Análisis espacial: tasas anuales y hotspots Getis-Ord Gi*

1. **Tasa anual** por 100 mil habitantes por área comunitaria (población del censo 2020, CMAP), promediada en 2019–2025.
2. **Getis-Ord Gi\\*** sobre una grilla de 1 km para cada año, con corrección FDR.
3. **Estabilidad** de los hotspots entre años con el índice de Jaccard."""),
        ("code", INICIO),
        ("code", CARGA),
        ("md", "## 1. Tasas anuales por área comunitaria"),
        ("code", """\
from delitos_chicago import espacial
from delitos_chicago.config import ANIOS_ESPACIALES
poblacion = espacial.cargar_poblacion()
areas = espacial.cargar_geojson_areas()
tasas = espacial.tasas_anuales_area(completos, poblacion)
resumen = espacial.resumen_areas(tasas[tasas["anio"].isin(ANIOS_ESPACIALES)], areas.set_index("area_comunitaria")["nombre_area"])
resumen.head(10)"""),
        ("code", """\
mapa = areas.merge(resumen[["area_comunitaria", "tasa_anual_100k"]], on="area_comunitaria")
fig, ax = plt.subplots(figsize=(7, 9))
mapa.plot(column="tasa_anual_100k", cmap="YlOrRd", edgecolor="#424242", linewidth=0.4, legend=True, ax=ax,
          legend_kwds={"label": "Delitos por año por 100 mil hab.", "shrink": 0.6})
ax.axis("off")
plt.show()"""),
        ("code", """\
# Volumen frente a tasa: las áreas con más delitos no son las de más delitos por habitante
resumen.sort_values("puesto_volumen").head(5)[["nombre_area", "delitos_promedio_anual", "poblacion_2020", "tasa_anual_100k", "puesto_tasa"]]"""),
        ("md", "## 2. Getis-Ord Gi* por año"),
        ("code", """\
grilla = espacial.conteos_grilla(completos, ANIOS_ESPACIALES, 1000)
gi = espacial.hotspots_gi(grilla)
estab, resumen_gi = espacial.estabilidad_hotspots(gi)
estab"""),
        ("code", "resumen_gi"),
        ("code", """\
espacial.graficar_hotspots_por_anio(gi, areas, estab, 1000)
display(Image(filename=str(FIGURAS / "12_hotspots_gi_por_anio.png"), width=1000))"""),
        ("code", """\
espacial.graficar_persistencia(gi, areas, 1000)
display(Image(filename=str(FIGURAS / "13_persistencia_hotspots.png"), width=550))
espacial.areas_de_hotspots_persistentes(gi, areas, 1000).head(8)"""),
        ("md", """Los hotspots son estables (Jaccard alto entre años consecutivos) y se concentran en el oeste, el centro y el sur. Gi\\* usa conteos por celda: un hotspot en el Loop refleja mucha actividad y población flotante, no necesariamente más riesgo por residente."""),
    ],
    "04_pronostico.ipynb": [
        ("md", """# 04 · Pronóstico mensual por distrito con backtesting de origen móvil

- Series mensuales completas por distrito hasta el **último mes completo** (el mes en curso se excluye).
- Variables sin fuga: rezagos 1, 2, 3 y 12 y medias móviles del pasado.
- **8 cortes trimestrales**: en cada uno se reentrena con lo anterior y se pronostica un mes adelante durante 3 meses.
- **Intervalos de predicción al 90 %** calibrados con los errores de los 12 meses previos al corte, que el modelo no vio."""),
        ("code", INICIO),
        ("code", CARGA),
        ("code", """\
from delitos_chicago import pronostico
serie = pronostico.preparar_series_mensuales_distrito(df, hasta=mes_completo)
caracteristicas = pronostico.construir_caracteristicas_tiempo(serie)
print(f"{serie['distrito'].nunique()} distritos · {serie['fecha'].min():%Y-%m} a {serie['fecha'].max():%Y-%m}")
caracteristicas.tail(3)"""),
        ("md", "## 1. Comprobación de que no hay fuga: alterar el futuro no cambia las variables del pasado"),
        ("code", """\
corte = mes_completo - pd.DateOffset(months=12)
alterada = serie.copy()
alterada.loc[alterada["fecha"] >= corte, "delitos"] *= 10
a = pronostico.construir_caracteristicas_tiempo(serie).set_index(["distrito", "fecha"])
b = pronostico.construir_caracteristicas_tiempo(alterada).set_index(["distrito", "fecha"])
columnas = [c for c in a.columns if c != "delitos"]
hasta = a.index.get_level_values("fecha") <= corte
print("Variables idénticas hasta el corte:", a.loc[hasta, columnas].equals(b.loc[hasta, columnas]))"""),
        ("md", "## 2. Backtesting de origen móvil"),
        ("code", """\
origenes = pronostico.origenes_trimestrales(mes_completo)
bt = pronostico.backtesting_origen_movil(caracteristicas, origenes)
print("Ganador:", bt["ganador"], "· mejora vs. base estacional:", bt["mejora_ganador_vs_estacional_pct"], "%")
pd.DataFrame(bt["metricas"]).T"""),
        ("code", """\
tabla = bt["por_origen"].pivot(index="origen", columns="modelo", values="WAPE_pct")
ax = tabla.plot(marker="o", figsize=(11, 4))
ax.set_ylabel("WAPE (%)")
ax.set_title("WAPE por corte")
plt.show()"""),
        ("code", """\
g = bt["ganador"]
r = bt["resultados"]
top = r.groupby("distrito")["delitos"].sum().idxmax()
d = r[r["distrito"] == top].set_index("fecha")
fig, ax = plt.subplots(figsize=(11, 4))
ax.fill_between(d.index, d[f"inf_{g}"], d[f"sup_{g}"], alpha=0.2, label="IP 90 %")
ax.plot(d.index, d["delitos"], "o-", color="black", label="Real")
ax.plot(d.index, d[f"pred_{g}"], "s--", label=g)
ax.set_title(f"Distrito {top}")
ax.legend()
plt.show()
print(f"Cobertura del intervalo del 90 % en todos los distritos: {bt['metricas'][g]['cobertura_pct']} %")"""),
        ("md", """El modelo lineal (Ridge) y el Random Forest quedan muy cerca y ambos reducen el error frente a las líneas base. La cobertura del intervalo queda algo por debajo del 90 % nominal: conviene leerlo como un rango algo optimista."""),
    ],
}


def construir(nombre: str, celdas: list[tuple[str, str]]) -> nbformat.NotebookNode:
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    nb.cells = [nbformat.v4.new_markdown_cell(t) if tipo == "md" else nbformat.v4.new_code_cell(t) for tipo, t in celdas]
    return nb


def main() -> None:
    nombres = sys.argv[1:] or list(NOTEBOOKS)
    for nombre in nombres:
        nb = construir(nombre, NOTEBOOKS[nombre])
        NotebookClient(nb, timeout=900, kernel_name="python3", resources={"metadata": {"path": str(CARPETA)}}).execute()
        nbformat.write(nb, CARPETA / nombre)
        print(f"OK {nombre}")


if __name__ == "__main__":
    main()
