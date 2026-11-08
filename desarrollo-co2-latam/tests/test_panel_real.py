"""Controles sobre el panel ya construido (data/procesados, versionado): se saltan si no existe."""
import pandas as pd
import pytest

from desarrollo_co2 import config

pytestmark = pytest.mark.skipif(not config.PANEL.exists(), reason="falta el panel (ejecuta el pipeline)")


@pytest.fixture(scope="module")
def panel():
    return pd.read_csv(config.PANEL)


def test_una_fila_por_pais_y_anio(panel):
    assert not panel.duplicated(["iso3", "anio"]).any()
    assert set(panel["iso3"]) == set(config.PAISES) | {config.REGION}


def test_region_es_la_suma_de_sus_miembros(panel):
    miembros = sorted(set(config.PAISES) - {"CUB", "VEN"})
    for anio in (2000, 2024):
        suma = panel[(panel["iso3"].isin(miembros)) & (panel["anio"] == anio)]["co2_mt"].sum()
        region = panel[(panel["iso3"] == config.REGION) & (panel["anio"] == anio)]["co2_mt"].item()
        assert region == pytest.approx(suma)


def test_valores_plausibles(panel):
    p = panel[panel["iso3"] != config.REGION]
    assert (p["co2_mt"].dropna() > 0).all()
    assert p["co2_pc_t"].dropna().between(0, 20).all()
    assert p["urbana_pct"].dropna().between(0, 100).all()
    ecu = p[(p["iso3"] == "ECU") & (p["anio"] == 2022)].iloc[0]
    assert 17e6 < ecu["poblacion_bm"] < 19e6
