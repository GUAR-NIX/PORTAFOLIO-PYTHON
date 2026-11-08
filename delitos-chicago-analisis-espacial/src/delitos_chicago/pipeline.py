"""Orquestador del análisis de delitos de Chicago.

1. Ingesta y Parquet particionado (solo si no existe).
2. Armonización de categorías renombradas (detectada con los códigos IUCR).
3. Análisis temporal: tendencia, hora × día, STL, serie interrumpida del COVID-19, cambio 2019 → 2024.
4. Análisis espacial: tasas anuales por 100 mil, Getis-Ord Gi* y estabilidad de hotspots.
5. Arrestos con IC de Wilson, violencia doméstica y distritos.
6. Pronóstico por distrito con backtesting de origen móvil e intervalos de predicción.
7. reports/resultados.json; después, `python -m delitos_chicago.cifras_readme` regenera el README.

Los totales y rankings usan solo años completos; el año en curso aparece marcado como parcial.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from delitos_chicago import armonizacion, espacial, policial, pronostico, temporal
from delitos_chicago.config import (
    ANIO_CAMBIO_FIN, ANIO_CAMBIO_INI, ANIOS_ESPACIALES, FIGURAS, MUESTRA, PROCESADOS, RAW, REPORTES,
)
from delitos_chicago.ingesta import auditar_y_limpiar, generar_muestra_ci

COLUMNAS = "id_delito, fecha, arresto, domestico, distrito, area_comunitaria, CAST(anio AS INTEGER) AS anio, " \
           "latitud, longitud, coord_x, coord_y"
TAM_CELDA_M = 1000.0
SERIES_COVID = {
    "Todos los delitos": None,
    "Hurto (THEFT)": ("tipo_primario", "THEFT"),
    "Agresión (BATTERY)": ("tipo_primario", "BATTERY"),
    "Robo a vivienda (BURGLARY)": ("tipo_primario", "BURGLARY"),
    "Narcóticos (NARCOTICS)": ("tipo_primario", "NARCOTICS"),
    "Robo de vehículo (MOTOR VEHICLE THEFT)": ("tipo_primario", "MOTOR VEHICLE THEFT"),
    "Violencia doméstica (indicador)": ("domestico", True),
}


def _guardar_json(nombre: str, datos: Any) -> None:
    (REPORTES / nombre).write_text(json.dumps(datos, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def cargar_datos(ruta_parquet: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Devuelve (delitos armonizados, tabla de renombres, conteos año × tipo × IUCR sin armonizar)."""
    con = duckdb.connect()
    con.execute("SET memory_limit = '4GB'")
    origen = f"read_parquet('{(ruta_parquet / '**' / '*.parquet').as_posix()}', hive_partitioning=true)"
    conteos = con.execute(
        f"SELECT CAST(anio AS INTEGER) AS anio, tipo_primario, codigo_iucr, count(*) AS conteo FROM {origen} GROUP BY ALL"
    ).df()
    anio_max = int(conteos["anio"].max())
    tabla = armonizacion.detectar_renombres(conteos, anio_ultimo=anio_max - 1)
    tipo = armonizacion.expresion_sql(armonizacion.mapa_renombres(tabla))
    df = con.execute(f"SELECT {COLUMNAS}, {tipo} AS tipo_primario FROM {origen}").df()
    df["tipo_primario"] = df["tipo_primario"].astype("category")
    return df, tabla, conteos


