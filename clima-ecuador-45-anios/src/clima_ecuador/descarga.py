"""
Descarga con caché local de todas las fuentes.

* **ERA5 horario** (1980–2024) desde el archivo público de Open-Meteo en AWS Open Data (``s3://openmeteo``).
  La API gratuita pondera cada petición por ubicaciones × días/14 × variables/10: 45 años × 22 ciudades × 7 variables
  serían ~25 000 llamadas, más del doble del límite diario (10 000). El archivo .om es el mismo ERA5 que sirve la
  API, se lee por rangos HTTP (solo los bytes de cada punto) y no tiene límite de llamadas.
* **API de Open-Meteo** solo para dos cosas pequeñas: qué celda de ERA5 usa Open-Meteo para cada punto
  (selección de celda "land") y una muestra diaria de 2 años para verificar la agregación propia.
* **ONI** (NOAA PSL), **GHCN-Daily** (NOAA NCEI) para la validación y los **límites provinciales** (geoBoundaries).

Cada bloque descargado se guarda en disco y no se vuelve a pedir (``forzar=True`` lo renueva). Todas las
peticiones tienen reintentos con espera creciente; la API, además, pausas entre llamadas y manejo del 429.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import config

TIEMPO_ESPERA = 90      # segundos por petición HTTP
REINTENTOS = 5
PAUSA_API = 1.5         # segundos entre llamadas a la API (muy por debajo de 600/min)
EPOCA = pd.Timestamp("1970-01-01")


# ---------------------------------------------------------------------------
# Utilidades HTTP
# ---------------------------------------------------------------------------
def _get(url: str, params: dict | None = None, reintentos: int = REINTENTOS) -> requests.Response:
    """GET con reintentos y espera creciente. Si la API responde 429 (límite) espera un minuto."""
    ultimo_error: Exception | None = None
    for intento in range(reintentos):
        try:
            r = requests.get(url, params=params, timeout=TIEMPO_ESPERA)
            if r.status_code == 429:
                motivo = r.text[:200]
                if "Daily" in motivo:      # no tiene sentido insistir hasta el día siguiente
                    raise RuntimeError(f"Límite diario de la API agotado: {motivo}")
                time.sleep(60)
                continue
            r.raise_for_status()
            return r
        except (requests.RequestException, ValueError) as e:
            ultimo_error = e
            time.sleep(2 ** intento)
    raise RuntimeError(f"No se pudo descargar {url} tras {reintentos} intentos: {ultimo_error}")


def _con_reintentos(funcion, *args, reintentos: int = REINTENTOS):
    ultimo_error: Exception | None = None
    for intento in range(reintentos):
        try:
            return funcion(*args)
        except Exception as e:  # noqa: BLE001 - errores de red de s3fs/omfiles son de varios tipos
            ultimo_error = e
            time.sleep(2 ** intento)
    raise RuntimeError(f"Falló {funcion.__name__}{args} tras {reintentos} intentos: {ultimo_error}")


# ---------------------------------------------------------------------------
# Celdas de ERA5
# ---------------------------------------------------------------------------
def indice_malla(lat: float, lon: float, resolucion: float = config.RESOLUCION) -> tuple[int, int]:
    """Fila y columna de la malla regular global de ERA5 (lat −90…90, lon −180…179,75)."""
    iy = int(round((lat + 90) / resolucion))
    ix = int(round((lon + 180) / resolucion)) % int(round(360 / resolucion))
    return iy, ix


def celdas_open_meteo(forzar: bool = False, destino: Path = config.CELDAS) -> pd.DataFrame:
    """Pregunta a la API qué celda de ERA5 usa para cada punto y lee la altitud media de esa celda.

    La API elige una celda de tierra con altitud parecida ("cell_selection=land"), no necesariamente la más cercana:
    en la costa la celda más cercana puede ser mar. Una sola llamada con todos los puntos (peso ≈ 3).
    """
    if destino.exists() and not forzar:
        return pd.read_csv(destino)
    pts = config.puntos()
    nombres = list(pts)
    params = {
        "latitude": ",".join(str(pts[n][0]) for n in nombres),
        "longitude": ",".join(str(pts[n][1]) for n in nombres),
        "start_date": "2015-01-01", "end_date": "2015-01-01",
        "daily": "temperature_2m_max", "models": "era5", "timezone": "GMT",
    }
    cuerpo = _get(config.URL_API_ARCHIVO, params).json()
    cuerpo = cuerpo if isinstance(cuerpo, list) else [cuerpo]
    alturas = altura_celdas([indice_malla(c["latitude"], c["longitude"]) for c in cuerpo])
    filas = []
    for n, c, z_celda in zip(nombres, cuerpo, alturas):
        la, lo, z, reg, tipo = pts[n]
        iy, ix = indice_malla(c["latitude"], c["longitude"])
        # HSURF vale −999 en celdas de mar: en Galápagos las islas son más pequeñas que una celda de 25 km
        filas.append({"punto": n, "tipo": tipo, "region": reg, "lat": la, "lon": lo, "altitud": z,
                      "lat_celda": round(c["latitude"], 3), "lon_celda": round(c["longitude"], 3),
                      "iy": iy, "ix": ix, "altitud_dem_api": c["elevation"],
                      "altitud_celda": max(z_celda, 0.0), "celda_mar": z_celda < -100})
    df = pd.DataFrame(filas)
    df["dist_km"] = 111.2 * np.hypot(df["lat_celda"] - df["lat"],
                                     (df["lon_celda"] - df["lon"]) * np.cos(np.radians(df["lat"])))
    destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destino, index=False)
    return df


def _sistema_s3():
    import s3fs
    return s3fs.S3FileSystem(anon=True)


def altura_celdas(indices: list[tuple[int, int]]) -> list[float]:
    """Altitud media (m) de las celdas de ERA5, del archivo estático HSURF de Open-Meteo."""
    from omfiles import OmFileReader
    lector = OmFileReader.from_fsspec(_sistema_s3(), f"{config.S3_ERA5}/static/HSURF.om")
    return [float(lector[iy, ix]) for iy, ix in indices]


# ---------------------------------------------------------------------------
# ERA5 horario desde S3
# ---------------------------------------------------------------------------
def bloques(anio_inicio: int = config.ANIO_INICIO, anio_fin: int = config.ANIO_FIN) -> list[dict]:
    """Lista de archivos .om a leer: un year_YYYY.om por año hasta 2021 y los chunk_N.om después.

    Se piden 7 horas más al final: el último día local de Galápagos (UTC−6) acumula lluvia hasta las 06:00 UTC.
    """
    lista = [{"nombre": f"year_{a}", "inicio": pd.Timestamp(f"{a}-01-01")}
             for a in range(anio_inicio, min(anio_fin, config.ULTIMO_ANIO_ARCHIVO) + 1)]
    if anio_fin > config.ULTIMO_ANIO_ARCHIVO:
        desde = pd.Timestamp(f"{max(anio_inicio, config.ULTIMO_ANIO_ARCHIVO + 1)}-01-01")
        hasta = pd.Timestamp(f"{anio_fin + 1}-01-01 07:00")
        h0 = int((desde - EPOCA) / pd.Timedelta(hours=1))
        h1 = int((hasta - EPOCA) / pd.Timedelta(hours=1))
        for n in range(h0 // config.HORAS_POR_TROZO, h1 // config.HORAS_POR_TROZO + 1):
            lista.append({"nombre": f"chunk_{n}", "inicio": EPOCA + pd.Timedelta(hours=n * config.HORAS_POR_TROZO)})
    return lista


def _leer_bloque(variable: str, bloque: dict, celdas: pd.DataFrame, hilos: int = 8) -> pd.DataFrame:
    from omfiles import OmFileReader
    lector = OmFileReader.from_fsspec(_sistema_s3(), f"{config.S3_ERA5}/{variable}/{bloque['nombre']}.om")
    n_horas = lector.shape[-1]
    unicas = sorted(set(zip(celdas["iy"], celdas["ix"])))      # dos puntos pueden compartir celda
    with ThreadPoolExecutor(hilos) as ex:
        series = dict(zip(unicas, ex.map(lambda c: np.asarray(lector[c[0], c[1], :], dtype="float32"), unicas)))
    lector.close()
    datos = {p: series[(iy, ix)] for p, iy, ix in zip(celdas["punto"], celdas["iy"], celdas["ix"])}
    indice = pd.date_range(bloque["inicio"], periods=n_horas, freq="h", name="hora_utc")
    return pd.DataFrame(datos, index=indice)


def bloque_valido(ruta: Path, n_puntos: int) -> bool:
    """Un bloque en caché sirve si se puede leer, tiene todas las columnas y al menos 504 horas."""
    if not ruta.exists():
        return False
    try:
        df = pd.read_parquet(ruta)
    except Exception:  # noqa: BLE001 - archivo truncado por un corte de luz, por ejemplo
        return False
    return df.shape[1] == n_puntos and len(df) >= config.HORAS_POR_TROZO


def descargar_era5(celdas: pd.DataFrame | None = None, variables: list[str] | None = None,
                   carpeta: Path = config.ERA5_CRUDO, forzar: bool = False, archivos_en_paralelo: int = 3,
                   avisar=print) -> list[dict]:
    """Extrae de S3 la serie horaria de cada variable en cada punto. Un Parquet por variable y bloque.

    Se puede cortar y reanudar: los bloques ya guardados y legibles se saltan; los dañados se vuelven a bajar.
    """
    celdas = celdas_open_meteo() if celdas is None else celdas
    variables = variables or list(config.VARIABLES_S3)
    tareas = [(v, b) for v in variables for b in bloques()]
    pendientes = [(v, b) for v, b in tareas
                  if forzar or not bloque_valido(carpeta / v / f"{b['nombre']}.parquet", len(celdas))]
    avisar(f"ERA5: {len(tareas)} bloques, {len(tareas) - len(pendientes)} ya en caché, {len(pendientes)} por bajar")
    log: list[dict] = []

    def tarea(vb):
        v, b = vb
        t0 = time.perf_counter()
        df = _con_reintentos(_leer_bloque, v, b, celdas)
        destino = carpeta / v / f"{b['nombre']}.parquet"
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporal = destino.with_suffix(".tmp")      # escritura atómica: un corte no deja Parquet a medias
        df.to_parquet(temporal)
        temporal.replace(destino)
        return {"variable": v, "bloque": b["nombre"], "horas": len(df), "segundos": round(time.perf_counter() - t0, 1)}

    with ThreadPoolExecutor(archivos_en_paralelo) as ex:
        for i, fila in enumerate(ex.map(tarea, pendientes), 1):
            log.append(fila)
            if i % 20 == 0 or i == len(pendientes):
                avisar(f"  {i}/{len(pendientes)} · último: {fila['variable']} {fila['bloque']} ({fila['segundos']} s)")
    return log


# ---------------------------------------------------------------------------
# Muestra diaria de la API (verificación de la agregación propia)
# ---------------------------------------------------------------------------
VARIABLES_API = ["temperature_2m_max", "temperature_2m_min", "temperature_2m_mean", "precipitation_sum",
                 "relative_humidity_2m_mean", "wind_speed_10m_max", "shortwave_radiation_sum"]


def _misma_celda(ruta: Path, lat: float, lon: float) -> bool:
    d = json.loads(ruta.read_text(encoding="utf-8"))
    return abs(d["latitude"] - lat) < 0.01 and abs(d["longitude"] - lon) < 0.01


def descargar_muestra_api(anios: tuple[int, ...] = (2015, 2023), carpeta: Path = config.MUESTRA_API,
                          forzar: bool = False) -> pd.DataFrame:
    """Valores diarios de la API (``models=era5``) para las 22 ciudades. Peso ≈ 22 × 2 × 26 × 0,7 ≈ 800 llamadas.

    Con ``elevation=nan`` la API no corrige por altitud: así se compara exactamente con la celda cruda de S3.
    Pero sin altitud de referencia la API elige otra celda en 3 ciudades (Esmeraldas, Salinas, Ibarra); por eso se
    pide el centro de la misma celda de ``celdas_era5.csv`` con ``cell_selection=nearest``.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    celdas = pd.read_csv(config.CELDAS).set_index("punto")
    tablas = []
    for ciudad, (_, _, _, reg) in config.CIUDADES.items():
        la, lo = celdas.loc[ciudad, "lat_celda"], celdas.loc[ciudad, "lon_celda"]
        for anio in anios:
            destino = carpeta / f"{ciudad.replace(' ', '_')}_{anio}.json"
            if forzar or not destino.exists() or not _misma_celda(destino, la, lo):
                params = {"latitude": la, "longitude": lo, "start_date": f"{anio}-01-01",
                          "end_date": f"{anio}-12-31", "daily": ",".join(VARIABLES_API), "models": "era5",
                          "elevation": "nan", "cell_selection": "nearest",
                          "timezone": "Pacific/Galapagos" if reg == "Galápagos" else "America/Guayaquil"}
                destino.write_text(_get(config.URL_API_ARCHIVO, params).text, encoding="utf-8")
                time.sleep(PAUSA_API)
            d = json.loads(destino.read_text(encoding="utf-8"))["daily"]
            t = pd.DataFrame(d).rename(columns={"time": "fecha"})
            t["ciudad"] = ciudad
            tablas.append(t)
    df = pd.concat(tablas, ignore_index=True)
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


