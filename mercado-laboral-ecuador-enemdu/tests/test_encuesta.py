"""Pruebas unitarias del motor de inferencia en muestras complejas (encuesta.py)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from empleo_enemdu.encuesta import (
    DisenoMuestralENEMDU,
    cuantil_ponderado,
    estimar_razon_dominio,
    prueba_diferencia_dominios,
)


def test_diseno_muestral_linealizacion_taylor_exacta() -> None:
    """Verifica que la varianza de Taylor coincida con el cálculo analítico manual en 2 estratos."""
    df = pd.DataFrame(
        {
            "estrato": ["E1", "E1", "E1", "E1", "E2", "E2", "E2", "E2"],
            "upm": ["U1", "U1", "U2", "U2", "U3", "U3", "U4", "U4"],
            "fexp": [10.0, 10.0, 20.0, 20.0, 15.0, 15.0, 25.0, 25.0],
            "y": [1.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
            "dom": [True, True, True, True, True, True, True, True],
        }
    )
    diseno = DisenoMuestralENEMDU.desde_dataframe(df)
    est = estimar_razon_dominio(diseno, df["y"], df["dom"], indicador="test", dominio="Total")

    # Cálculo manual: X_hat = 140, Y_hat = 10+10+15 = 35 -> R_hat = 0.25
    assert est.estimacion == pytest.approx(35.0 / 140.0, abs=1e-12)
    assert est.poblacion_expandida == pytest.approx(140.0, abs=1e-12)
    assert est.n_upm == 4
    assert est.n_estratos == 2
    assert est.grados_libertad == 2

    # Totales linealizados por UPM: z_ha = sum(w_i * (y_i - 0.25) / 140)
    z_u1 = (10.0 * 0.75 + 10.0 * 0.75) / 140.0
    z_u2 = (20.0 * (-0.25) + 20.0 * (-0.25)) / 140.0
    z_u3 = (15.0 * 0.75 + 15.0 * (-0.25)) / 140.0
    z_u4 = (25.0 * (-0.25) + 25.0 * (-0.25)) / 140.0
    # Para a_h = 2: v_h = (2/1) * ((z_1 - media)^2 + (z_2 - media)^2) = (z_1 - z_2)^2
    var_manual = (z_u1 - z_u2) ** 2 + (z_u3 - z_u4) ** 2
    assert est.error_estandar == pytest.approx(np.sqrt(var_manual), abs=1e-12)


def test_correlacion_intraconglomerado_produce_deff_mayor_a_uno() -> None:
    """Cuando las observaciones dentro de cada UPM son idénticas, DEFF supera ampliamente a 1."""
    rng = np.random.default_rng(123)
    filas = []
    for h in range(5):
        for u in range(10):
            val_upm = float(rng.integers(0, 2))
            for _ in range(15):
                filas.append(
                    {
                        "estrato": f"H{h}",
                        "upm": f"H{h}_U{u}",
                        "fexp": 20.0,
                        "y": val_upm,
                    }
                )
    df = pd.DataFrame(filas)
    diseno = DisenoMuestralENEMDU.desde_dataframe(df)
    est = estimar_razon_dominio(diseno, df["y"], np.ones(len(df), dtype=bool))
    assert est.deff > 10.0
    assert est.deft > 3.0
    assert est.n_efectivo < est.n_muestral / 10.0


def test_dominio_vacio_lanza_value_error(df_muestra: pd.DataFrame) -> None:
    """Un dominio sin observaciones válidas debe lanzar ValueError explícito."""
    diseno = DisenoMuestralENEMDU.desde_dataframe(df_muestra)
    masc_vacia = np.zeros(len(df_muestra), dtype=bool)
    with pytest.raises(ValueError, match="no tiene observaciones"):
        estimar_razon_dominio(diseno, df_muestra["adec"], masc_vacia, dominio="Vacio")


def test_covarianza_intra_upm_en_diferencia_hombre_mujer(df_muestra: pd.DataFrame) -> None:
    """En hogares que comparten UPM, la covarianza positiva reduce el EE frente a independencia."""
    diseno = DisenoMuestralENEMDU.desde_dataframe(df_muestra)
    pean = df_muestra["pean"].eq(1)
    hombre = pean & (df_muestra["p02"] == 1)
    mujer = pean & (df_muestra["p02"] == 2)
    res = prueba_diferencia_dominios(
        diseno, df_muestra["adec"], hombre, mujer, nombre_a="Hombre", nombre_b="Mujer"
    )
    assert res["diferencia"] == pytest.approx(res["estimacion_a"] - res["estimacion_b"], abs=1e-12)
    assert res["error_estandar_complejo"] > 0
    assert 0.0 <= res["p_valor"] <= 1.0


def test_cuantil_ponderado_exacto() -> None:
    """Verifica mediana y cuartiles ponderados."""
    valores = np.array([100.0, 200.0, 300.0, 400.0])
    pesos_iguales = np.array([1.0, 1.0, 1.0, 1.0])
    q = cuantil_ponderado(valores, pesos_iguales, [0.25, 0.50, 0.75])
    assert q[1] == pytest.approx(250.0, abs=1e-6)

    pesos_concentrados = np.array([1.0, 1.0, 1.0, 100.0])
    q_pesado = cuantil_ponderado(valores, pesos_concentrados, [0.50])
    assert q_pesado[0] > 350.0
