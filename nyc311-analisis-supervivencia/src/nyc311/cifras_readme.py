"""Genera README.es.md y docs/GUIA_PASO_A_PASO.md desde plantillas y desde reports/.

Ninguna cifra de esos documentos se escribe a mano: las plantillas de `scripts/plantillas/` tienen
marcadores `{{clave}}` que este módulo rellena con `reports/resultados.json` y `reports/tablas/*.csv`.
La prueba `tests/test_cifras_readme.py` falla si alguien edita el README a mano o si cambian los resultados.

Uso:
    python -m nyc311.cifras_readme             # regenera README.es.md y la guía
    python -m nyc311.cifras_readme --verificar # solo comprueba (código 1 si hay desfase)
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from nyc311.config import ARCHIVO_RESULTADOS, DIR_TABLAS, RAIZ
from nyc311.etiquetas import BOROUGHS_ES, tipo_es

DIR_PLANTILLAS = RAIZ / "scripts" / "plantillas"
DOCUMENTOS: dict[str, Path] = {
    "README.md": RAIZ / "README.es.md",
    "GUIA_PASO_A_PASO.md": RAIZ / "docs" / "GUIA_PASO_A_PASO.md",
}
_MARCADOR = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")
AVISO = (
    "<!-- Archivo generado por `python -m nyc311.cifras_readme` desde scripts/plantillas/{nombre}.\n"
    "     No lo edites a mano: cambia la plantilla y vuelve a generarlo. Todas las cifras salen de reports/. -->\n"
)


def n(valor: float, decimales: int = 1) -> str:
    """Formato numérico es-EC: punto de miles y coma decimal (7.544.678 · 37,1)."""
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def duracion(dias: float) -> str:
    """Duración legible: minutos, horas o días."""
    if dias is None or pd.isna(dias) or math.isinf(dias):
        return "no alcanzada"
    if dias < 1 / 24:
        return f"{n(dias * 1440, 0)} min"
    if dias < 1:
        return f"{n(dias * 24, 1)} h"
    return f"{n(dias, 1)} días"


def _fila(df: pd.DataFrame, columna: str, valor: str) -> pd.Series:
    return df.loc[df[columna].astype(str).eq(valor)].iloc[0]


def construir_contexto() -> dict[str, str]:
    res = json.loads(ARCHIVO_RESULTADOS.read_text(encoding="utf-8"))
    c: dict[str, str] = {}
    f, cal, g = res["fuente"], res["calidad"], res["global"]
    c["fecha_corte"] = f["fecha_corte"].replace("T", " ")
    c["fecha_descarga"] = f["fecha_descarga_utc"]
    for k in ["filas_crudas", "filas_limpias", "filas_descartadas", "cierre_antes_de_apertura", "cerradas_sin_fecha_cierre",
              "cierre_posterior_al_corte", "fecha_cierre_con_estado_abierto", "cierres_instantaneos", "censuradas_abiertas",
              "eventos_cerradas", "borough_sin_dato", "zip_invalido_o_nulo", "duplicados_unique_key", "n_tipos_queja", "n_agencias"]:
        c[k] = n(cal[k], 0)
    c["pct_censuradas"] = n(cal["pct_censuradas"], 2)
    imp = cal["cierre_antes_de_apertura_por_agencia"]
    c["imposibles_dot_dep_pct"] = n(100 * (imp.get("DOT", 0) + imp.get("DEP", 0)) / cal["cierre_antes_de_apertura"], 0)

    c["mediana_global_h"] = n(g["mediana_km_horas"], 1)
    c["mediana_global_ic"] = f"{n(g['mediana_ic_inf_horas'], 2)}–{n(g['mediana_ic_sup_horas'], 2)} h"
    c["promedio_ingenuo_global_d"] = n(g["promedio_ingenuo_cerradas_dias"], 1)
    c["mediana_ingenua_global_h"] = n(g["mediana_ingenua_cerradas_horas"], 1)
    c["rmst_90_global_d"] = n(g["rmst_90d_dias"], 1)
    for k in ["pct_cerradas_1d", "pct_cerradas_7d", "pct_cerradas_30d", "pct_abiertas_90d"]:
        c[f"global_{k}"] = n(g[k], 1)

    # Sesgo: corte retrospectivo
    exp = pd.DataFrame(res["sesgo"]["tabla"])
    c["sesgo_corte"] = res["sesgo"]["corte_ficticio"]
    filas = []
    for grupo in ["Todas", "NYPD", "HPD", "DSNY", "DOT", "DOHMH", "DOB", "DPR", "TLC", "EDC"]:
        r = _fila(exp, "grupo", grupo)
        filas.append(
            f"| {'Todas las agencias' if grupo == 'Todas' else grupo} | {n(r['n'], 0)} | {n(r['pct_abiertas_corte_ficticio'], 1)} % "
            f"| {duracion(r['mediana_ingenua_ficticio'])} | **{duracion(r['mediana_km_ficticio'])}** | {duracion(r['mediana_verdad'])} "
            f"| {duracion(r['promedio_ingenuo_ficticio'])} | {duracion(r['promedio_verdad_cerradas'])} |"
        )
    c["tabla_sesgo"] = "\n".join(filas)
    for ag in ["DOB", "DPR", "TLC", "EDC"]:
        r = _fila(exp, "grupo", ag)
        c[f"sesgo_{ag.lower()}_ingenua"] = duracion(r["mediana_ingenua_ficticio"])
        c[f"sesgo_{ag.lower()}_km"] = duracion(r["mediana_km_ficticio"])
        c[f"sesgo_{ag.lower()}_verdad"] = duracion(r["mediana_verdad"])
        c[f"sesgo_{ag.lower()}_prom_ingenuo"] = duracion(r["promedio_ingenuo_ficticio"])
        c[f"sesgo_{ag.lower()}_prom_verdad"] = duracion(r["promedio_verdad_cerradas"])
        c[f"sesgo_{ag.lower()}_abiertas"] = n(r["pct_abiertas_corte_ficticio"], 0)
        c[f"sesgo_{ag.lower()}_veces"] = n(r["mediana_verdad"] / r["mediana_ingenua_ficticio"], 1)

    # Kaplan-Meier por agencia y tipo
    km_a = pd.read_csv(DIR_TABLAS / "km_agencias.csv")
    filas = []
    for _, r in km_a.head(10).iterrows():
        filas.append(
            f"| {r['agencia']} | {n(r['n'], 0)} | {n(r['pct_censuradas'], 1)} % | **{duracion(r['mediana_km_dias'])}** "
            f"({duracion(r['mediana_ic_inf'])} – {duracion(r['mediana_ic_sup'])}) | {n(r['pct_cerradas_7d'], 1)} % "
            f"| {n(r['pct_cerradas_30d'], 1)} % | {duracion(r['promedio_ingenuo_cerradas_dias'])} |"
        )
    c["tabla_agencias"] = "\n".join(filas)
    for ag in ["NYPD", "HPD", "DSNY", "DOB", "DPR", "DOT", "TLC"]:
        r = _fila(km_a, "agencia", ag)
        c[f"km_{ag.lower()}"] = duracion(r["mediana_km_dias"])
        c[f"km_{ag.lower()}_7d"] = n(r["pct_cerradas_7d"], 1)
    for ag in ["TLC", "DPR", "DOB"]:
        r = _fila(km_a, "agencia", ag)
        c[f"km_{ag.lower()}_censura"] = n(r["pct_censuradas"], 1)
        c[f"km_{ag.lower()}_mediana_ingenua"] = duracion(r["mediana_ingenua_cerradas_dias"])
        c[f"km_{ag.lower()}_promedio_ingenuo"] = duracion(r["promedio_ingenuo_cerradas_dias"])
    km_t = pd.read_csv(DIR_TABLAS / "km_tipos_queja.csv").head(20).sort_values("mediana_km_dias")
    c["tipo_mas_rapido"] = tipo_es(km_t.iloc[0]["tipo_queja"])
    c["tipo_mas_rapido_med"] = duracion(km_t.iloc[0]["mediana_km_dias"])
    c["tipo_mas_lento"] = tipo_es(km_t.iloc[-1]["tipo_queja"])
    c["tipo_mas_lento_med"] = duracion(km_t.iloc[-1]["mediana_km_dias"])
    km_c = pd.read_csv(DIR_TABLAS / "km_canales.csv")
    for canal, clave in [("Teléfono", "telefono"), ("Web", "web"), ("App móvil", "app"), ("Otro/desconocido", "otro")]:
        c[f"km_canal_{clave}"] = duracion(_fila(km_c, "canal", canal)["mediana_km_dias"])
    mezcla = res["mezcla_canal"]
    c["pct_hpd_telefono"] = n(mezcla["Teléfono"]["pct_hpd"], 0)
    c["pct_hpd_app"] = n(mezcla["App móvil"]["pct_hpd"], 0)
    c["pct_nypd_app"] = n(mezcla["App móvil"]["pct_nypd"], 0)
    c["pct_solicitudes_si"] = n(res["pct_solicitudes_por_borough"]["STATEN ISLAND"], 0)
    km_b = pd.read_csv(DIR_TABLAS / "km_boroughs.csv")
    for b in ["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"]:
        c[f"km_{b.lower().replace(' ', '_')}"] = duracion(_fila(km_b, "borough", b)["mediana_km_dias"])

    lr = pd.read_csv(DIR_TABLAS / "logrank.csv")
    filas = []
    for _, r in lr.iterrows():
        p = "< 1e-300" if r["p_valor"] == 0 else f"{r['p_valor']:.1e}"
        dimension = r["dimension"].replace("tipo_queja", "tipo de queja").replace(" | ", ", dentro de ")
        filas.append(f"| {dimension} | {r['grupos']} | {n(r['chi2'], 0)} | {r['gl']} | {p} |")
    c["tabla_logrank"] = "\n".join(filas)

    # Cox
    cox = res["cox"]
    c["cox_n"] = n(cox["n_muestra"], 0)
    c["cox_c_a"] = n(cox["modelo_A"]["concordancia"], 3)
    c["cox_c_b"] = n(cox["modelo_B"]["concordancia"], 3)
    for modelo in ["A", "B"]:
        hr = pd.DataFrame(cox[f"modelo_{modelo}"]["hr"])
        filas = []
        for _, r in hr.iterrows():
            nombre = r["covariable"]
            for k, v in BOROUGHS_ES.items():
                nombre = nombre.replace(k, v)
            nombre = (nombre.replace("agencia=", "Agencia ").replace("borough=", "Borough ").replace("canal=", "Canal ")
                      .replace("fin_de_semana", "Creada en fin de semana").replace("nocturna", "Creada de 22 h a 6 h"))
            filas.append(f"| {nombre} | **{n(r['hr'], 2)}** ({n(r['ic_inf'], 2)}–{n(r['ic_sup'], 2)}) | {r['lectura']} |")
        c[f"tabla_cox_{modelo.lower()}"] = "\n".join(filas)
        for _, r in hr.iterrows():
            clave = re.sub(r"[^a-z0-9]+", "_", r["covariable"].lower().replace("ó", "o").replace("é", "e")).strip("_")
            c[f"hr_{modelo.lower()}_{clave}"] = n(r["hr"], 2)
            c[f"hr_{modelo.lower()}_{clave}_pct"] = n(abs(r["hr"] - 1) * 100, 0)
    ven = pd.DataFrame(cox["hr_por_ventana"])
    vb = ven.loc[ven["covariable"].eq("borough=BRONX")].reset_index(drop=True)
    for i, r in vb.iterrows():
        c[f"ventana_{i}"] = r["ventana"]
        c[f"hr_bronx_ventana_{i}"] = n(r["hr"], 2)
    ph_b = pd.DataFrame(cox["modelo_B"]["ph"])
    c["ph_b_max_cov"] = ph_b.iloc[0]["covariable"]
    c["ph_b_max_est"] = n(ph_b.iloc[0]["estadistico"], 1)
    ph_a = pd.DataFrame(cox["modelo_A"]["ph"])
    c["ph_a_max_cov"] = ph_a.iloc[0]["covariable"]
    c["ph_a_max_est"] = n(ph_a.iloc[0]["estadistico"], 1)
    c["ph_a_n_agencias_top5"] = str(int(ph_a.head(5)["covariable"].str.startswith("agencia").sum()))

    # Equidad
    eq = res["equidad"]
    eb = pd.DataFrame(eq["boroughs"])
    oe_h = eq["oe_por_horizonte"]
    filas = []
    for _, r in eb.loc[eb["borough"].ne("SIN DATO")].sort_values("o_entre_e").iterrows():
        h = oe_h[r["borough"]]
        filas.append(
            f"| {BOROUGHS_ES[r['borough']]} | {n(r['n'], 0)} | {n(r['pct_cerradas_7d'], 1)} % | {n(r['pct_esperado_7d'], 1)} % "
            f"| **{n(r['o_entre_e'], 3)}** ({n(r['ic_inf'], 3)}–{n(r['ic_sup'], 3)}) | {n(h['1 h'], 3)} | {n(h['8 h'], 3)} "
            f"| {n(h['1 día'], 3)} |"
        )
    c["tabla_equidad"] = "\n".join(filas)
    for _, r in eb.iterrows():
        k = r["borough"].lower().replace(" ", "_")
        c[f"oe_{k}"] = n(r["o_entre_e"], 3)
        c[f"pct7_{k}"] = n(r["pct_cerradas_7d"], 1)
        c[f"esp7_{k}"] = n(r["pct_esperado_7d"], 1)
        for etiqueta, sufijo in [("1 h", "h1"), ("8 h", "h8"), ("1 día", "d1")]:
            c[f"oe_{sufijo}_{k}"] = n(oe_h[r["borough"]][etiqueta], 3)
    c["bronx_h1_pct"] = n(100 * (1 - oe_h["BRONX"]["1 h"]), 0)
    for k in ["n_zip_analizados", "n_zip_significativos", "n_zip_lentos", "n_zip_rapidos"]:
        c[k] = str(eq[k])
    c["oe_zip_p05"] = n(eq["oe_zip_p05"], 3)
    c["oe_zip_p95"] = n(eq["oe_zip_p95"], 3)
    c["pct_lentos_en_bronx"] = n(eq["pct_lentos_en_bronx"], 0)
    c["pct_rapidos_en_si"] = n(eq["pct_rapidos_en_staten_island"], 0)
    filas = []
    for r in eq["zip_mas_lentos"] + eq["zip_mas_rapidos"]:
        filas.append(f"| {r['zip']} | {BOROUGHS_ES.get(r['borough'], r['borough'])} | {n(r['n'], 0)} | {n(r['pct_cerradas_7d'], 1)} % "
                     f"| {n(r['pct_esperado_7d'], 1)} % | **{n(r['o_entre_e'], 3)}** |")
    c["tabla_zip"] = "\n".join(filas)
    c["zip_mas_lento"] = eq["zip_mas_lentos"][0]["zip"]
    c["zip_mas_lento_oe"] = n(eq["zip_mas_lentos"][0]["o_entre_e"], 3)
    c["nota_zip_mas_lento"] = (
        " Es Roosevelt Island: una isla residencial pequeña, con administración y accesos propios."
        if c["zip_mas_lento"] == "10044" else ""
    )
    c["n_zip_rapidos_si"] = n(round(eq["pct_rapidos_en_staten_island"] * eq["n_zip_rapidos"] / 100), 0)

    # Evolución
    ev = res["evolucion"]
    (p1, d1), (p2, d2) = sorted(ev["periodos"].items())
    c["periodo1"], c["periodo2"] = p1, p2
    c["p1_mediana_h"], c["p2_mediana_h"] = n(d1["mediana_km_horas"], 1), n(d2["mediana_km_horas"], 1)
    c["p1_pct7"], c["p2_pct7"] = n(d1["pct_cerradas_7d"], 1), n(d2["pct_cerradas_7d"], 1)
    c["p1_oe"], c["p2_oe"] = n(d1["o_entre_e"], 3), n(d2["o_entre_e"], 3)
    c["dif_pct7_pp"] = n(d2["pct_cerradas_7d"] - d1["pct_cerradas_7d"], 1)
    c["mes_mediana_max"] = ev["mes_mediana_max"]["mes"]
    c["mes_mediana_max_h"] = n(24 * ev["mes_mediana_max"]["mediana_km_dias"], 1)
    c["mes_mediana_min"] = ev["mes_mediana_min"]["mes"]
    c["mes_mediana_min_h"] = n(24 * ev["mes_mediana_min"]["mediana_km_dias"], 1)
    c["mes_oe_min"] = ev["mes_oe_min"]["mes"]
    c["mes_oe_min_val"] = n(ev["mes_oe_min"]["o_entre_e"], 3)
    c["mes_oe_max"] = ev["mes_oe_max"]["mes"]
    c["mes_oe_max_val"] = n(ev["mes_oe_max"]["o_entre_e"], 3)
    c["calef_max_mes"] = ev["pct_calefaccion_max"]["mes"]
    c["calef_max_pct"] = n(ev["pct_calefaccion_max"]["pct"], 1)
    c["calef_min_mes"] = ev["pct_calefaccion_min"]["mes"]
    c["calef_min_pct"] = n(ev["pct_calefaccion_min"]["pct"], 1)
    c["dohmh_inst_1"] = n(ev["dohmh"]["pct_instantaneos"][p1], 0)
    c["dohmh_inst_2"] = n(ev["dohmh"]["pct_instantaneos"][p2], 0)
    c["roedor_inst_1"] = n(ev["dohmh"]["pct_instantaneos_roedores"][p1], 0)
    c["roedor_inst_2"] = n(ev["dohmh"]["pct_instantaneos_roedores"][p2], 0)
    c["comida_60d"] = n(ev["dohmh"]["pct_comida_cerradas_a_60_dias"], 0)
    ag = pd.DataFrame(ev["agencias"])
    for clave in ["DOHMH", "DOB", "DOT", "HPD"]:
        r = _fila(ag, "agencia", clave)
        c[f"anual_{clave.lower()}_1"] = duracion(r["mediana_anio1_dias"])
        c[f"anual_{clave.lower()}_2"] = duracion(r["mediana_anio2_dias"])
    filas = [f"| {r['agencia']} | {duracion(r['mediana_anio1_dias'])} | {duracion(r['mediana_anio2_dias'])} | {'+' if r['cambio_pct'] > 0 else ''}{n(r['cambio_pct'], 0)} % |"
             for _, r in ag.loc[ag["agencia"].ne("Otras")].sort_values("cambio_pct").iterrows()]
    c["tabla_agencias_anual"] = "\n".join(filas)
    return c


def rellenar(plantilla: str, contexto: dict[str, Any]) -> str:
    faltan = sorted({m for m in _MARCADOR.findall(plantilla) if m not in contexto})
    if faltan:
        raise KeyError(f"Marcadores sin valor: {faltan}")
    return _MARCADOR.sub(lambda m: str(contexto[m.group(1)]), plantilla)


def documentos_esperados() -> dict[Path, str]:
    contexto = construir_contexto()
    salida = {}
    for nombre, destino in DOCUMENTOS.items():
        plantilla = (DIR_PLANTILLAS / nombre).read_text(encoding="utf-8")
        salida[destino] = AVISO.format(nombre=nombre) + rellenar(plantilla, contexto)
    return salida


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verificar", action="store_true")
    args = parser.parse_args()
    desfasados = []
    for destino, texto in documentos_esperados().items():
        if args.verificar:
            if not destino.exists() or destino.read_text(encoding="utf-8") != texto:
                desfasados.append(destino.name)
        else:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(texto, encoding="utf-8")
            print(f"generado {destino.relative_to(RAIZ)}")
    if desfasados:
        print(f"Desfasados: {desfasados}")
        sys.exit(1)


if __name__ == "__main__":
    main()