# ---------------------------------------------------------------------------
# ONI, estaciones GHCN-Daily y límites provinciales
# ---------------------------------------------------------------------------
def descargar_archivo(url: str, destino: Path, forzar: bool = False) -> Path:
    if destino.exists() and not forzar:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(_get(url).content)
    return destino


def descargar_oni(forzar: bool = False) -> Path:
    return descargar_archivo(config.URL_ONI, config.CRUDOS / "oni.data", forzar)


def descargar_nino12(forzar: bool = False) -> Path:
    return descargar_archivo(config.URL_NINO12, config.CRUDOS / "nino12.data", forzar)


def descargar_ghcn(forzar: bool = False) -> list[Path]:
    return [descargar_archivo(config.URL_GHCN.format(estacion=e), config.CRUDOS / "ghcn" / f"{e}.csv", forzar)
            for e in config.ESTACIONES]


def descargar_provincias(forzar: bool = False) -> Path:
    return descargar_archivo(config.URL_PROVINCIAS, config.GEOJSON_PROVINCIAS, forzar)


def leer_oni(ruta: Path, columna: str = "oni") -> pd.DataFrame:
    """Lee el formato de PSL: primera línea con años, luego ``año v1 … v12`` y -99.9 como faltante.

    Sirve para el ONI y para Niño 1+2 (``columna="nino12"``). Fases: ≥ +0,5 El Niño, ≤ −0,5 La Niña.
    """
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    filas = []
    for linea in lineas[1:]:
        partes = linea.split()
        if len(partes) != 13 or not partes[0].isdigit():
            continue
        anio = int(partes[0])
        for mes, valor in enumerate(partes[1:], 1):
            v = float(valor)
            filas.append({"fecha": pd.Timestamp(anio, mes, 1), columna: np.nan if v <= -99 else v})
    df = pd.DataFrame(filas).dropna().reset_index(drop=True)
    df["fase"] = np.select([df[columna] >= 0.5, df[columna] <= -0.5], ["El Niño", "La Niña"], "Neutral")
    return df


