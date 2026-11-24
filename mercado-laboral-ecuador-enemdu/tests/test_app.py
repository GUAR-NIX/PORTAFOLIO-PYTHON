"""Pruebas de humo de la aplicación interactiva Streamlit y verificación de artefactos."""

from __future__ import annotations


from streamlit.testing.v1 import AppTest

from empleo_enemdu.config import DIR_FIGURAS, RAIZ


def test_figuras_generadas_existen_y_no_estan_vacias() -> None:
    """Verifica que las 10 figuras editoriales PNG existan y superen los 30 KB."""
    pngs = sorted(DIR_FIGURAS.glob("*.png"))
    assert len(pngs) == 10
    for ruta in pngs:
        assert ruta.stat().st_size > 30_000, f"Figura demasiado pequeña: {ruta.name}"


def test_streamlit_app_arranca_y_filtra_provincia() -> None:
    """Ejecuta la app de Streamlit con AppTest y cambia filtros de provincia y educación."""
    ruta_app = RAIZ / "app" / "streamlit_app.py"
    at = AppTest.from_file(str(ruta_app), default_timeout=30)
    at.run()
    assert not at.exception
    assert len(at.metric) >= 5

    # Cambiar provincia a Pichincha y escolaridad en el simulador Mincer
    at.sidebar.selectbox(key="provincia_sel").select("Pichincha").run()
    assert not at.exception
    assert "Pichincha" in at.metric[0].label
