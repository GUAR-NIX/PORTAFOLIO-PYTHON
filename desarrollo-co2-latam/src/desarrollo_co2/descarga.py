"""
Descarga con caché local de las dos fuentes.

* Banco Mundial: API v2 pública (sin clave). Un archivo JSON por indicador en data/raw/.
* Our World in Data: el CSV completo de emisiones (≈14 MB) en data/raw/.

Si el archivo ya está en caché no se vuelve a descargar (``forzar=True`` lo renueva).
La API del Banco Mundial a veces tarda o corta la conexión: hay reintentos con espera creciente.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import config

TIEMPO_ESPERA = 60   # segundos por petición
REINTENTOS = 4


def _get(url: str, params: dict | None = None) -> requests.Response:
    ultimo_error: Exception | None = None
    for intento in range(REINTENTOS):
        try:
            r = requests.get(url, params=params, timeout=TIEMPO_ESPERA)
            r.raise_for_status()
            return r
        except requests.RequestException as e:  # timeout, 5xx, conexión cortada
            ultimo_error = e
            time.sleep(2 ** intento)
    raise RuntimeError(f"No se pudo descargar {url} tras {REINTENTOS} intentos: {ultimo_error}")


def url_indicador(codigo: str, paises: list[str], anio_inicio: int, anio_fin: int) -> tuple[str, dict]:
    """URL y parámetros de la API v2 para varios países y un indicador."""
    url = f"{config.URL_BANCO_MUNDIAL}/country/{';'.join(paises)}/indicator/{codigo}"
    params = {"format": "json", "date": f"{anio_inicio}:{anio_fin}", "per_page": 5000}
    return url, params


def descargar_indicador_bm(codigo: str, paises: list[str] | None = None, carpeta: Path = config.CRUDOS,
                           forzar: bool = False) -> Path:
    """Baja un indicador del Banco Mundial para todos los países y lo guarda tal cual (JSON)."""
    paises = paises or list(config.PAISES)
    destino = carpeta / f"bm_{codigo}.json"
    if destino.exists() and not forzar:
        return destino
    carpeta.mkdir(parents=True, exist_ok=True)
    url, params = url_indicador(codigo, paises, config.ANIO_INICIO, config.ANIO_FIN)
    registros: list[dict] = []
    pagina, paginas = 1, 1
    while pagina <= paginas:
        cuerpo = _get(url, {**params, "page": pagina}).json()
        if not isinstance(cuerpo, list) or len(cuerpo) < 2:
            # La API responde [{"message": ...}] cuando el indicador no existe o fue archivado
            raise ValueError(f"Respuesta inesperada para {codigo}: {str(cuerpo)[:200]}")
        paginas = int(cuerpo[0]["pages"])
        registros.extend(cuerpo[1] or [])
        pagina += 1
    destino.write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")
    return destino


def descargar_owid(carpeta: Path = config.CRUDOS, forzar: bool = False) -> Path:
    destino = carpeta / "owid-co2-data.csv"
    if destino.exists() and not forzar:
        return destino
    carpeta.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(_get(config.URL_OWID).content)
    return destino


def descargar_todo(forzar: bool = False, carpeta: Path = config.CRUDOS) -> list[dict]:
    """Baja (o reutiliza) todas las fuentes y devuelve un log con tamaño y fecha de cada archivo."""
    log = []
    tareas = [(f"Banco Mundial {c}", lambda c=c: descargar_indicador_bm(c, carpeta=carpeta, forzar=forzar))
              for c in config.INDICADORES_BM]
    tareas.append(("Our World in Data CO2", lambda: descargar_owid(carpeta=carpeta, forzar=forzar)))
    for nombre, tarea in tareas:
        t0 = time.perf_counter()
        ruta = tarea()
        log.append({
            "fuente": nombre, "archivo": ruta.name, "kb": round(ruta.stat().st_size / 1024, 1),
            "modificado": datetime.fromtimestamp(ruta.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
            "segundos": round(time.perf_counter() - t0, 2),
        })
    return log
