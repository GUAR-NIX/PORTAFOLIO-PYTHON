"""La app de Streamlit arranca con los archivos versionados y responde a la selección."""

from __future__ import annotations

import pandas as pd
from streamlit.testing.v1 import AppTest

from nyc311.config import DIR_TABLAS, RAIZ

APP = str(RAIZ / "app" / "streamlit_app.py")


def test_app_arranca_y_muestra_curva_y_tabla() -> None:
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    assert at.selectbox[0].value == "Todos los tipos"
    assert len(at.dataframe) == 1
    tabla = at.dataframe[0].value
    assert set(tabla["Borough"]) == {"Toda la ciudad", "Bronx"}


def test_app_filtra_por_tipo_y_borough() -> None:
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.selectbox[0].set_value("HEAT/HOT WATER").run()
    at.multiselect[0].set_value(["QUEENS", "MANHATTAN"]).run()
    assert not at.exception
    tabla = at.dataframe[0].value
    assert set(tabla["Borough"]) == {"Queens", "Manhattan"}
    esperado = pd.read_csv(DIR_TABLAS / "resumen_app.csv")
    fila = esperado.query("tipo_queja == 'HEAT/HOT WATER' and borough == 'QUEENS'").iloc[0]
    assert int(tabla.loc[tabla["Borough"].eq("Queens"), "Solicitudes"].iat[0]) == fila["n"]


def test_curvas_de_la_app_son_validas() -> None:
    c = pd.read_parquet(DIR_TABLAS / "curvas_km.parquet")
    app = c.loc[c["dimension"].eq("tipo_borough")]
    assert app.groupby(["grupo", "borough"]).size().gt(100).all()
    for _, g in app.groupby(["grupo", "borough"]):
        s = g.sort_values("tiempo")["supervivencia"].to_numpy()
        assert (s[1:] <= s[:-1] + 1e-12).all()  # no creciente
