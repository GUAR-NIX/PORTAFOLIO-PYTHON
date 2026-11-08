import numpy as np
import pandas as pd
import pytest

from clima_ecuador import descarga, enso


def test_leer_oni(tmp_path):
    ruta = tmp_path / "oni.data"
    ruta.write_text(" 1950 2026\n1997  -0.5 -0.4 -0.2 0.1 0.6 1.0 1.4 1.7 2.0 2.2 2.4 2.4\n"
                    "2026  0.1 0.2 -99.90 -99.90 -99.90 -99.90 -99.90 -99.90 -99.90 -99.90 -99.90 -99.90\n"
                    "  -99.9\n ONI from CPC\n", encoding="utf-8")
    oni = descarga.leer_oni(ruta).set_index("fecha")
    assert len(oni) == 14
    assert oni.loc["1997-12-01", "fase"] == "El Niño"
    assert oni.loc["1997-01-01", "fase"] == "La Niña"


def test_correlacion_efectiva_es_mas_conservadora():
    rng = np.random.default_rng(3)
    n = 300
    x = np.zeros(n)
    y = np.zeros(n)
    for i in range(1, n):
        x[i] = 0.9 * x[i - 1] + rng.normal()
        y[i] = 0.9 * y[i - 1] + rng.normal()
    r = enso.correlacion_efectiva(x, y)
    assert r["n_efectivo"] < n / 4
    assert r["p"] > r["p_ingenuo"]


def test_correlacion_con_rezago_encuentra_el_retraso():
    meses = pd.date_range("1980-01-01", periods=480, freq="MS")
    rng = np.random.default_rng(5)
    oni_v = np.convolve(rng.normal(size=480), np.ones(3) / 3, "same")
    oni = pd.DataFrame({"fecha": meses, "oni": oni_v})
    # la lluvia local responde al ONI de 3 meses antes
    local = pd.Series(oni_v, index=meses).shift(3) * 30 + rng.normal(0, 5, 480)
    anom = pd.DataFrame({"punto": "X", "mes": meses, "precip_pct": local.to_numpy()})
    c = enso.correlaciones_rezago(anom, oni, ["precip_pct"])
    assert enso.mejor_rezago(c).iloc[0]["rezago"] == 3


def test_leer_ghcn_descarta_marcas_de_calidad(tmp_path):
    ruta = tmp_path / "X.csv"
    pd.DataFrame({"STATION": ["X", "X"], "DATE": ["2020-01-01", "2020-01-02"], "TMAX": [250, 990],
                  "TMAX_ATTRIBUTES": [",,S", ",X,S"], "PRCP": [12, 0], "PRCP_ATTRIBUTES": [",,S", ",,S"]}
                 ).to_csv(ruta, index=False)
    g = descarga.leer_ghcn([ruta])
    assert g["tmax"].tolist()[0] == pytest.approx(25.0)
    assert np.isnan(g["tmax"].tolist()[1])
    assert g["precip"].tolist() == [1.2, 0.0]
    assert g["tmin"].isna().all()


def test_episodios_agrupa_meses_consecutivos():
    meses = pd.date_range("1997-01-01", periods=24, freq="MS")
    valores = [0.0] * 6 + [1.6, 1.9, 2.2, 2.3] + [0.0] * 8 + [1.7, 1.8] + [0.0] * 4
    oni = pd.DataFrame({"fecha": meses, "oni": valores})
    anom = pd.DataFrame({"region": "Costa", "mes": meses, "precip_pct": 100.0, "tmed": 1.0})
    e = enso.episodios_fuertes(anom, oni)
    assert len(e) == 2
    assert e.iloc[0]["inicio"] == "1997-07" and e.iloc[0]["fin"] == "1997-10"
