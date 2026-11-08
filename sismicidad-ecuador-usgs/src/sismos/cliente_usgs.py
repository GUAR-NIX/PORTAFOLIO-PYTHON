"""
Cliente del FDSN Event Web Service del USGS con paginación, reintentos, pausas y caché.

* La API devuelve como máximo 20 000 eventos por consulta: se pide **un año por consulta** y, si un año
  supera el límite (la API responde 400 o llega una página llena), el intervalo se parte en dos mitades
  hasta que cada trozo quepa.
* Cada respuesta se guarda tal cual (CSV) en ``data/raw/usgs/<etiqueta>/``. Si el archivo ya existe no
  se vuelve a pedir: la descarga se puede cortar (apagón, internet caído) y retomar sin repetir nada.
  La escritura es atómica (archivo temporal + renombrar) para que un corte no deje un CSV a medias.
* Entre llamadas reales hay una pausa fija; con 429/503 se respeta ``Retry-After`` o se espera más.
* La sesión HTTP se inyecta: las pruebas usan respuestas grabadas, sin internet.
"""
from __future__ import annotations

import io
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

from . import config

FORMATO_FECHA = "%Y-%m-%dT%H:%M:%S"


class LimiteExcedido(Exception):
    """La consulta pide más eventos de los que la API entrega de una vez."""


@dataclass
class ClienteUSGS:
    cache: Path = config.CACHE_USGS
    sesion: requests.Session | None = None
    pausa: float = config.PAUSA_SEGUNDOS
    limite: int = config.LIMITE_USGS
    reintentos: int = config.REINTENTOS
    tiempo_espera: int = config.TIEMPO_ESPERA
    url: str = config.URL_USGS
    llamadas_red: int = 0
    log: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cache = Path(self.cache)
        if self.sesion is None:
            self.sesion = requests.Session()
            self.sesion.headers["User-Agent"] = "portafolio-sismos-ecuador (estudio académico)"

    # ---- una consulta -------------------------------------------------------------------
    def parametros(self, inicio: datetime, fin: datetime, region: dict | None, mag_min: float) -> dict:
        p = {"format": "csv", "starttime": inicio.strftime(FORMATO_FECHA),
             "endtime": fin.strftime(FORMATO_FECHA), "minmagnitude": mag_min,
             "orderby": "time-asc", "limit": self.limite}
        p.update(region or {})
        return p

    def _pedir(self, params: dict) -> str:
        """GET con reintentos. Devuelve el texto CSV ('' si no hay eventos)."""
        ultimo: Exception | None = None
        for intento in range(self.reintentos):
            if self.llamadas_red and self.pausa:
                time.sleep(self.pausa)
            self.llamadas_red += 1
            try:
                r = self.sesion.get(self.url, params=params, timeout=self.tiempo_espera)
            except requests.RequestException as e:          # timeout o conexión cortada
                ultimo = e
                time.sleep(min(2 ** intento, 60) * (self.pausa > 0))
                continue
            if r.status_code == 204:                          # sin eventos en el intervalo
                return ""
            if r.status_code == 200:
                return r.text
            if r.status_code == 400 and "limit" in r.text.lower():
                raise LimiteExcedido(r.text[:200])
            if r.status_code in (429, 500, 502, 503, 504):
                espera = float(r.headers.get("Retry-After", 2 ** (intento + 2)))
                ultimo = RuntimeError(f"HTTP {r.status_code}")
                time.sleep(min(espera, 120) * (self.pausa > 0))
                continue
            raise RuntimeError(f"HTTP {r.status_code} inesperado: {r.text[:200]}")
        raise RuntimeError(f"La API no respondió tras {self.reintentos} intentos: {ultimo}")

    def consultar(self, etiqueta: str, inicio: datetime, fin: datetime, region: dict | None,
                  mag_min: float) -> pd.DataFrame:
        """Eventos en [inicio, fin), partiendo el intervalo si supera el límite de la API."""
        carpeta = self.cache / etiqueta
        archivo = carpeta / f"{inicio:%Y%m%dT%H%M%S}_{fin:%Y%m%dT%H%M%S}.csv"
        if archivo.exists():
            self.log.append({"etiqueta": etiqueta, "inicio": inicio, "fin": fin, "origen": "cache"})
            return _leer_csv(archivo.read_text(encoding="utf-8"))

        try:
            texto = self._pedir(self.parametros(inicio, fin, region, mag_min))
            tabla = _leer_csv(texto)
            if len(tabla) >= self.limite:
                raise LimiteExcedido(f"{len(tabla)} filas = página llena")
        except LimiteExcedido:
            if fin - inicio <= timedelta(hours=1):
                raise
            medio = inicio + (fin - inicio) / 2
            medio = medio.replace(microsecond=0)
            self.log.append({"etiqueta": etiqueta, "inicio": inicio, "fin": fin, "origen": "partido"})
            return pd.concat([self.consultar(etiqueta, inicio, medio, region, mag_min),
                              self.consultar(etiqueta, medio, fin, region, mag_min)],
                             ignore_index=True)

        carpeta.mkdir(parents=True, exist_ok=True)
        temporal = archivo.with_suffix(".tmp")
        temporal.write_text(texto, encoding="utf-8")
        temporal.replace(archivo)
        self.log.append({"etiqueta": etiqueta, "inicio": inicio, "fin": fin, "origen": "red",
                         "eventos": len(tabla)})
        return tabla

    # ---- varios años ------------------------------------------------------------------------
    def descargar_anios(self, etiqueta: str, anio_inicio: int, anio_fin: int, region: dict | None,
                        mag_min: float, paso_anios: int = 1, avisar=print) -> pd.DataFrame:
        """Una consulta por bloque de ``paso_anios`` años; une todo y quita repetidos por ``id``."""
        partes = []
        for anio in range(anio_inicio, anio_fin + 1, paso_anios):
            fin_bloque = min(anio + paso_anios, anio_fin + 1)
            antes = self.llamadas_red
            tabla = self.consultar(etiqueta, datetime(anio, 1, 1), datetime(fin_bloque, 1, 1),
                                   region, mag_min)
            if avisar and self.llamadas_red > antes:
                avisar(f"  {etiqueta} {anio}–{fin_bloque - 1}: {len(tabla):,} eventos (red)")
            partes.append(tabla)
        partes = [p for p in partes if len(p)]
        if not partes:
            return _leer_csv("")
        unido = pd.concat(partes, ignore_index=True)
        # Los extremos de los intervalos son inclusivos en la API: un evento justo en la frontera
        # puede venir dos veces
        return unido.drop_duplicates("id").reset_index(drop=True)


COLUMNAS = ["time", "latitude", "longitude", "depth", "mag", "magType", "nst", "gap", "dmin", "rms",
            "net", "id", "updated", "place", "type", "horizontalError", "depthError", "magError",
            "magNst", "status", "locationSource", "magSource"]


def _leer_csv(texto: str) -> pd.DataFrame:
    if not texto.strip():
        return pd.DataFrame(columns=COLUMNAS)
    return pd.read_csv(io.StringIO(texto), dtype={"id": str, "magType": str, "net": str})
