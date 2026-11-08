"""Ejecuta la app de Streamlit de verdad (AppTest) sobre la muestra versionada."""
from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def test_app_se_ejecuta_con_la_muestra(monkeypatch: pytest.MonkeyPatch) -> None:
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("DELITOS_FUENTE", "muestra")
    app = AppTest.from_file(str(RAIZ / "app" / "streamlit_app.py"), default_timeout=120)
    app.run()
    assert not app.exception, app.exception
    assert app.title[0].value.startswith("Delitos en Chicago")
    etiquetas = [m.label for m in app.metric]
    assert "Total Delitos Filtrados" in etiquetas
    # Las categorías del filtro llegan armonizadas: no aparece la etiqueta antigua
    opciones = app.sidebar.multiselect[0].options
    assert "CRIM SEXUAL ASSAULT" not in opciones

    # Al filtrar por un tipo, el total cambia y la app sigue sin errores
    total_inicial = app.metric[0].value
    app.sidebar.multiselect[0].set_value(["THEFT"]).run()
    assert not app.exception
    assert app.metric[0].value != total_inicial
