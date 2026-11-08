"""Ingesta, limpieza y validación de calidad de datos de delitos de Chicago.

Lee los CSV de delitos descargados, normaliza tipos y nombres de columnas,
audita la calidad de los datos (duplicados, coordenadas inválidas, fechas),
y exporta a formato Parquet particionado por año usando DuckDB.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from delitos_chicago.config import MUESTRA, PROCESADOS, RAW, REPORTES

BBOX_CHICAGO = {
    "lat_min": 41.64,
    "lat_max": 42.03,
    "lon_min": -87.94,
    "lon_max": -87.52,
}


def obtener_archivos_crudos(carpeta_raw: Path = RAW) -> list[Path]:
    """Lista todos los CSV de delitos disponibles en data/raw/."""
    # Excluir archivos parciales
    archivos = sorted([p for p in carpeta_raw.glob("crimes_*.csv") if not p.name.endswith(".parcial")])
    if not archivos:
        unico = carpeta_raw / "crimes.csv"
        if unico.exists():
            return [unico]
    return archivos


def auditar_y_limpiar(
    carpeta_raw: Path = RAW,
    destino: Path = PROCESADOS,
) -> dict[str, Any]:
    """Ejecuta la auditoría de calidad y particiona los datos a Parquet con DuckDB.

    Produce un reporte completo de calidad en reports/calidad.json y reports/calidad.csv.
    """
    archivos = obtener_archivos_crudos(carpeta_raw)
    if not archivos:
        raise FileNotFoundError(f"No se encontraron archivos CSV de delitos en {carpeta_raw}")

    lista_rutas = [str(a).replace("\\", "/") for a in archivos]

    con = duckdb.connect()

    # Inspeccionar columnas para detectar si vienen en minúsculas snake_case o Title Case
    primer_archivo = lista_rutas[0]
    cols_muestra = con.execute(f"SELECT * FROM read_csv_auto('{primer_archivo}', all_varchar=true) LIMIT 1").df().columns
    cols_map = {c.strip().lower().replace(" ", "_"): c for c in cols_muestra}

    def c(nombre: str) -> str:
        real = cols_map.get(nombre)
        return f'"{real}"' if real else "NULL"

    # Construir vista unificada
    con.execute(f"""
        CREATE OR REPLACE VIEW vista_cruda AS
        SELECT
            TRY_CAST({c('id')} AS BIGINT) AS id_delito,
            TRY_CAST({c('case_number')} AS VARCHAR) AS numero_caso,
            COALESCE(
                TRY_CAST({c('date')} AS TIMESTAMP),
                TRY_CAST(strptime({c('date')}, '%m/%d/%Y %I:%M:%S %p') AS TIMESTAMP)
            ) AS fecha,
            TRY_CAST({c('block')} AS VARCHAR) AS cuadra,
            TRY_CAST({c('iucr')} AS VARCHAR) AS codigo_iucr,
            UPPER(TRIM(TRY_CAST({c('primary_type')} AS VARCHAR))) AS tipo_primario,
            TRY_CAST({c('description')} AS VARCHAR) AS descripcion,
            TRY_CAST({c('location_description')} AS VARCHAR) AS lugar,
            TRY_CAST({c('arrest')} AS BOOLEAN) AS arresto,
            TRY_CAST({c('domestic')} AS BOOLEAN) AS domestico,
            TRY_CAST({c('beat')} AS INTEGER) AS beat,
            TRY_CAST({c('district')} AS INTEGER) AS distrito,
            TRY_CAST({c('ward')} AS INTEGER) AS barrio_ward,
            TRY_CAST({c('community_area')} AS INTEGER) AS area_comunitaria,
            TRY_CAST({c('fbi_code')} AS VARCHAR) AS codigo_fbi,
            TRY_CAST({c('x_coordinate')} AS DOUBLE) AS coord_x,
            TRY_CAST({c('y_coordinate')} AS DOUBLE) AS coord_y,
            COALESCE(
                TRY_CAST({c('year')} AS INTEGER),
                TRY_CAST(strftime(TRY_CAST({c('date')} AS TIMESTAMP), '%Y') AS INTEGER)
            ) AS anio,
            TRY_CAST({c('latitude')} AS DOUBLE) AS latitud,
            TRY_CAST({c('longitude')} AS DOUBLE) AS longitud
        FROM read_csv_auto({lista_rutas}, all_varchar=true, union_by_name=true)
    """)

    # Auditoría de métricas de calidad
    total_filas = con.execute("SELECT count(*) FROM vista_cruda").fetchone()[0]
    id_duplicados = con.execute("""
        SELECT count(*) - count(DISTINCT id_delito) FROM vista_cruda WHERE id_delito IS NOT NULL
    """).fetchone()[0]
    sin_coordenadas = con.execute("""
        SELECT count(*) FROM vista_cruda WHERE latitud IS NULL OR longitud IS NULL
    """).fetchone()[0]
    fuera_chicago = con.execute(f"""
        SELECT count(*) FROM vista_cruda
        WHERE latitud IS NOT NULL AND longitud IS NOT NULL
          AND (latitud < {BBOX_CHICAGO['lat_min']} OR latitud > {BBOX_CHICAGO['lat_max']}
               OR longitud < {BBOX_CHICAGO['lon_min']} OR longitud > {BBOX_CHICAGO['lon_max']})
    """).fetchone()[0]
    fechas_nulas = con.execute("SELECT count(*) FROM vista_cruda WHERE fecha IS NULL").fetchone()[0]

    # Distribución por año
    anios_stats = con.execute("""
        SELECT anio, count(*) as conteo
        FROM vista_cruda
        WHERE anio IS NOT NULL
        GROUP BY anio
        ORDER BY anio
    """).df().to_dict(orient="records")

    destino_parquet = destino / "delitos_parquet"
    destino_parquet.mkdir(parents=True, exist_ok=True)

    # Filtrar deduplicando por id_delito manteniendo registros válidos
    con.execute("""
        CREATE OR REPLACE TABLE delitos_limpios AS
        SELECT * EXCLUDE (row_num)
        FROM (
            SELECT *,
                ROW_NUMBER() OVER(PARTITION BY id_delito ORDER BY fecha DESC NULLS LAST) as row_num
            FROM vista_cruda
            WHERE id_delito IS NOT NULL
        )
        WHERE row_num = 1
    """)

    total_limpias = con.execute("SELECT count(*) FROM delitos_limpios").fetchone()[0]

    # Exportar a Parquet particionado por anio
    print(f"Exportando {total_limpias:,} registros a Parquet particionado en {destino_parquet}…")
    con.execute(f"""
        COPY delitos_limpios TO '{str(destino_parquet).replace('\\', '/')}' (FORMAT PARQUET, PARTITION_BY (anio), OVERWRITE_OR_IGNORE true)
    """)

    calidad: dict[str, Any] = {
        "archivos_evaluados": len(archivos),
        "total_registros_brutos": int(total_filas),
        "duplicados_id": int(id_duplicados),
        "fechas_invalidas": int(fechas_nulas),
        "sin_coordenadas": int(sin_coordenadas),
        "pct_sin_coordenadas": round((sin_coordenadas / total_filas * 100), 2) if total_filas else 0.0,
        "coordenadas_fuera_chicago": int(fuera_chicago),
        "total_registros_limpios": int(total_limpias),
        "pct_retenido": round((total_limpias / total_filas * 100), 2) if total_filas else 0.0,
        "distribucion_anios": anios_stats,
    }

    # Guardar reportes
    REPORTES.mkdir(parents=True, exist_ok=True)
    (REPORTES / "calidad.json").write_text(json.dumps(calidad, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Guardar calidad en formato tabular CSV
    df_calidad = pd.DataFrame([
        {"metrica": "Total registros brutos", "valor": total_filas, "unidad": "filas"},
        {"metrica": "Duplicados por ID", "valor": id_duplicados, "unidad": "filas"},
        {"metrica": "Fechas inválidas o nulas", "valor": fechas_nulas, "unidad": "filas"},
        {"metrica": "Sin coordenadas geográficas", "valor": sin_coordenadas, "unidad": "filas"},
        {"metrica": "Coordenadas fuera del polígono de Chicago", "valor": fuera_chicago, "unidad": "filas"},
        {"metrica": "Total registros limpios retenidos", "valor": total_limpias, "unidad": "filas"},
        {"metrica": "Tasa de retención limpia", "valor": round((total_limpias / total_filas * 100), 2), "unidad": "%"},
    ])
    df_calidad.to_csv(REPORTES / "calidad.csv", index=False)

    return calidad


def generar_muestra_ci(
    origen_parquet: Path = PROCESADOS / "delitos_parquet",
    destino: Path = MUESTRA,
    n: int = 10000,
) -> Path:
    """Extrae una muestra aleatoria simple (n filas en Parquet; las primeras 500 también en CSV para inspección rápida)."""
    destino.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    patron = str(origen_parquet / "**/*.parquet").replace("\\", "/")
    df_muestra = con.execute(f"""
        SELECT *
        FROM read_parquet('{patron}', hive_partitioning=true)
        USING SAMPLE {n}
    """).df()

    ruta_pq = destino / "muestra_delitos.parquet"
    ruta_csv = destino / "muestra_delitos.csv"
    df_muestra.to_parquet(ruta_pq, index=False)
    df_muestra.head(500).to_csv(ruta_csv, index=False)
    print(f"Muestra generada con {len(df_muestra):,} filas en {ruta_pq}")
    return ruta_pq
