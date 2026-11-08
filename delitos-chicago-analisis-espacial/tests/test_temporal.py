"""Pruebas del análisis temporal: STL, serie interrumpida, cambio por tipo y patrón horario."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from delitos_chicago.temporal import (
    cambio_porcentual_por_tipo,
    delitos_por_anio_tipo,
    descomposicion_stl,
    mapa_calor_hora_dia,
    patron_horario,
    serie_interrumpida,
)


def _serie_mensual(efecto: float = 0.0, semilla: int = 0) -> pd.Series:
    """Serie con tendencia, estacionalidad y ruido; desde 2020-03 se multiplica por (1 + efecto)."""
    rng = np.random.default_rng(semilla)
    fechas = pd.date_range("2012-01-01", "2021-12-01", freq="MS")
    t = np.arange(len(fechas))
    media_diaria = 700 * np.exp(-0.002 * t + 0.15 * np.sin(2 * np.pi * (fechas.month - 4) / 12) + rng.normal(0, 0.02, len(t)))
    valores = media_diaria * fechas.days_in_month
    valores = np.where(fechas >= "2020-03-01", valores * (1 + efecto), valores)
    return pd.Series(valores.round(), index=fechas)


def test_serie_interrumpida_recupera_el_efecto() -> None:
    res = serie_interrumpida(_serie_mensual(efecto=-0.30))["resumen"]
    assert res["cambio_inf_pct"] <= -30 <= res["cambio_sup_pct"]
    assert abs(res["cambio_pct"] + 30) < 3
    assert res["meses_pre"] == 62 and res["meses_evaluados"] == 22


def test_serie_interrumpida_sin_efecto_cubre_cero() -> None:
    res = serie_interrumpida(_serie_mensual(efecto=0.0, semilla=3))
    assert res["resumen"]["cambio_inf_pct"] < 0 < res["resumen"]["cambio_sup_pct"]
    assert res["resumen"]["meses_fuera_intervalo"] <= 3  # intervalo del 95 % sobre 22 meses


def test_serie_interrumpida_no_usa_datos_posteriores_para_ajustar() -> None:
    """El contrafactual no cambia si se alteran los datos después de la intervención."""
    serie = _serie_mensual()
    alterada = serie.copy()
    alterada[alterada.index >= "2020-03-01"] *= 5
    a = serie_interrumpida(serie)["tabla"]["contrafactual"]
    b = serie_interrumpida(alterada)["tabla"]["contrafactual"]
    pd.testing.assert_series_equal(a, b)


def test_descomposicion_stl_suma_y_estacionalidad() -> None:
    fechas = pd.date_range("2015-01-01", "2020-12-31", freq="D")
    rng = np.random.default_rng(0)
    pesos = 1 + 0.5 * (fechas.month == 7) - 0.3 * (fechas.month == 2)  # más delitos en julio, menos en febrero
    repeticiones = rng.poisson(20 * pesos)
    df = pd.DataFrame({"fecha": np.repeat(fechas, repeticiones), "tipo_primario": "THEFT"})
    df.loc[::10, "tipo_primario"] = "BATTERY"
    stl = descomposicion_stl(df, "THEFT", hasta="2020-06-01")
    assert stl["serie"].index.max() == pd.Timestamp("2020-06-01")
    assert stl["serie"].sum() == (df["tipo_primario"] == "THEFT").sum() - (df.query("tipo_primario == 'THEFT'")["fecha"] >= "2020-07-01").sum()
    np.testing.assert_allclose(stl["tendencia"] + stl["estacional"] + stl["residuo"], stl["serie"])
    por_mes = stl["estacional"].groupby(stl["estacional"].index.month).mean()
    assert por_mes.idxmax() == 7 and por_mes.idxmin() == 2


def test_cambio_porcentual_sin_division_por_cero(df_delitos_sinteticos: pd.DataFrame) -> None:
    df = pd.DataFrame({
        "anio": [2019] * 3 + [2024] * 5,
        "tipo_primario": ["A", "A", "B", "A", "B", "B", "B", "NUEVO"],
    })
    cambio = cambio_porcentual_por_tipo(df, 2019, 2024).set_index("tipo_primario")
    assert cambio.loc["A", "cambio_pct"] == -50.0
    assert cambio.loc["B", "cambio_pct"] == 200.0
    assert pd.isna(cambio.loc["NUEVO", "cambio_pct"])  # no existía en 2019
    with pytest.raises(ValueError):
        cambio_porcentual_por_tipo(df_delitos_sinteticos, 2019, 2024)  # la fixture solo tiene 2020


def test_patron_horario_excluye_medianoche() -> None:
    horas = [0] * 500 + [19] * 100 + [20] * 100 + [21] * 90 + [18] * 80 + [5] * 1 + [3] * 30
    df = pd.DataFrame({"fecha": pd.Timestamp("2024-01-05") + pd.to_timedelta(horas, unit="h")})
    p = patron_horario(df)
    assert (p["franja_pico_inicio"], p["franja_pico_fin"]) == (18, 22)
    assert p["pct_medianoche"] == round(500 / len(horas) * 100, 1)
    assert p["hora_minima"] in {h for h in range(24) if h not in (0, 3, 5, 18, 19, 20, 21)}


def test_tablas_hora_dia_y_anio_tipo(df_delitos_sinteticos: pd.DataFrame) -> None:
    tabla = mapa_calor_hora_dia(df_delitos_sinteticos)
    assert tabla.shape == (7, 24) and tabla.values.sum() == len(df_delitos_sinteticos)
    assert delitos_por_anio_tipo(df_delitos_sinteticos)["conteo"].sum() == len(df_delitos_sinteticos)
