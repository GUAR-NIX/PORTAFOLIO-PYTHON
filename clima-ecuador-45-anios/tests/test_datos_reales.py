"""Controles sobre las tablas reales que produce el pipeline (se saltan si no existen)."""
import json

import numpy as np
import pandas as pd
import pytest

from clima_ecuador import config

FALTAN = not (config.DIARIO.exists() and config.RESULTADOS.exists())
pytestmark = pytest.mark.skipif(FALTAN, reason="faltan las tablas procesadas (ejecuta el pipeline)")


@pytest.fixture(scope="module")
def diario():
    return pd.read_parquet(config.DIARIO)


@pytest.fixture(scope="module")
def resultados():
    return json.loads(config.RESULTADOS.read_text(encoding="utf-8"))


def test_todas_las_ciudades_y_dias(diario):
    dias = (pd.Timestamp(f"{config.ANIO_FIN}-12-31") - pd.Timestamp(f"{config.ANIO_INICIO}-01-01")).days + 1
    conteo = diario.groupby("punto").size()
    assert set(config.CIUDADES) <= set(conteo.index)
    assert (conteo == dias).all()
    assert not diario.duplicated(["punto", "fecha"]).any()


def test_rangos_plausibles(diario):
    ciudades = diario[diario["punto"].isin(config.CIUDADES)]
    medias = ciudades.groupby("punto")["tmed"].mean()
    assert medias["Guayaquil"] > 24 and medias["Quito"] < 16   # la altitud manda
    assert (ciudades["tmin"] <= ciudades["tmax"]).all()
    assert ciudades["precip"].min() >= 0


def test_controles_de_calidad(resultados):
    c = resultados["calidad"]
    assert c["saltos"] == 0 and c["duplicadas"] == 0 and c["fuera_de_rango"] == 0
    assert c["pct_completo_min"] == pytest.approx(100)
    # el pico de radiación debe caer cerca del mediodía local (11–13 h)
    assert all(11 <= h <= 13 for h in c["hora_pico_radiacion"])


def test_agregacion_igual_a_la_api(resultados):
    api = resultados["api_vs_propio"]
    assert api["tmax_celda"]["correlacion"] > 0.99
    assert api["precip"]["correlacion"] > 0.99
    assert abs(api["tmax_celda"]["dif_media"]) < 0.2


def test_resultados_tienen_tendencias(resultados):
    assert {"tmed", "tmax", "tmin"} <= set(resultados["nacional"])
    assert np.isfinite(resultados["nacional"]["tmed"]["pendiente_decada"])
    assert len(resultados["validacion"]) >= 5
