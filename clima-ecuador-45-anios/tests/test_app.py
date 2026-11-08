"""Pruebas de humo de la app: se ejecuta completa sin errores con las tablas versionadas."""
from pathlib import Path

import pytest

from clima_ecuador import config

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"
FALTAN = not (config.MENSUAL.exists() and config.ANUAL.exists())


@pytest.mark.skipif(FALTAN, reason="faltan las tablas procesadas (ejecuta el pipeline)")
def test_app_corre_sin_errores():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP), default_timeout=120).run()
    assert not app.exception
    assert len(app.metric) == 4
    assert any("Quito" in str(m.label) for m in app.metric)


@pytest.mark.skipif(FALTAN, reason="faltan las tablas procesadas (ejecuta el pipeline)")
def test_app_cambia_ciudad_variable_y_periodo():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP), default_timeout=120).run()
    app.selectbox(key="ciudad").select("Puerto Ayora").run()
    app.selectbox(key="variable").select("precip").run()
    app.slider(key="periodo").set_value((1990, 2024)).run()
    assert not app.exception
    assert any("Puerto Ayora" in str(m.label) for m in app.metric)
    assert any("mm" in str(m.value) for m in app.metric)
