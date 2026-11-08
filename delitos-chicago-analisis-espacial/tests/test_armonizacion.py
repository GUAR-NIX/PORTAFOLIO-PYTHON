"""Pruebas de la detección y aplicación de renombres de categorías."""
from __future__ import annotations

import duckdb
import pandas as pd

from delitos_chicago.armonizacion import (
    armonizar_tipos,
    comparar_antes_despues,
    detectar_renombres,
    expresion_sql,
    mapa_renombres,
)


def _conteos() -> pd.DataFrame:
    """Serie sintética: 'VIEJO' pasa a llamarse 'NUEVO' en 2011 con los mismos códigos IUCR."""
    filas = []
    for anio in range(2001, 2021):
        if anio <= 2010:
            filas += [(anio, "VIEJO", "0261", 90), (anio, "VIEJO", "0262", 10), (anio, "NUEVO", "0261", 2)]
        else:
            filas += [(anio, "NUEVO", "0261", 90), (anio, "NUEVO", "0262", 10)]
        if anio <= 2005:  # desaparece y sus códigos no vuelven a aparecer
            filas.append((anio, "EXTINTO", "9999", 5))
        if anio <= 2012:  # desaparece, pero solo una parte menor de sus registros pasa a otra categoría
            filas += [(anio, "PARCIAL", "1000", 3), (anio, "PARCIAL", "1001", 7)]
        else:
            filas.append((anio, "OTRA", "1000", 3))
        filas.append((anio, "ESTABLE", "0820", 50))
    return pd.DataFrame(filas, columns=["anio", "tipo_primario", "codigo_iucr", "conteo"])


def test_detecta_renombre_por_codigos_iucr() -> None:
    tabla = detectar_renombres(_conteos(), anio_ultimo=2020).set_index("tipo_original")
    assert tabla.loc["VIEJO", "tipo_armonizado"] == "NUEVO"
    assert tabla.loc["VIEJO", "cobertura_iucr_pct"] == 100.0
    assert tabla.loc["VIEJO", "ultimo_anio_original"] == 2010
    # Sin sucesor y con cobertura insuficiente (30 %) no se armonizan
    assert tabla.loc["EXTINTO", "tipo_armonizado"] == "EXTINTO"
    assert tabla.loc["PARCIAL", "tipo_armonizado"] == "PARCIAL"
    assert tabla.loc["PARCIAL", "cobertura_iucr_pct"] == 30.0
    assert "ESTABLE" not in tabla.index and "NUEVO" not in tabla.index
    assert mapa_renombres(tabla.reset_index()) == {"VIEJO": "NUEVO"}


def test_armonizar_en_pandas_y_sql_coinciden() -> None:
    mapa = {"VIEJO": "NUEVO", "O'HARE": "AEROPUERTO"}
    serie = pd.Series(["VIEJO", "NUEVO", "ESTABLE", "O'HARE"])
    esperado = ["NUEVO", "NUEVO", "ESTABLE", "AEROPUERTO"]
    assert armonizar_tipos(serie, mapa).tolist() == esperado
    df = pd.DataFrame({"tipo_primario": serie})
    sql = duckdb.sql(f"SELECT {expresion_sql(mapa)} AS t FROM df").df()["t"].tolist()
    assert sql == esperado
    assert expresion_sql({}) == "tipo_primario"


def test_comparacion_antes_despues_reproduce_el_caso() -> None:
    """Con la etiqueta nueva sola el cambio es enorme; sumando ambas etiquetas es 0 %."""
    conteos = _conteos()
    caso = comparar_antes_despues(conteos, {"VIEJO": "NUEVO"}, 2010, 2011).set_index("categoria")
    assert caso.loc["VIEJO", "conteo_2011"] == 0
    assert caso.loc["NUEVO", "cambio_pct"] == round((100 - 2) / 2 * 100, 1)
    assert caso.loc["NUEVO (armonizada)", "conteo_2010"] == 102
    assert caso.loc["NUEVO (armonizada)", "cambio_pct"] == round((100 - 102) / 102 * 100, 1)