def ejecutar_pipeline(carpeta_raw: Path = RAW) -> dict[str, Any]:
    """Ejecuta el análisis completo y guarda tablas, figuras y resultados.json."""
    inicio = time.time()
    ruta_parquet = PROCESADOS / "delitos_parquet"
    if not any(ruta_parquet.glob("**/*.parquet")):
        print("[1/6] Ingesta, auditoría y particionado con DuckDB...")
        auditar_y_limpiar(carpeta_raw=carpeta_raw)
        generar_muestra_ci(origen_parquet=ruta_parquet, destino=MUESTRA)
    calidad = json.loads((REPORTES / "calidad.json").read_text(encoding="utf-8"))

    print("[2/6] Carga y armonización de categorías...")
    df, renombres, conteos = cargar_datos(ruta_parquet)
    mapa = armonizacion.mapa_renombres(renombres)
    renombres.to_csv(REPORTES / "armonizacion_categorias.csv", index=False)
    caso = armonizacion.comparar_antes_despues(conteos, mapa, ANIO_CAMBIO_INI, ANIO_CAMBIO_FIN)
    caso.to_csv(REPORTES / f"control_calidad_renombres_{ANIO_CAMBIO_INI}_{ANIO_CAMBIO_FIN}.csv", index=False)

    fecha_max = pd.Timestamp(df["fecha"].max())
    mes_completo = pronostico.ultimo_mes_completo(fecha_max)
    anio_completo = mes_completo.year if mes_completo.month == 12 else mes_completo.year - 1
    completos = df[df["anio"] <= anio_completo]
    periodo = f"2001–{anio_completo}"
    faltan = sorted(set(range(2001, anio_completo + 1)) - set(df["anio"].astype(int).unique()))
    if faltan:
        raise RuntimeError(
            f"Faltan los años {faltan} en {ruta_parquet}. Vuelve a ejecutar `python descargar_datos.py` hasta que "
            "termine sin avisos y borra data/procesados/delitos_parquet para que el pipeline vuelva a ingerir los CSV."
        )
    print(f"  → {len(df):,} registros; último dato {fecha_max.date()}; años completos {periodo}")

    print("[3/6] Análisis temporal...")
    anual = df.groupby("anio").size()
    anual.rename("delitos").reset_index().assign(parcial=lambda t: t["anio"] > anio_completo).to_csv(
        REPORTES / "tendencia_anual.csv", index=False)
    temporal.graficar_tendencia_anual(anual, anio_completo + 1, f"(hasta {fecha_max:%d-%m})")
    tabla_hora = temporal.mapa_calor_hora_dia(completos)
    temporal.graficar_mapa_calor_hora_dia(tabla_hora)
    horario = temporal.patron_horario(completos)
    _guardar_json("patron_horario.json", horario)

    top = completos["tipo_primario"].value_counts().head(10)
    top.rename_axis("tipo_primario").rename("delitos").reset_index().to_csv(REPORTES / "top_tipos.csv", index=False)
    temporal.graficar_top_tipos(top, f"Top 10 tipos de delito ({periodo}, categorías armonizadas)")

    stl = temporal.descomposicion_stl(df, "THEFT", hasta=str(mes_completo.date()))
    temporal.graficar_stl(stl, "THEFT (hurto)")
    estacionalidad = temporal.resumen_estacionalidad(stl)

    mensual = temporal.serie_mensual(df)
    mensual = mensual[mensual.index <= mes_completo]
    covid = temporal.serie_interrumpida(mensual)
    covid["tabla"].to_csv(REPORTES / "covid_serie_interrumpida.csv", index=False)
    temporal.graficar_efecto_covid(mensual, covid)
    series = {}
    for nombre, filtro in SERIES_COVID.items():
        s = mensual if filtro is None else temporal.serie_mensual(df, df[filtro[0]] == filtro[1])
        series[nombre] = s[s.index <= mes_completo]
    covid_series = temporal.efecto_covid_por_serie(series)
    covid_series.to_csv(REPORTES / "covid_por_serie.csv", index=False)

    cambio = temporal.cambio_porcentual_por_tipo(df, ANIO_CAMBIO_INI, ANIO_CAMBIO_FIN)
    cambio.to_csv(REPORTES / f"cambio_porcentual_{ANIO_CAMBIO_INI}_{ANIO_CAMBIO_FIN}.csv", index=False)

    print("[4/6] Análisis espacial: tasas anuales y Getis-Ord Gi*...")
    poblacion = espacial.cargar_poblacion()
    gdf_areas = espacial.cargar_geojson_areas()
    nombres = gdf_areas.set_index("area_comunitaria")["nombre_area"]
    tasas = espacial.tasas_anuales_area(completos, poblacion)
    tasas.to_csv(REPORTES / "tasas_anuales_area.csv", index=False)
    resumen_areas = espacial.resumen_areas(tasas[tasas["anio"].isin(ANIOS_ESPACIALES)], nombres)
    resumen_areas.to_csv(REPORTES / "delitos_por_area_comunitaria.csv", index=False)
    ventana = f"{ANIOS_ESPACIALES[0]}–{ANIOS_ESPACIALES[-1]}"
    espacial.graficar_coropleta_tasa(gdf_areas, resumen_areas, f"Tasa anual promedio por 100 mil habitantes, {ventana}")
    espacial.graficar_ranking_areas(resumen_areas, 12, f"Áreas comunitarias, promedio {ventana} (población censo 2020)")
    espacial.generar_mapa_coropleta_html(gdf_areas, resumen_areas, f"Delitos por año por 100 mil hab. ({ventana})")
    espacial.generar_mapa_calor_puntos_html(completos[completos["anio"].isin(ANIOS_ESPACIALES)])

    grilla = espacial.conteos_grilla(completos, ANIOS_ESPACIALES, TAM_CELDA_M)
    gi = espacial.hotspots_gi(grilla)
    gi.drop(columns="p_valor").to_csv(REPORTES / "hotspots_gi_celdas.csv", index=False)
    estab, resumen_gi = espacial.estabilidad_hotspots(gi)
    estab.to_csv(REPORTES / "estabilidad_espacial_hotspots.csv", index=False)
    espacial.areas_de_hotspots_persistentes(gi, gdf_areas, TAM_CELDA_M).to_csv(
        REPORTES / "hotspots_persistentes_por_area.csv", index=False)
    espacial.graficar_hotspots_por_anio(gi, gdf_areas, estab, TAM_CELDA_M)
    espacial.graficar_persistencia(gi, gdf_areas, TAM_CELDA_M)

    print("[5/6] Arrestos, violencia doméstica y distritos...")
    tasas_arresto = policial.tasa_arresto_por_tipo(completos, min_casos=500)
    tasas_arresto.to_csv(REPORTES / "tasa_arresto_por_tipo.csv", index=False)
    policial.graficar_tasa_arresto_por_tipo(tasas_arresto)
    distritos = policial.analisis_distritos_policiales(completos)
    distritos.to_csv(REPORTES / "metricas_distritos_policiales.csv", index=False)
    policial.graficar_distritos_comparativa(distritos)
    domestica = policial.analisis_violencia_domestica(completos)
    _guardar_json("violencia_domestica.json", domestica)

    print("[6/6] Pronóstico con backtesting de origen móvil...")
    serie_distritos = pronostico.preparar_series_mensuales_distrito(df, hasta=mes_completo)
    caracteristicas = pronostico.construir_caracteristicas_tiempo(serie_distritos)
    bt = pronostico.backtesting_origen_movil(caracteristicas, pronostico.origenes_trimestrales(mes_completo))
    evaluacion = {
        "configuracion": bt["configuracion"],
        "ganador": bt["ganador"],
        "mejora_ganador_vs_estacional_pct": bt["mejora_ganador_vs_estacional_pct"],
        "metricas": bt["metricas"],
    }
    _guardar_json("evaluacion_pronostico.json", evaluacion)
    pd.DataFrame.from_dict(bt["metricas"], orient="index").rename_axis("modelo").reset_index().to_csv(
        REPORTES / "pronostico_metricas.csv", index=False)
    bt["por_origen"].to_csv(REPORTES / "backtesting_por_corte.csv", index=False)
    pronostico.graficar_pronostico_vs_real(bt["resultados"], bt["ganador"])
    pronostico.graficar_comparacion_modelos(bt["por_origen"])

    resultados: dict[str, Any] = {
        "proyecto": "PYTHON_03_delitos_chicago",
        "periodo_datos": {
            "primer_anio": int(df["anio"].min()),
            "ultimo_dato": str(fecha_max.date()),
            "ultimo_anio_completo": int(anio_completo),
            "ultimo_mes_completo": mes_completo.strftime("%Y-%m"),
            "registros_totales": int(len(df)),
            "registros_anios_completos": int(len(completos)),
            "registros_anio_parcial": int(len(df) - len(completos)),
        },
        "calidad_datos": {k: calidad[k] for k in (
            "archivos_evaluados", "total_registros_brutos", "duplicados_id", "fechas_invalidas",
            "sin_coordenadas", "pct_sin_coordenadas", "coordenadas_fuera_chicago", "total_registros_limpios",
        )},
        "armonizacion": {"renombres": mapa, "categorias_desaparecidas": int(len(renombres))},
        "temporal": {
            "patron_horario": {k: v for k, v in horario.items() if k != "por_hora"},
            "estacionalidad_hurto": estacionalidad,
            "covid": covid["resumen"],
        },
        "espacial": {"ventana": ANIOS_ESPACIALES, "tam_celda_m": TAM_CELDA_M, "gi": resumen_gi,
                     "poblacion_total_cmap_2020": int(poblacion.sum())},
        "policial": {
            "tasa_arresto_global_pct": round(float(completos["arresto"].mean() * 100), 2),
            "proporcion_violencia_domestica_pct": domestica["proporcion_domestica_pct"],
        },
        "pronostico": evaluacion | {"metricas": None},
        "tiempo_ejecucion_segundos": round(time.time() - inicio, 1),
        "artefactos": {
            "figuras_png": len(list(FIGURAS.glob("*.png"))),
            "reportes_csv": len(list(REPORTES.glob("*.csv"))),
            "mapas_html": len(list(REPORTES.glob("*.html"))),
        },
    }
    del resultados["pronostico"]["metricas"]
    try:
        import psutil

        info = psutil.Process().memory_info()
        resultados["memoria_pico_mb"] = round(getattr(info, "peak_wset", info.rss) / 2**20)
    except ImportError:
        pass
    _guardar_json("resultados.json", resultados)
    print(f"Pipeline completado en {resultados['tiempo_ejecucion_segundos']} s")
    return resultados


if __name__ == "__main__":
    ejecutar_pipeline()
