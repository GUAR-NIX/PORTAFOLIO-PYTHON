"""Prueba de humo de la app con los catálogos procesados versionados."""
from pathlib import Path

import pytest

from sismos import config

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
HAY_DATOS = config.CATALOGO_ECUADOR.exists() and config.CATALOGO_CINTURON.exists()


@pytest.mark.skipif(not HAY_DATOS, reason="faltan los catálogos procesados (ejecuta el pipeline)")
def test_app_corre_sin_errores():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not app.exception
    assert len(app.metric) == 4
    assert app.metric[0].label == "Sismos"


@pytest.mark.skipif(not HAY_DATOS, reason="faltan los catálogos procesados (ejecuta el pipeline)")
def test_app_filtra_region_anios_y_magnitud():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP), default_timeout=120).run()
    total = app.metric[0].value
    app.selectbox(key="region").select("Japón").run()
    app.slider(key="anios").set_value((2000, 2020)).run()
    app.slider(key="magnitud").set_value((6.0, 9.0)).run()
    assert not app.exception
    assert app.metric[0].value != total
    assert int(app.metric[2].value) >= 1          # Tohoku 2011 y otros M≥7