def leer_ghcn(rutas: list[Path]) -> pd.DataFrame:
    """GHCN-Daily (CSV de NCEI): TMAX/TMIN en °C y PRCP en mm. Se descartan los valores con marca de calidad."""
    tablas = []
    for ruta in rutas:
        d = pd.read_csv(ruta, low_memory=False)
        t = pd.DataFrame({"estacion": d["STATION"], "fecha": pd.to_datetime(d["DATE"])})
        for col, nombre in [("TMAX", "tmax"), ("TMIN", "tmin"), ("PRCP", "precip")]:
            if col in d:
                valor = pd.to_numeric(d[col], errors="coerce") / 10  # décimas de °C y de mm
                marca = d.get(f"{col}_ATTRIBUTES", pd.Series("", index=d.index)).fillna("").astype(str)
                calidad = marca.str.split(",").str[1].fillna("")    # segunda letra: control de calidad
                t[nombre] = valor.where(calidad.str.strip() == "")
            else:
                t[nombre] = np.nan
        tablas.append(t)
    return pd.concat(tablas, ignore_index=True)


def descargar_todo(forzar: bool = False, avisar=print) -> list[dict]:
    """Baja (o reutiliza) todas las fuentes y devuelve un log con tamaño y tiempo de cada una."""
    log = []
    t0 = time.perf_counter()
    celdas = celdas_open_meteo(forzar=forzar)
    log.append({"fuente": "API Open-Meteo: celdas ERA5", "archivo": config.CELDAS.name,
                "segundos": round(time.perf_counter() - t0, 1)})
    for nombre, tarea in [("ONI (NOAA PSL)", descargar_oni), ("Niño 1+2 (NOAA PSL)", descargar_nino12),
                          ("Provincias (geoBoundaries)", descargar_provincias)]:
        t0 = time.perf_counter()
        ruta = tarea(forzar)
        log.append({"fuente": nombre, "archivo": ruta.name, "segundos": round(time.perf_counter() - t0, 1)})
    t0 = time.perf_counter()
    descargar_ghcn(forzar)
    log.append({"fuente": "GHCN-Daily (8 estaciones)", "archivo": "ghcn/*.csv", "segundos": round(time.perf_counter() - t0, 1)})
    t0 = time.perf_counter()
    descargar_muestra_api(forzar=forzar)
    log.append({"fuente": "API Open-Meteo: muestra diaria", "archivo": "api_muestra/*.json",
                "segundos": round(time.perf_counter() - t0, 1)})
    t0 = time.perf_counter()
    bloques_bajados = descargar_era5(celdas, forzar=forzar, avisar=avisar)
    log.append({"fuente": "ERA5 horario (S3 Open-Meteo)", "archivo": f"era5/ ({len(bloques_bajados)} bloques nuevos)",
                "segundos": round(time.perf_counter() - t0, 1)})
    for fila in log:
        fila["fecha"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    return log
