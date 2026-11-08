"""Prueba de humo de la app: se ejecuta completa sin errores con el panel versionado."""
from pathlib import Path

import pytest

from desarrollo_co2 import config

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


@pytest.mark.skipif(not config.PANEL.exists(), reason="falta el panel (ejecuta el pipeline)")
def test_app_corre_sin_errores():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP), default_timeout=90).run()
    assert not app.exception
    assert len(app.metric) == 4
    assert any("Ecuador" in str(m.label) for m in app.metric)


@pytest.mark.skipif(not config.PANEL.exists(), reason="falta el panel (ejecuta el pipeline)")
def test_app_cambia_de_pais_y_periodo():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP), default_timeout=90).run()
    app.selectbox(key="pais").select("Chile").run()
    app.slider(key="periodo").set_value((2010, 2020)).run()
    assert not app.exception
    assert any("Chile" in str(m.label) for m in app.metric)
