"""Sesión HTTP falsa que sirve respuestas grabadas de la API del USGS (las pruebas no usan internet)."""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest

GRABADAS = Path(__file__).parent / "grabadas"


class Respuesta:
    def __init__(self, status_code: int, text: str, headers: dict | None = None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class SesionGrabada:
    """Imita al servicio FDSN con una semana real grabada (16–23 de abril de 2016, Ecuador ampliado).

    Filtra el CSV grabado por starttime/endtime como lo haría la API y, si el resultado supera
    ``limite_servidor``, responde el mismo error 400 que devolvió la API real (también grabado)."""

    def __init__(self, limite_servidor: int = 20_000, fallos: list[int] | None = None):
        self.texto = (GRABADAS / "ecuador_2016-04-16_2016-04-23.csv").read_text(encoding="utf-8")
        self.tabla = pd.read_csv(io.StringIO(self.texto))
        self.tabla["_t"] = pd.to_datetime(self.tabla["time"], utc=True, format="ISO8601")
        self.error_400 = (GRABADAS / "error_limite_400.txt").read_text(encoding="utf-8")
        self.limite_servidor = limite_servidor
        self.fallos = list(fallos or [])     # códigos HTTP a devolver antes de responder bien
        self.llamadas: list[dict] = []
        self.headers: dict = {}

    def get(self, url, params=None, timeout=None):
        self.llamadas.append(dict(params))
        if self.fallos:
            return Respuesta(self.fallos.pop(0), "Service Unavailable", {"Retry-After": "0"})
        t0 = pd.Timestamp(params["starttime"], tz="UTC")
        t1 = pd.Timestamp(params["endtime"], tz="UTC")
        sel = self.tabla[(self.tabla["_t"] >= t0) & (self.tabla["_t"] < t1)]
        if len(sel) > self.limite_servidor:
            return Respuesta(400, self.error_400)
        sel = sel.drop(columns="_t").head(params.get("limit", 10**9))
        return Respuesta(200, sel.to_csv(index=False))


@pytest.fixture
def sesion_grabada():
    return SesionGrabada()
