"""Pruebas del pronóstico: ausencia de fuga, mes incompleto, origen móvil e intervalos."""
from __future__ import annotations

import numpy as np
import pandas as pd

from delitos_chicago.pronostico import (
    backtesting_origen_movil,
    construir_caracteristicas_tiempo,
    evaluar_metricas,
    origenes_trimestrales,
    preparar_series_mensuales_distrito,
    ultimo_mes_completo,
)


def _serie(semilla: int = 0, meses: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    fechas = pd.date_range("2015-01-01", periods=meses, freq="MS")
    filas = []
    for distrito, nivel in [(1, 400), (2, 900), (3, 650)]:
        estacional = 1 + 0.2 * np.sin(2 * np.pi * fechas.month / 12)
        valores = rng.poisson(nivel * estacional)
        filas.append(pd.DataFrame({"fecha": fechas, "distrito": distrito, "delitos": valores}))
    return pd.concat(filas, ignore_index=True)


def test_evaluar_metricas() -> None:
    m = evaluar_metricas(np.array([100.0, 200.0, 300.0]), np.array([110.0, 190.0, 310.0]))
    assert m["MAE"] == 10.0
    assert m["WAPE_pct"] == round(30 / 600 * 100, 2)
    assert m["Sesgo_pct"] == round(10 / 600 * 100, 2)


def test_ultimo_mes_completo_excluye_mes_parcial() -> None:
    assert ultimo_mes_completo(pd.Timestamp("2026-10-16")) == pd.Timestamp("2026-09-01")
    assert ultimo_mes_completo(pd.Timestamp("2026-09-30 23:10")) == pd.Timestamp("2026-09-01")
    origenes = origenes_trimestrales(pd.Timestamp("2026-09-01"), n_cortes=8, horizonte=3)
    assert origenes[0] == pd.Timestamp("2024-10-01") and origenes[-1] == pd.Timestamp("2026-07-01")


def test_series_completan_meses_vacios_y_cortan_en_el_ultimo_mes() -> None:
    df = pd.DataFrame({
        "fecha": pd.to_datetime(["2024-01-05", "2024-03-02", "2024-03-09", "2024-04-01"] + ["2024-02-10"] * 60),
        "distrito": [1, 1, 1, 1] + [2] * 60,
    })
    serie = preparar_series_mensuales_distrito(df, hasta=pd.Timestamp("2024-03-01"), min_media_mensual=0)
    d1 = serie[serie["distrito"] == 1].set_index("fecha")["delitos"]
    assert d1.to_dict() == {pd.Timestamp("2024-01-01"): 1, pd.Timestamp("2024-02-01"): 0, pd.Timestamp("2024-03-01"): 2}
    assert preparar_series_mensuales_distrito(df, hasta=pd.Timestamp("2024-03-01"), min_media_mensual=10)["distrito"].unique().tolist() == [2]


def test_caracteristicas_solo_usan_el_pasado() -> None:
    """Cambiar el valor de un mes no altera ninguna variable de ese mismo mes ni de los anteriores."""
    serie = _serie()
    corte = pd.Timestamp("2020-06-01")
    alterada = serie.copy()
    alterada.loc[alterada["fecha"] >= corte, "delitos"] *= 10
    a = construir_caracteristicas_tiempo(serie).set_index(["distrito", "fecha"])
    b = construir_caracteristicas_tiempo(alterada).set_index(["distrito", "fecha"])
    columnas = [c for c in a.columns if c != "delitos"]
    hasta = a.index.get_level_values("fecha") <= corte
    pd.testing.assert_frame_equal(a.loc[hasta, columnas], b.loc[hasta, columnas])


def test_backtesting_sin_fuga_del_futuro() -> None:
    """El pronóstico del primer mes de un corte no cambia si se alteran los meses posteriores a ese mes."""
    serie = _serie()
    origen = pd.Timestamp("2023-01-01")
    alterada = serie.copy()
    alterada.loc[alterada["fecha"] > origen, "delitos"] *= 3
    res_a = backtesting_origen_movil(construir_caracteristicas_tiempo(serie), [origen], horizonte=1)["resultados"]
    res_b = backtesting_origen_movil(construir_caracteristicas_tiempo(alterada), [origen], horizonte=1)["resultados"]
    columnas = [c for c in res_a.columns if c.startswith(("pred_", "inf_", "sup_"))]
    pd.testing.assert_frame_equal(res_a[columnas], res_b[columnas])
    assert (res_a["fecha"] == origen).all()


def test_backtesting_origen_movil_metricas_e_intervalos() -> None:
    caracteristicas = construir_caracteristicas_tiempo(_serie(semilla=1))
    origenes = origenes_trimestrales(caracteristicas["fecha"].max(), n_cortes=4, horizonte=3)
    bt = backtesting_origen_movil(caracteristicas, origenes, horizonte=3)
    assert bt["configuracion"]["meses_evaluados"] == 12 and bt["configuracion"]["cortes"] == 4
    assert set(bt["por_origen"]["origen"]) == {o.strftime("%Y-%m") for o in origenes}
    assert bt["ganador"] == min(bt["metricas"], key=lambda m: bt["metricas"][m]["WAPE_pct"])
    for modelo, m in bt["metricas"].items():
        assert (bt["resultados"][f"inf_{modelo}"] <= bt["resultados"][f"sup_{modelo}"]).all()
        assert 70 <= m["cobertura_pct"] <= 100, modelo  # ruido estacionario: cobertura cercana al 90 %
