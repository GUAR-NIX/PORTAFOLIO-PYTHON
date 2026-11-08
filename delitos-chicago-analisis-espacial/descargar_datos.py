"""Descarga reanudable de datos de delitos de Chicago, geometrías oficiales y población 2020.

Descarga los CSV anuales desde la API oficial de Chicago (Socrata), verifica filas con DuckDB,
descarga la población del censo 2020 por área comunitaria (CMAP) y registra cada archivo
(URL, fecha, filas, bytes y SHA-256) en data/manifiesto_fuente.json.

Uso:
    python descargar_datos.py                    # descarga lo que falte y registra el manifiesto
    python descargar_datos.py --solo-manifiesto  # solo recalcula el manifiesto de los archivos locales
    python descargar_datos.py --solo-poblacion   # solo descarga la población de CMAP
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import requests

RAIZ = Path(__file__).resolve().parent
RAW = RAIZ / "data" / "raw"
REFERENCIA = RAIZ / "data" / "referencia"
MANIFIESTO = RAIZ / "data" / "manifiesto_fuente.json"
URL_API = "https://data.cityofchicago.org/resource/ijzp-q8t2"
INTENTOS_POR_ANIO = 4
FUENTES_GEO = {
    "community_areas.geojson": "https://data.cityofchicago.org/resource/igwz-8jzy.geojson",
    "police_districts.geojson": "https://data.cityofchicago.org/resource/24zt-jpfn.geojson",
}
# Población del censo 2020 por área comunitaria: CMAP, Community Data Snapshots 2026 (capa CCA, campo F2020_POP)
URL_CMAP = (
    "https://services5.arcgis.com/LcMXE3TFhi1BSaCY/arcgis/rest/services/"
    "Community_Data_Snapshots_2026/FeatureServer/11/query"
)
PARAMS_CMAP = {"where": "1=1", "outFields": "GEOG,F2010_POP,F2020_POP", "returnGeometry": "false", "f": "json"}
# CMAP y el GeoJSON de la ciudad escriben distinto dos nombres
ALIAS_CMAP = {"THE LOOP": "LOOP", "O'HARE": "OHARE"}


def contar_filas_csv(ruta: Path) -> int:
    """Cuenta el número de registros en un CSV usando DuckDB."""
    if not ruta.exists() or ruta.stat().st_size == 0:
        return 0
    con = duckdb.connect()
    try:
        res = con.execute("SELECT count(*) FROM read_csv_auto(?, all_varchar=true, header=true)", [str(ruta)]).fetchone()
        return int(res[0]) if res else 0
    except Exception:
        import csv
        try:
            with ruta.open("r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                next(reader, None)
                return sum(1 for _ in reader)
        except Exception:
            return 0


def sha256(ruta: Path) -> str:
    """Calcula el hash SHA-256 de un archivo en bloques."""
    resumen = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(8 * 1024 * 1024), b""):
            resumen.update(bloque)
    return resumen.hexdigest()


def obtener_conteos(sesion: requests.Session) -> dict[int, int]:
    """Obtiene el número oficial de delitos por año desde la API."""
    parametros = {"$select": "year,count(*) as filas", "$group": "year", "$order": "year"}
    respuesta = sesion.get(f"{URL_API}.json", params=parametros, timeout=120)
    respuesta.raise_for_status()
    datos = respuesta.json()
    if isinstance(datos, dict) and datos.get("error"):
        raise RuntimeError(f"Error de la API: {datos.get('message')}")
    return {int(x["year"]): int(x["filas"]) for x in datos if x.get("year")}


def descargar_archivo(
    sesion: requests.Session,
    url: str,
    destino: Path,
    parametros: dict[str, str | int] | None = None,
) -> None:
    """Descarga un archivo con escritura atómica via archivo parcial."""
    parcial = destino.with_suffix(destino.suffix + ".parcial")
    parcial.parent.mkdir(parents=True, exist_ok=True)
    with sesion.get(url, params=parametros, stream=True, timeout=(30, 600)) as respuesta:
        respuesta.raise_for_status()
        with parcial.open("wb") as archivo:
            for bloque in respuesta.iter_content(4 * 1024 * 1024):
                if bloque:
                    archivo.write(bloque)
    parcial.replace(destino)


def descargar_poblacion_cmap(sesion: requests.Session, destino: Path = REFERENCIA / "poblacion_areas_cmap_2020.csv") -> Path:
    """Descarga la población 2010 y 2020 por área comunitaria (CMAP) y la une al número oficial de área."""
    import geopandas as gpd
    import pandas as pd

    respuesta = sesion.get(URL_CMAP, params=PARAMS_CMAP, timeout=120)
    respuesta.raise_for_status()
    cmap = pd.DataFrame([f["attributes"] for f in respuesta.json()["features"]])
    cmap["clave"] = cmap["GEOG"].str.upper().replace(ALIAS_CMAP)
    areas = gpd.read_file(RAW / "community_areas.geojson")
    areas = pd.DataFrame({"area_comunitaria": areas["area_numbe"].astype(int), "clave": areas["community"].str.upper()})
    tabla = areas.merge(cmap, on="clave", how="left", validate="one_to_one")
    if tabla["F2020_POP"].isna().any() or len(tabla) != 77:
        raise RuntimeError(f"No se pudo unir la población de CMAP: {tabla[tabla['F2020_POP'].isna()]}")
    tabla = tabla.rename(columns={"GEOG": "nombre_cmap", "F2010_POP": "poblacion_2010", "F2020_POP": "poblacion_2020"})
    destino.parent.mkdir(parents=True, exist_ok=True)
    tabla[["area_comunitaria", "nombre_cmap", "poblacion_2010", "poblacion_2020"]].astype(
        {"poblacion_2010": int, "poblacion_2020": int}
    ).sort_values("area_comunitaria").to_csv(destino, index=False)
    return destino


def _registro(ruta: Path, url: str, **extra: Any) -> dict[str, Any]:
    """Ficha de trazabilidad de un archivo local (la fecha es su última modificación, en UTC)."""
    fecha = datetime.fromtimestamp(ruta.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    return {
        "archivo": ruta.relative_to(RAIZ).as_posix(),
        "url": url,
        "fecha_descarga_utc": fecha,
        **extra,
        "bytes": ruta.stat().st_size,
        "sha256": sha256(ruta),
    }


def registrar_manifiesto(conteos_api: dict[int, int] | None = None) -> dict[str, Any]:
    """Escribe data/manifiesto_fuente.json con URL, fecha, filas, bytes y SHA-256 de cada archivo fuente."""
    from urllib.parse import urlencode

    previo = json.loads(MANIFIESTO.read_text(encoding="utf-8")) if MANIFIESTO.exists() else {}
    archivos: list[dict[str, Any]] = []
    for ruta in sorted(RAW.glob("crimes_*.csv")):
        anio = int(ruta.stem.split("_")[1])
        consulta = urlencode({"$where": f"year={anio}", "$order": "id"})
        extra: dict[str, Any] = {"anio": anio, "filas": contar_filas_csv(ruta)}
        if conteos_api and anio in conteos_api:
            extra["filas_api"] = conteos_api[anio]
        archivos.append(_registro(ruta, f"{URL_API}.csv?{consulta}", **extra))
    for nombre, url in FUENTES_GEO.items():
        if (RAW / nombre).exists():
            archivos.append(_registro(RAW / nombre, url))
    poblacion = REFERENCIA / "poblacion_areas_cmap_2020.csv"
    if poblacion.exists():
        archivos.append(_registro(
            poblacion, f"{URL_CMAP}?{urlencode(PARAMS_CMAP)}",
            nota="CMAP Community Data Snapshots 2026, campo F2020_POP (censo 2020)",
        ))

    manifiesto = {
        "fuente": "Chicago Data Portal — Crimes 2001 to Present",
        "dataset_id": "ijzp-q8t2",
        "licencia": "Chicago Data Portal Terms of Use",
        "consultado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds") if conteos_api else previo.get("consultado_utc"),
        "conteo_api": sum(conteos_api.values()) if conteos_api else previo.get("conteo_api"),
        "nota": (
            "La fecha de cada archivo es su última modificación local. El portal se actualiza a diario, "
            "así que una descarga nueva tendrá otros hashes y conteos."
        ),
        "archivos": archivos,
    }
    MANIFIESTO.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifiesto


def main() -> None:
    """Punto de entrada principal para la descarga reanudable."""
    RAW.mkdir(parents=True, exist_ok=True)
    sesion = requests.Session()
    sesion.headers.update({"User-Agent": "portafolio-delitos-chicago/1.0"})

    # 1. Descargar geometrías oficiales
    for nombre, url in FUENTES_GEO.items():
        destino = RAW / nombre
        if destino.exists() and destino.stat().st_size > 1000:
            print(f"OK geo: {nombre} ({destino.stat().st_size:,} bytes)")
        else:
            print(f"DESCARGA geo: {nombre}…")
            try:
                descargar_archivo(sesion, url, destino)
                print(f"  → guardado ({destino.stat().st_size:,} bytes)")
            except Exception as e:
                print(f"  Advertencia al descargar {nombre}: {e}")

    # 2. Consultar conteos por año
    print("Consultando conteos oficiales por año...")
    conteos = obtener_conteos(sesion)
    total_esperado = sum(conteos.values())
    print(f"Total histórico registrado: {total_esperado:,} delitos en {len(conteos)} años")

    # 3. Descargar por año en orden inverso (años recientes primero para disponibilidad rápida)
    faltan: list[int] = []
    for anio in sorted(conteos.keys(), reverse=True):
        esperado = conteos[anio]
        destino = RAW / f"crimes_{anio}.csv"
        # Tolerancia de 1% por actualizaciones continuas de la ciudad
        tolerancia = max(200, int(esperado * 0.01))

        if destino.exists():
            obtenidas = contar_filas_csv(destino)
            if abs(obtenidas - esperado) <= tolerancia:
                print(f"OK {anio}: {obtenidas:,} filas verificadas (esperadas ~{esperado:,})")
                continue
            print(f"REINTENTO {anio}: existentes {obtenidas:,} != esperadas {esperado:,}")

        # El portal responde a veces 500/503 o se queda sin responder: se reintenta con espera creciente
        completo = False
        for intento in range(1, INTENTOS_POR_ANIO + 1):
            print(f"DESCARGA {anio}: {esperado:,} filas… (intento {intento}/{INTENTOS_POR_ANIO})")
            try:
                descargar_archivo(
                    sesion,
                    f"{URL_API}.csv",
                    destino,
                    {"$where": f"year={anio}", "$order": "id", "$limit": esperado + 500},
                )
                obtenidas = contar_filas_csv(destino)
                print(f"  → {obtenidas:,} filas guardadas en {destino.name}")
                if abs(obtenidas - esperado) <= tolerancia:
                    completo = True
                    break
                print(f"  Incompleto: {obtenidas:,} filas frente a ~{esperado:,} esperadas")
            except Exception as e:
                print(f"  Error en año {anio}: {e}")
            if intento < INTENTOS_POR_ANIO:
                time.sleep(30 * intento)
        if not completo:
            faltan.append(anio)

    # 4. Población 2020 por área comunitaria y manifiesto con hashes
    print("Descargando población 2020 por área comunitaria (CMAP)...")
    descargar_poblacion_cmap(sesion)
    registrar_manifiesto(conteos)
    if faltan:
        raise SystemExit(
            f"\nFaltan o están incompletos los años {sorted(faltan)} (el portal no respondió). "
            "Vuelve a ejecutar `python descargar_datos.py`: es reanudable y solo baja lo que falta."
        )
    print("\nDescarga finalizada. Manifiesto en data/manifiesto_fuente.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Descarga reanudable de los datos del proyecto.")
    parser.add_argument("--solo-manifiesto", action="store_true", help="no descarga: registra hashes de los archivos locales")
    parser.add_argument("--solo-poblacion", action="store_true", help="descarga solo la población de CMAP y registra el manifiesto")
    args = parser.parse_args()
    if args.solo_poblacion:
        descargar_poblacion_cmap(requests.Session())
        registrar_manifiesto()
    elif args.solo_manifiesto:
        registrar_manifiesto()
    else:
        main()
