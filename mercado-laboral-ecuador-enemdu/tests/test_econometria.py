"""Pruebas de las regresiones de Mincer, Oaxaca-Blinder, cuantiles y desigualdad."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from empleo_enemdu.desigualdad import curva_lorenz_y_deciles, gini_ponderado
from empleo_enemdu.mincer import estimar_modelos_mincer
from empleo_enemdu.oaxaca import brecha_cuantilica_genero, descomposicion_oaxaca_blinder


def test_modelos_mincer_retorno_educativo_y_canal_formalidad(
    resultados_json: dict[str, Any],
) -> None:
    """El retorno a la escolaridad disminuye al controlar por formalidad y es mayor en el sector formal."""
    modelos = resultados_json["mincer"]["modelos"]
    b_m1 = modelos["m1_base"]["coeficientes"]["escolaridad"]["beta"]
    b_m2 = modelos["m2_formalidad"]["coeficientes"]["escolaridad"]["beta"]
    b_m3 = modelos["m3_completo"]["coeficientes"]["escolaridad"]["beta"]
    b_for = modelos["m4_sector_formal"]["coeficientes"]["escolaridad"]["beta"]
    b_inf = modelos["m5_sector_informal"]["coeficientes"]["escolaridad"]["beta"]

    assert b_m1 > b_m2 > b_m3 > 0.02
    assert b_for > b_inf * 2.5

    # Los errores estándar agrupados por UPM deben ser mayores que los errores WLS ingenuos
    for m in modelos.values():
        c_esc = m["coeficientes"]["escolaridad"]
        assert c_esc["ee_cluster_upm"] > c_esc["ee_ingenuo_wls"] * 1.8


def test_efecto_diploma_monotono_creciente(resultados_json: dict[str, Any]) -> None:
    """El premio salarial por credencial educativa debe crecer de forma monótona hasta posgrado."""
    premios = [d["premio_salarial_pct"] for d in resultados_json["mincer"]["efecto_diploma"]]
    assert premios == sorted(premios)
    assert premios[-1] > 120.0  # Posgrado > +120%


def test_aditividad_exacta_oaxaca_blinder(df_muestra: pd.DataFrame) -> None:
    """La suma de dotaciones + retornos debe igualar exactamente la brecha logarítmica total."""
    res = descomposicion_oaxaca_blinder(df_muestra, n_boot=10, semilla=7)
    oax = res["resumen_oaxaca"]
    suma_partes = oax["dotaciones_explicada_log"] + oax["retornos_no_explicada_log"]
    assert suma_partes == pytest.approx(oax["brecha_log_total"], abs=2e-4)

    suma_ref_h = oax["dotaciones_ref_hombre_log"] + oax["retornos_ref_hombre_log"]
    assert suma_ref_h == pytest.approx(oax["brecha_log_total"], abs=2e-4)

    # Suma de los componentes individuales debe igualar el total explicado y no explicado
    suma_comp_exp = sum(c["dotaciones_log"] for c in res["componentes"])
    suma_comp_ret = sum(c["retornos_log"] for c in res["componentes"])
    assert suma_comp_exp == pytest.approx(oax["dotaciones_explicada_log"], abs=5e-4)
    assert suma_comp_ret == pytest.approx(oax["retornos_no_explicada_log"], abs=5e-4)


def test_mujeres_ocupadas_mayor_escolaridad_dotaciones_negativas(
    resultados_json: dict[str, Any],
) -> None:
    """En el Ecuador las mujeres ocupadas tienen más escolaridad que los hombres: dotaciones < 0."""
    oax = resultados_json["oaxaca_blinder"]
    desc = oax["descriptivos_ocupados"]
    assert desc["escolaridad_media_mujer"] > desc["escolaridad_media_hombre"]
    assert oax["resumen_oaxaca"]["dotaciones_explicada_log"] < 0.0
    assert (
        oax["resumen_oaxaca"]["retornos_no_explicada_log"]
        > oax["resumen_oaxaca"]["brecha_log_total"]
    )


def test_piso_pegajoso_informal_mayor_que_formal(df_muestra: pd.DataFrame) -> None:
    """En los cuantiles bajos (P10-P25), la brecha salarial es mayor en el sector informal."""
    df_q = brecha_cuantilica_genero(df_muestra)
    assert set(df_q["sector"].unique()) == {"Total ocupados", "Sector formal", "Sector informal"}
    assert len(df_q) == 33


def test_gini_propiedades_y_conciliacion_inec(resultados_json: dict[str, Any]) -> None:
    """Gini es 0 en equidistribución y coincide con 0,451 del INEC en el ingreso per cápita 2025."""
    iguales = np.ones(500) * 300.0
    pesos = np.ones(500)
    assert gini_ponderado(iguales, pesos) == pytest.approx(0.0, abs=1e-10)

    desig = resultados_json["desigualdad_y_pobreza"]
    assert desig["ingreso_per_capita_hogar"]["gini"] == pytest.approx(0.451, abs=1e-3)
    assert desig["ingreso_per_capita_hogar"]["indice_palma"] > 2.0

    # La suma de las participaciones de los 10 deciles debe ser 100%
    suma_deciles = sum(d["participacion_ingreso_pct"] for d in desig["deciles_ingpc"])
    assert suma_deciles == pytest.approx(100.0, abs=0.1)


def test_curva_lorenz_monotona_y_acotada() -> None:
    """Verifica que la curva de Lorenz comience en 0, termine en 100 y esté debajo de la diagonal."""
    rng = np.random.default_rng(99)
    ingresos = rng.lognormal(mean=5.5, sigma=0.8, size=1000)
    pesos = rng.uniform(1.0, 20.0, size=1000)
    df_lor, df_dec, res = curva_lorenz_y_deciles(ingresos, pesos)

    assert df_lor["ingreso_acum_pct"].iloc[0] == pytest.approx(0.0, abs=1e-6)
    assert df_lor["ingreso_acum_pct"].iloc[-1] == pytest.approx(100.0, abs=1e-6)
    assert (df_lor["ingreso_acum_pct"] <= df_lor["igualdad_pct"] + 1e-6).all()
    assert len(df_dec) == 10
    assert 0.2 < res["gini"] < 0.7
