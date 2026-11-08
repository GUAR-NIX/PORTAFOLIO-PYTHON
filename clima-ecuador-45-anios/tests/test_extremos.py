import numpy as np
import pandas as pd
import pytest

from clima_ecuador import extremos


def test_rachas():
    c = np.array([1, 1, 0, 1, 1, 1, 0, 0, 1], dtype=bool)
    assert extremos.rachas(c) == [2, 3, 1]
    assert extremos.rachas(np.zeros(4, dtype=bool)) == []
    assert extremos.dias_en_rachas(c, 3).tolist() == [0, 0, 0, 1, 1, 1, 0, 0, 0]


def test_dia_del_anio_ignora_29_de_febrero():
    f = pd.Series(pd.to_datetime(["2020-02-28", "2020-02-29", "2020-03-01", "2021-03-01", "2020-12-31"]))
    assert extremos.dia_del_anio(f).tolist() == [59, 59, 60, 60, 365]


def test_percentil_por_dia_del_anio(diario_sintetico):
    p90 = extremos.umbral_percentil(diario_sintetico, "tmax")
    assert len(p90) == 365
    # el umbral sigue el ciclo anual del seno: más alto en abril que en octubre
    assert p90[91] > p90[274]


def test_indices_tx90p_en_referencia_cerca_de_10(diario_sintetico):
    ind = extremos.indices_ciudad(diario_sintetico)
    ref = ind[ind["anio"].between(1981, 2010)]
    assert ref["tx90p"].mean() == pytest.approx(10, abs=1.5)
    # con calentamiento, la última década tiene más días cálidos que la primera
    assert ind[ind["anio"] >= 2011]["tx90p"].mean() > ind[ind["anio"] <= 1990]["tx90p"].mean()


def test_ola_de_calor_y_racha_seca():
    fechas = pd.date_range("1981-01-01", "2012-12-31", freq="D")
    d = pd.DataFrame({"fecha": fechas, "tmax": 20.0, "tmin": 10.0, "precip": 5.0})
    d["tmax"] += np.random.default_rng(1).normal(0, 0.1, len(d))
    d.loc[d["fecha"].between("2012-06-10", "2012-06-14"), "tmax"] = 30      # 5 días muy cálidos
    d.loc[d["fecha"].between("2012-08-01", "2012-08-20"), "precip"] = 0     # 20 días secos
    d.loc[d["fecha"] == "2012-09-01", "precip"] = 80
    ind = extremos.indices_ciudad(d).set_index("anio").loc[2012]
    assert ind["olas_calor"] >= 1 and ind["dias_ola_calor"] >= 5
    assert ind["cdd"] == 20 and ind["rachas_secas_10"] == 1
    assert ind["rx1day"] == 80 and ind["r20mm"] == 1
