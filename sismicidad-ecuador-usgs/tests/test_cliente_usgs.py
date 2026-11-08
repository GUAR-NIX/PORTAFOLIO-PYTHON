"""Paginación, caché y reintentos del cliente, con respuestas grabadas de la API real."""
from datetime import datetime

import pytest

from sismos.cliente_usgs import ClienteUSGS, LimiteExcedido
from conftest import GRABADAS, Respuesta, SesionGrabada

INICIO, FIN = datetime(2016, 4, 16), datetime(2016, 4, 23)
EVENTOS_SEMANA = 67      # filas del CSV grabado


def cliente(tmp_path, sesion, **kw):
    return ClienteUSGS(cache=tmp_path, sesion=sesion, pausa=0, **kw)


def test_una_consulta_trae_todo_y_guarda_cache(tmp_path, sesion_grabada):
    c = cliente(tmp_path, sesion_grabada)
    tabla = c.consultar("prueba", INICIO, FIN, None, 2.5)
    assert len(tabla) == EVENTOS_SEMANA
    assert tabla["id"].is_unique
    assert len(list((tmp_path / "prueba").glob("*.csv"))) == 1
    assert sesion_grabada.llamadas[0]["orderby"] == "time-asc"


def test_la_segunda_vez_sale_de_cache_sin_red(tmp_path, sesion_grabada):
    c = cliente(tmp_path, sesion_grabada)
    c.consultar("prueba", INICIO, FIN, None, 2.5)
    llamadas = len(sesion_grabada.llamadas)
    otra = cliente(tmp_path, SesionGrabada())          # sesión nueva: si pidiera algo, se notaría
    tabla = otra.consultar("prueba", INICIO, FIN, None, 2.5)
    assert len(tabla) == EVENTOS_SEMANA
    assert otra.llamadas_red == 0 and len(sesion_grabada.llamadas) == llamadas


def test_error_400_por_limite_parte_el_intervalo(tmp_path):
    """El servidor rechaza consultas con más de 20 eventos (como hace la API real con más de 20 000)."""
    sesion = SesionGrabada(limite_servidor=20)
    c = cliente(tmp_path, sesion)
    tabla = c.consultar("prueba", INICIO, FIN, None, 2.5)
    assert len(tabla) == EVENTOS_SEMANA                 # no se pierde ni se repite ningún evento
    assert tabla["id"].is_unique
    assert any(r["origen"] == "partido" for r in c.log)
    assert len(list((tmp_path / "prueba").glob("*.csv"))) >= 4


def test_pagina_llena_tambien_se_parte(tmp_path):
    """Si la API trunca en ``limit`` sin dar error, una página llena se trata como límite excedido."""
    sesion = SesionGrabada()
    c = cliente(tmp_path, sesion, limite=30)
    tabla = c.consultar("prueba", INICIO, FIN, None, 2.5)
    assert len(tabla) == EVENTOS_SEMANA and tabla["id"].is_unique


def test_reintenta_ante_503_y_429(tmp_path):
    sesion = SesionGrabada(fallos=[503, 429])
    c = cliente(tmp_path, sesion)
    tabla = c.consultar("prueba", INICIO, FIN, None, 2.5)
    assert len(tabla) == EVENTOS_SEMANA
    assert len(sesion.llamadas) == 3


def test_se_rinde_tras_los_reintentos(tmp_path):
    c = cliente(tmp_path, SesionGrabada(fallos=[503] * 10), reintentos=3)
    with pytest.raises(RuntimeError, match="3 intentos"):
        c.consultar("prueba", INICIO, FIN, None, 2.5)
    assert not list(tmp_path.rglob("*.csv"))            # nada a medias en caché


def test_respuesta_vacia_grabada(tmp_path):
    vacio = (GRABADAS / "vacio_204.txt").read_text(encoding="utf-8")

    class Vacia:
        headers: dict = {}

        def get(self, url, params=None, timeout=None):
            return Respuesta(200, vacio)

    tabla = cliente(tmp_path, Vacia()).consultar("prueba", INICIO, FIN, None, 2.5)
    assert len(tabla) == 0 and "mag" in tabla.columns


def test_limite_en_intervalo_minimo_no_se_parte_para_siempre(tmp_path):
    c = cliente(tmp_path, SesionGrabada(limite_servidor=0))
    with pytest.raises(LimiteExcedido):
        c.consultar("prueba", datetime(2016, 4, 17), datetime(2016, 4, 17, 1), None, 2.5)


def test_descargar_anios_une_y_quita_repetidos(tmp_path, sesion_grabada):
    c = cliente(tmp_path, sesion_grabada)
    tabla = c.descargar_anios("prueba", 2015, 2017, {"minlatitude": -6}, 2.5, avisar=None)
    assert len(sesion_grabada.llamadas) == 3            # una consulta por año
    assert sesion_grabada.llamadas[0]["minlatitude"] == -6
    assert sesion_grabada.llamadas[1]["starttime"] == "2016-01-01T00:00:00"
    assert len(tabla) == EVENTOS_SEMANA
