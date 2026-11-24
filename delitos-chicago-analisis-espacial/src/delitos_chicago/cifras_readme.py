"""Genera README.es.md y docs/GUIA_PASO_A_PASO.md a partir de plantillas y de los resultados en reports/.

Ninguna cifra de esos documentos se escribe a mano: las plantillas de `scripts/plantillas/` tienen
marcadores `{{clave}}` que este módulo rellena leyendo reports/. La prueba
`tests/test_cifras_readme.py` falla si alguien edita el README a mano o si cambian los resultados.

Uso:
    python -m delitos_chicago.cifras_readme             # regenera README.es.md y la guía
    python -m delitos_chicago.cifras_readme --verificar # solo comprueba (código 1 si hay desfase)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from delitos_chicago.config import ANIO_CAMBIO_FIN, ANIO_CAMBIO_INI, MUESTRA, RAIZ, REPORTES
from delitos_chicago.pronostico import MODELOS

DIR_PLANTILLAS = RAIZ / "scripts" / "plantillas"
DOCUMENTOS = {"README.md": RAIZ / "README.es.md", "GUIA_PASO_A_PASO.md": RAIZ / "docs" / "GUIA_PASO_A_PASO.md"}
_MARCADOR = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")

TIPOS_ES = {
    "THEFT": "Hurto (*theft*)",
    "BATTERY": "Agresión física (*battery*)",
    "CRIMINAL DAMAGE": "Daño a la propiedad",
    "NARCOTICS": "Narcóticos",
    "ASSAULT": "Amenaza o asalto (*assault*)",
    "OTHER OFFENSE": "Otro delito",
    "BURGLARY": "Robo a vivienda o local (*burglary*)",
    "MOTOR VEHICLE THEFT": "Robo de vehículo motorizado",
    "DECEPTIVE PRACTICE": "Fraude (*deceptive practice*)",
    "ROBBERY": "Robo con violencia (*robbery*)",
    "STALKING": "Acoso (*stalking*)",
    "CRIMINAL SEXUAL ASSAULT": "Agresión sexual criminal",
    "HOMICIDE": "Homicidio",
    "GAMBLING": "Juego ilegal",
    "PROSTITUTION": "Prostitución",
    "WEAPONS VIOLATION": "Infracción de armas",
}
CAMBIO_MOSTRAR = ["MOTOR VEHICLE THEFT", "STALKING", "HOMICIDE", "ROBBERY", "CRIMINAL SEXUAL ASSAULT", "THEFT", "NARCOTICS", "GAMBLING"]
ARRESTO_MOSTRAR = ["PROSTITUTION", "NARCOTICS", "GAMBLING", "WEAPONS VIOLATION", "HOMICIDE", "THEFT", "MOTOR VEHICLE THEFT", "CRIMINAL DAMAGE", "BURGLARY"]
DIAS = {"Lun": "lunes", "Mar": "martes", "Mié": "miércoles", "Jue": "jueves", "Vie": "viernes", "Sáb": "sábado", "Dom": "domingo"}


def n(valor: float, decimales: int = 0) -> str:
    """Formato numérico en español: punto de miles y coma decimal (8.665.676 · 21,4)."""
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def s(valor: float, decimales: int = 1) -> str:
    """Como `n`, con signo explícito y signo menos tipográfico (+141,8 · −0,4)."""
    return ("+" if valor >= 0 else "−") + n(abs(valor), decimales)


def _tabla(encabezado: list[str], alineacion: str, filas: list[list[str]]) -> str:
    lineas = ["| " + " | ".join(encabezado) + " |", alineacion]
    lineas += ["| " + " | ".join(f) + " |" for f in filas]
    return "\n".join(lineas)


def _leer_json(nombre: str) -> dict[str, Any]:
    return json.loads((REPORTES / nombre).read_text(encoding="utf-8"))


def construir_contexto() -> dict[str, str]:
    """Todas las cifras que citan el README y la guía, leídas de reports/."""
    res = _leer_json("resultados.json")
    pd_ = res["periodo_datos"]
    covid = res["temporal"]["covid"]
    hora = res["temporal"]["patron_horario"]
    est = res["temporal"]["estacionalidad_hurto"]
    gi = res["espacial"]["gi"]
    pron = _leer_json("evaluacion_pronostico.json")
    dom = _leer_json("violencia_domestica.json")
    calidad = res["calidad_datos"]
    anio_c = pd_["ultimo_anio_completo"]
    c: dict[str, str] = {}

    # Periodo y calidad
    c |= {
        "registros_totales": n(pd_["registros_totales"]),
        "registros_completos": n(pd_["registros_anios_completos"]),
        "registros_parcial": n(pd_["registros_anio_parcial"]),
        "anio_completo": str(anio_c),
        "anio_parcial": str(anio_c + 1),
        "ultimo_dato": pd.Timestamp(pd_["ultimo_dato"]).strftime("%d-%m-%Y"),
        "ultimo_mes_completo": pd_["ultimo_mes_completo"],
        "sin_coordenadas": n(calidad["sin_coordenadas"]),
        "pct_sin_coordenadas": n(calidad["pct_sin_coordenadas"], 2),
        "fuera_chicago": n(calidad["coordenadas_fuera_chicago"]),
        "duplicados": n(calidad["duplicados_id"]),
        "tiempo_pipeline": n(res["tiempo_ejecucion_segundos"], 1),
        "memoria_pico_gb": n(res.get("memoria_pico_mb", 0) / 1024, 1),
        "n_figuras": str(res["artefactos"]["figuras_png"]),
        "n_csv": str(res["artefactos"]["reportes_csv"]),
        "poblacion_cmap": n(res["espacial"]["poblacion_total_cmap_2020"]),
    }
    manifiesto = json.loads((RAIZ / "data" / "manifiesto_fuente.json").read_text(encoding="utf-8"))
    c["archivos_manifiesto"] = str(len(manifiesto["archivos"]))
    c["fecha_descarga"] = pd.Timestamp(manifiesto["consultado_utc"]).strftime("%d-%m-%Y")
    c["muestra_parquet"] = n(len(pd.read_parquet(MUESTRA / "muestra_delitos.parquet", columns=["id_delito"])))
    c["muestra_csv"] = n(len(pd.read_csv(MUESTRA / "muestra_delitos.csv", usecols=["id_delito"])))

    # Tendencia
    anual = pd.read_csv(REPORTES / "tendencia_anual.csv").set_index("anio")
    completos = anual[~anual["parcial"]]["delitos"]
    a_max, a_min = int(completos.idxmax()), int(completos.idxmin())
    c |= {
        "anio_max": str(a_max), "delitos_max": n(completos[a_max]),
        "anio_min": str(a_min), "delitos_min": n(completos[a_min]),
        "delitos_ultimo_completo": n(completos[anio_c]),
        "caida_max_a_ultimo_pct": s((completos[anio_c] / completos[a_max] - 1) * 100),
        "caida_2020_vs_2019_pct": s((completos[2020] / completos[2019] - 1) * 100),
    }
    anios_tabla = [2001, a_max, 2010, 2019, 2020, 2021, 2022, 2023, 2024, anio_c]
    filas = []
    for a in sorted(set(anios_tabla)):
        etiqueta = f"{a} (máx.)" if a == a_max else f"{a} (mín.)" if a == a_min else str(a)
        filas.append([etiqueta, n(completos[a])])
    filas.append([f"{anio_c + 1} (parcial, hasta {c['ultimo_dato'][:5]})", n(anual.loc[anio_c + 1, "delitos"])])
    c["tabla_tendencia"] = _tabla(["Año", "Delitos"], "|---|---:|", filas)

    # Armonización
    caso = pd.read_csv(REPORTES / f"control_calidad_renombres_{ANIO_CAMBIO_INI}_{ANIO_CAMBIO_FIN}.csv").set_index("categoria")
    ci, cf = f"conteo_{ANIO_CAMBIO_INI}", f"conteo_{ANIO_CAMBIO_FIN}"
    viejo, nuevo, arm = "CRIM SEXUAL ASSAULT", "CRIMINAL SEXUAL ASSAULT", "CRIMINAL SEXUAL ASSAULT (armonizada)"
    c |= {
        "cs_viejo_ini": n(caso.loc[viejo, ci]), "cs_viejo_fin": n(caso.loc[viejo, cf]),
        "cs_nuevo_ini": n(caso.loc[nuevo, ci]), "cs_nuevo_fin": n(caso.loc[nuevo, cf]),
        "cs_nuevo_cambio": s(caso.loc[nuevo, "cambio_pct"]),
        "cs_arm_ini": n(caso.loc[arm, ci]), "cs_arm_fin": n(caso.loc[arm, cf]),
        "cs_arm_cambio": s(caso.loc[arm, "cambio_pct"]),
    }
    renombres = pd.read_csv(REPORTES / "armonizacion_categorias.csv")
    fila = renombres[renombres["tipo_original"] == viejo].iloc[0]
    c |= {
        "cs_codigos_iucr": str(int(fila["codigos_iucr"])),
        "cs_cobertura": n(fila["cobertura_iucr_pct"], 1),
        "cs_ultimo_anio": str(int(fila["ultimo_anio_original"])),
        "categorias_desaparecidas": str(len(renombres)),
        "tabla_armonizacion": _tabla(
            ["Categoría que desaparece", "Último año", "Registros", "Cobertura IUCR", "Decisión"], "|---|---:|---:|---:|---|",
            [[f"`{r.tipo_original}`", str(r.ultimo_anio_original), n(r.registros_original), f"{n(r.cobertura_iucr_pct, 1)} %",
              r.decision + (f" → `{r.tipo_armonizado}`" if r.tipo_armonizado != r.tipo_original else "")]
             for r in renombres.itertuples()],
        ),
    }

    # Cambio por tipo
    cambio = pd.read_csv(REPORTES / f"cambio_porcentual_{ANIO_CAMBIO_INI}_{ANIO_CAMBIO_FIN}.csv").set_index("tipo_primario")
    c["tabla_cambio"] = _tabla(
        ["Tipo (categorías armonizadas)", str(ANIO_CAMBIO_INI), str(ANIO_CAMBIO_FIN), "Δ"], "|---|---:|---:|---:|",
        [[TIPOS_ES[t], n(cambio.loc[t, ci]), n(cambio.loc[t, cf]), f"{s(cambio.loc[t, 'cambio_pct'])} %"] for t in CAMBIO_MOSTRAR],
    )
    for clave, tipo in {"mvt": "MOTOR VEHICLE THEFT", "narc": "NARCOTICS", "juego": "GAMBLING", "stalk": "STALKING"}.items():
        c[f"cambio_{clave}"] = s(cambio.loc[tipo, "cambio_pct"])
        c[f"cambio_{clave}_ini"] = n(cambio.loc[tipo, ci])
        c[f"cambio_{clave}_fin"] = n(cambio.loc[tipo, cf])

    # Horario y estacionalidad
    c |= {
        "franja_ini": f"{hora['franja_pico_inicio']:02d}:00",
        "franja_fin": f"{hora['franja_pico_fin']:02d}:00",
        "franja_pct": n(hora["franja_pico_pct"], 1),
        "franja_esperado_pct": n(4 / 24 * 100, 1),
        "hora_minima": f"{hora['hora_minima']:02d}:00",
        "pct_medianoche": n(hora["pct_medianoche"], 1),
        "dia_max": DIAS[hora["dia_maximo"]],
        "dia_min": DIAS[hora["dia_minimo"]],
        "dif_dias": n(hora["dif_dia_max_min_pct"], 1),
        "mes_alto": est["mes_alto"],
        "mes_bajo": est["mes_bajo"],
        "amplitud_estacional": n(est["amplitud_pct_media"], 1),
    }

    # COVID
    c |= {
        "covid_pre_ini": covid["inicio_pre"][:7], "covid_pre_fin": covid["fin_pre"][:7],
        "covid_meses_pre": str(covid["meses_pre"]),
        "covid_ini": covid["intervencion"][:7], "covid_fin": covid["fin_evaluacion"][:7],
        "covid_cambio": s(covid["cambio_pct"]), "covid_cambio_inf": s(covid["cambio_inf_pct"]),
        "covid_cambio_sup": s(covid["cambio_sup_pct"]),
        "covid_observado": n(covid["observado_total"]), "covid_contrafactual": n(covid["contrafactual_total"]),
        "covid_diferencia": n(-covid["diferencia_total"]),
        "covid_dif_inf": n(-covid["diferencia_sup"]), "covid_dif_sup": n(-covid["diferencia_inf"]),
        "covid_mape_pre": n(covid["mape_ajuste_pre_pct"], 1),
        "covid_tendencia_pre": s(covid["tendencia_pre_pct_anual"]),
        "covid_fuera": str(covid["meses_fuera_intervalo"]), "covid_meses": str(covid["meses_evaluados"]),
    }
    series = pd.read_csv(REPORTES / "covid_por_serie.csv")
    c["tabla_covid"] = _tabla(
        ["Serie", "Abr–may 2020", f"{c['covid_ini']} a {c['covid_fin']} (IC 95 %)", "Meses fuera del intervalo", "Error de ajuste pre"],
        "|---|---:|---:|---:|---:|",
        [[r.serie, f"{s(r.choque_abr_may_2020_pct)} %", f"{s(r.cambio_pct)} % ({s(r.cambio_inf_pct)} a {s(r.cambio_sup_pct)})",
          f"{r.meses_fuera_intervalo} de {r.meses_evaluados}", f"{n(r.mape_ajuste_pre_pct, 1)} %"] for r in series.itertuples()],
    )
    porserie = series.set_index("serie")
    c["covid_choque_total"] = s(porserie.loc["Todos los delitos", "choque_abr_may_2020_pct"])
    c["covid_choque_hurto"] = s(porserie.loc["Hurto (THEFT)", "choque_abr_may_2020_pct"])
    c["covid_choque_domestica"] = s(porserie.loc["Violencia doméstica (indicador)", "choque_abr_may_2020_pct"])
    c["covid_choque_burglary"] = s(porserie.loc["Robo a vivienda (BURGLARY)", "choque_abr_may_2020_pct"])
    c["covid_mvt"] = s(porserie.loc["Robo de vehículo (MOTOR VEHICLE THEFT)", "cambio_pct"])
    c["covid_mape_narc"] = n(porserie.loc["Narcóticos (NARCOTICS)", "mape_ajuste_pre_pct"], 1)

    # Top tipos
    top = pd.read_csv(REPORTES / "top_tipos.csv")
    c["tabla_top_tipos"] = _tabla(["Tipo primario", f"Total 2001–{anio_c}"], "|---|---:|",
                                  [[TIPOS_ES.get(r.tipo_primario, r.tipo_primario), n(r.delitos)] for r in top.itertuples()])

    # Áreas
    areas = pd.read_csv(REPORTES / "delitos_por_area_comunitaria.csv")
    ventana = res["espacial"]["ventana"]
    c["ventana"] = f"{ventana[0]}–{ventana[-1]}"
    c["n_anios_ventana"] = str(len(ventana))
    c["tabla_areas_tasa"] = _tabla(
        ["Puesto por tasa", "Área comunitaria", "Delitos por año por 100 mil hab.", "Delitos por año", "Puesto por volumen", "Ranking de tasa: medio (mín.–máx.)"],
        "|---:|---|---:|---:|---:|---:|",
        [[str(r.puesto_tasa), f"{r.nombre_area} ({r.area_comunitaria})", n(r.tasa_anual_100k), n(r.delitos_promedio_anual),
          str(r.puesto_volumen), f"{n(r.rank_tasa_promedio, 1)} ({r.rank_tasa_mejor}–{r.rank_tasa_peor})"]
         for r in areas.nsmallest(8, "puesto_tasa").itertuples()],
    )
    vol = areas.nsmallest(5, "puesto_volumen")
    c["tabla_areas_volumen"] = _tabla(
        ["Puesto por volumen", "Área comunitaria", "Delitos por año", "Población 2020", "Tasa por 100 mil", "Puesto por tasa"],
        "|---:|---|---:|---:|---:|---:|",
        [[str(r.puesto_volumen), f"{r.nombre_area} ({r.area_comunitaria})", n(r.delitos_promedio_anual), n(r.poblacion_2020),
          n(r.tasa_anual_100k), str(r.puesto_tasa)] for r in vol.itertuples()],
    )
    primera = areas.nsmallest(1, "puesto_tasa").iloc[0]
    austin = areas[areas["area_comunitaria"] == 25].iloc[0]
    c |= {
        "area_tasa_1": primera["nombre_area"], "area_tasa_1_tasa": n(primera["tasa_anual_100k"]),
        "area_tasa_1_vol": str(int(primera["puesto_volumen"])),
        "austin_vol": str(int(austin["puesto_volumen"])), "austin_tasa": str(int(austin["puesto_tasa"])),
        "austin_tasa_valor": n(austin["tasa_anual_100k"]), "austin_delitos": n(austin["delitos_promedio_anual"]),
        "austin_poblacion": n(austin["poblacion_2020"]),
    }
    top10 = areas.nsmallest(10, "puesto_tasa")
    variable = top10.loc[top10["rank_tasa_desv"].idxmax()]
    c |= {
        "areas_rank_desv_mediana_top10": n(top10["rank_tasa_desv"].median(), 1),
        "areas_rank_desv_max_top10": n(variable["rank_tasa_desv"], 1),
        "areas_rank_desv_max_area": variable["nombre_area"],
        "areas_rank_desv_max_mejor": str(int(variable["rank_tasa_mejor"])),
        "areas_rank_desv_max_peor": str(int(variable["rank_tasa_peor"])),
        "gi_primer_anio": str(ventana[0]),
    }

    # Gi*
    estab = pd.read_csv(REPORTES / "estabilidad_espacial_hotspots.csv")
    col_vs = [col for col in estab.columns if col.startswith("jaccard_vs_") and col != "jaccard_vs_anio_anterior"][0]
    c["tabla_gi"] = _tabla(
        ["Año", "Celdas hotspot", "% de celdas", "% de delitos en hotspots", "Jaccard vs año anterior", f"Jaccard vs {ventana[0]}"],
        "|---:|---:|---:|---:|---:|---:|",
        [[str(r.anio), str(r.celdas_hotspot), f"{n(r.pct_celdas, 1)} %", f"{n(r.pct_delitos_en_hotspots, 1)} %",
          "—" if pd.isna(r.jaccard_vs_anio_anterior) else n(r.jaccard_vs_anio_anterior, 2), n(getattr(r, col_vs), 2)]
         for r in estab.itertuples()],
    )
    pers = pd.read_csv(REPORTES / "hotspots_persistentes_por_area.csv")
    pers = pers[pers["celdas_persistentes"] >= pers["celdas_persistentes"].iloc[min(5, len(pers) - 1)]]  # top 6 con empates
    nombres = [f"{r.nombre_area} ({r.celdas_persistentes})" for r in pers.itertuples()]
    c["gi_areas_persistentes"] = ", ".join(nombres[:-1]) + " y " + nombres[-1]
    c |= {
        "gi_celdas": str(gi["celdas_area_estudio"]),
        "gi_persistentes": str(gi["celdas_hotspot_todos_los_anios"]),
        "gi_alguna_vez": str(gi["celdas_hotspot_alguna_vez"]),
        "gi_pct_celdas_persistentes": n(gi["pct_celdas_persistentes"], 1),
        "gi_pct_delitos_persistentes": n(gi["pct_delitos_ultimo_anio_en_persistentes"], 1),
        "gi_jaccard_medio": n(gi["jaccard_consecutivo_promedio"], 2),
        "gi_jaccard_extremos": n(gi["jaccard_primer_vs_ultimo"], 2),
        "gi_siguen": n(gi["pct_hotspots_primer_anio_que_siguen_ultimo"], 1),
        "gi_max_celdas": str(int(estab["celdas_hotspot"].max())),
        "gi_anio_max_celdas": str(int(estab.loc[estab["celdas_hotspot"].idxmax(), "anio"])),
        "gi_min_celdas": str(int(estab["celdas_hotspot"].min())),
        "gi_pct_delitos_min": n(estab["pct_delitos_en_hotspots"].min(), 1),
        "gi_pct_delitos_max": n(estab["pct_delitos_en_hotspots"].max(), 1),
    }

    # Arrestos, violencia doméstica y distritos
    arresto = pd.read_csv(REPORTES / "tasa_arresto_por_tipo.csv").set_index("tipo_primario")
    c["tabla_arresto"] = _tabla(
        ["Tipo", "Tasa de arresto", "IC 95 % (Wilson)"], "|---|---:|---:|",
        [[TIPOS_ES[t], f"{n(arresto.loc[t, 'tasa_arresto_pct'], 1)} %",
          f"{n(arresto.loc[t, 'ic_inf_pct'], 1)}–{n(arresto.loc[t, 'ic_sup_pct'], 1)} %"] for t in ARRESTO_MOSTRAR],
    )
    c["arresto_burglary"] = n(arresto.loc["BURGLARY", "tasa_arresto_pct"], 1)
    tipos_dom = list(dom["tipos_frecuentes_domestico"].items())[:3]
    c |= {
        "arresto_global": n(res["policial"]["tasa_arresto_global_pct"], 2),
        "dom_total": n(dom["delitos_domesticos"]), "dom_pct": n(dom["proporcion_domestica_pct"], 2),
        "dom_arresto": n(dom["tasa_arresto_domestico_pct"], 1), "nodom_arresto": n(dom["tasa_arresto_no_domestico_pct"], 1),
        "dom_tipos": ", ".join(f"{TIPOS_ES.get(t, t).lower()} ({n(v)})" for t, v in tipos_dom[:-1])
        + f" y {TIPOS_ES.get(tipos_dom[-1][0], tipos_dom[-1][0]).lower()} ({n(tipos_dom[-1][1])})",
    }
    distritos = pd.read_csv(REPORTES / "metricas_distritos_policiales.csv")
    c["tabla_distritos"] = _tabla(
        ["Distrito", f"Delitos 2001–{anio_c}", "Tasa de arresto"], "|---:|---:|---:|",
        [[str(r.distrito), n(r.total_delitos), f"{n(r.tasa_arresto_pct, 1)} %"] for r in distritos.head(4).itertuples()],
    )
    pequenos = distritos[distritos["distrito"].isin([31, 61])].set_index("distrito")["total_delitos"]
    c["distrito_31"], c["distrito_61"] = n(pequenos.get(31, 0)), n(pequenos.get(61, 0))

    # Pronóstico
    m = pron["metricas"]
    conf = pron["configuracion"]
    ganador = pron["ganador"]
    filas = []
    for clave, nombre in MODELOS.items():
        r = m[clave]
        negrita = (lambda t: f"**{t}**") if clave == ganador else (lambda t: t)
        filas.append([negrita(nombre), n(r["MAE"], 1), negrita(f"{n(r['WAPE_pct'], 2)} %"),
                      f"{n(r['WAPE_medio_por_corte'], 2)} ± {n(r['WAPE_desv_por_corte'], 2)}", f"{s(r['Sesgo_pct'], 2)} %",
                      f"{r['cortes_ganados']} de {conf['cortes']}", f"{n(r['cobertura_pct'], 1)} %"])
    c["tabla_pronostico"] = _tabla(
        ["Modelo", "MAE", "WAPE global", "WAPE por corte (media ± desv.)", "Sesgo", "Cortes ganados", "Cobertura IP 90 %"],
        "|---|---:|---:|---:|---:|---:|---:|", filas)
    segundo = sorted((k for k in MODELOS if k != ganador), key=lambda k: m[k]["WAPE_pct"])[0]
    c |= {
        "pron_ganador": MODELOS[ganador], "pron_wape": n(m[ganador]["WAPE_pct"], 2),
        "pron_segundo": MODELOS[segundo], "pron_wape_segundo": n(m[segundo]["WAPE_pct"], 2),
        "pron_base": n(m["Linea_Base_Estacional_t12"]["WAPE_pct"], 2),
        "pron_mejora": n(pron["mejora_ganador_vs_estacional_pct"], 1),
        "pron_cobertura": n(m[ganador]["cobertura_pct"], 1),
        "pron_ancho": n(m[ganador]["ancho_relativo_mediano_pct"], 1),
        "pron_sesgo": s(m[ganador]["Sesgo_pct"], 2),
        "pron_cortes": str(conf["cortes"]), "pron_horizonte": str(conf["horizonte_meses"]),
        "pron_primer_mes": conf["primer_mes_evaluado"], "pron_ultimo_mes": conf["ultimo_mes_evaluado"],
        "pron_meses": str(conf["meses_evaluados"]), "pron_distritos": str(conf["distritos"]),
        "pron_ganados": str(m[ganador]["cortes_ganados"]),
    }
    return c


def renderizar(plantilla: str, contexto: dict[str, str]) -> str:
    """Sustituye cada `{{clave}}`; falla si la plantilla pide una clave inexistente."""
    faltan = sorted({k for k in _MARCADOR.findall(plantilla) if k not in contexto})
    if faltan:
        raise KeyError(f"Claves sin valor en la plantilla: {faltan}")
    return _MARCADOR.sub(lambda m: contexto[m.group(1)], plantilla)


def documentos_esperados() -> dict[Path, str]:
    """Texto que deberían tener README.es.md y la guía según los resultados actuales."""
    contexto = construir_contexto()
    return {
        destino: renderizar((DIR_PLANTILLAS / nombre).read_text(encoding="utf-8"), contexto)
        for nombre, destino in DOCUMENTOS.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenera README y guía con las cifras de reports/.")
    parser.add_argument("--verificar", action="store_true", help="solo comprueba; código 1 si hay desfase")
    args = parser.parse_args()
    desfasados = []
    for destino, texto in documentos_esperados().items():
        if args.verificar:
            if destino.read_text(encoding="utf-8") != texto:
                desfasados.append(destino.name)
        else:
            destino.write_text(texto, encoding="utf-8")
    if desfasados:
        print(f"Desfasados respecto a reports/: {desfasados}")
        return 1
    print("README y guía coinciden con reports/." if args.verificar else "README y guía regenerados.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
