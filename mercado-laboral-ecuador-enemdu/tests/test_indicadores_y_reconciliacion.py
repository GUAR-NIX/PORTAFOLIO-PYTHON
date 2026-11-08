"""Pruebas de reconciliación contra los tabulados oficiales del INEC y reglas de limpieza."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from empleo_enemdu.limpieza import calcular_escolaridad_clasica, calcular_escolaridad_egb


def test_reconciliacion_exacta_80_celdas_contra_inec(df_reconciliacion: pd.DataFrame) -> None:
    """Las 80 combinaciones (10 indicadores × 8 dominios) deben coincidir al 100% con el INEC."""
    assert len(df_reconciliacion) == 80
    assert bool(df_reconciliacion["reconcilia_ok"].all()) is True
    assert df_reconciliacion["dif_indicador_pp"].abs().max() == pytest.approx(0.0, abs=1e-6)
    assert df_reconciliacion["dif_ee_pp"].abs().max() == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize(
    ("indicador", "valor_oficial", "ee_oficial"),
    [
        ("Empleo Bruto", 62.0, 0.4),
        ("Empleo Global", 96.4, 0.1),
        ("Empleo Adecuado/Pleno", 37.1, 0.6),
        ("Subempleo", 19.4, 0.4),
        ("Empleo no Remunerado", 8.8, 0.5),
        ("Otro Empleo no pleno", 30.8, 0.5),
        ("Desempleo", 3.6, 0.1),
        ("Participación Global", 64.3, 0.5),
        ("Participación Bruta", 45.7, 0.5),
        ("Sector informal", 51.5, 0.8),
    ],
)
def test_cifras_nacionales_oficiales_2025(
    df_reconciliacion: pd.DataFrame,
    indicador: str,
    valor_oficial: float,
    ee_oficial: float,
) -> None:
    """Verifica cada indicador nacional 2025 frente al boletín técnico oficial del INEC."""
    fila = df_reconciliacion.loc[
        (df_reconciliacion["dominio"] == "Total")
        & (df_reconciliacion["indicador"] == indicador)
    ].iloc[0]
    assert round(float(fila["estimacion_pct"]), 1) == pytest.approx(valor_oficial, abs=1e-6)
    assert round(float(fila["ee_complejo_pct"]), 1) == pytest.approx(ee_oficial, abs=1e-6)
    assert float(fila["deff"]) > 5.0


def test_identidad_suma_condicion_actividad_pea(df_reconciliacion: pd.DataFrame) -> None:
    """Empleo Global + Desempleo debe sumar exactamente 100% de la PEA en cada dominio."""
    piv = df_reconciliacion.pivot_table(
        index="dominio", columns="indicador", values="estimacion_pct"
    )
    suma = piv["Empleo Global"] + piv["Desempleo"]
    assert np.allclose(suma.to_numpy(), 100.0, atol=0.01)


def test_auditoria_centinelas_ingrl(resultados_json: dict[str, Any]) -> None:
    """Verifica que los 480 códigos 999999 y 1.471 códigos -1 hayan sido auditados y limpiados."""
    cent = resultados_json["calidad_y_diseno"]["centinelas_detectados"]
    assert cent["ingrl_999999_no_informa"] == 480
    assert cent["ingrl_menos_1_sin_ingreso"] == 1471
    assert cent["media_ingrl_cruda_sin_limpiar_usd"] > 3500.0
    assert 450.0 < cent["media_ingrl_limpia_ponderada_usd"] < 550.0
    assert cent["factor_distorsion_centinela"] > 7.0


def test_cobertura_24_provincias(df_provincias: pd.DataFrame) -> None:
    """Las 24 provincias del Ecuador deben estar presentes con intervalos de confianza válidos."""
    assert len(df_provincias) == 24
    assert (df_provincias["empleo_adecuado_pct"] > 0).all()
    assert (df_provincias["empleo_adecuado_ee_pct"] > 0).all()
    assert (df_provincias["informalidad_pct"].between(10, 95)).all()


def test_formulas_escolaridad_egb_y_clasica() -> None:
    """Verifica la homologación EGB frente a la escala clásica de Mincer."""
    p10a = pd.Series([1, 4, 5, 6, 7, 9, 10])
    p10b = pd.Series([np.nan, 6, 10, 6, 3, 5, 2])
    egb = calcular_escolaridad_egb(p10a, p10b)
    clas = calcular_escolaridad_clasica(p10a, p10b)

    assert list(egb) == [0.0, 7.0, 10.0, 13.0, 13.0, 18.0, 20.0]
    assert list(clas) == [0.0, 6.0, 9.0, 12.0, 12.0, 17.0, 19.0]
