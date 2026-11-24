"""Pruebas unitarias para el análisis policial y efectividad."""
from __future__ import annotations

import pandas as pd

from delitos_chicago.policial import (
    analisis_violencia_domestica,
    intervalo_confianza_proporcion,
    tasa_arresto_por_tipo,
)


def test_intervalo_confianza_wilson() -> None:
    inf, sup = intervalo_confianza_proporcion(50, 100, confianza=0.95)
    assert 0.0 <= inf <= 0.5 <= sup <= 1.0
    assert round(inf, 2) == 0.40 or round(inf, 2) == 0.41


def test_tasa_arresto_por_tipo(df_delitos_sinteticos: pd.DataFrame) -> None:
    res = tasa_arresto_por_tipo(df_delitos_sinteticos, min_casos=10)
    assert not res.empty
    assert "tasa_arresto_pct" in res.columns
    assert "ic_inf_pct" in res.columns
    assert "ic_sup_pct" in res.columns


def test_analisis_violencia_domestica(df_delitos_sinteticos: pd.DataFrame) -> None:
    dom = analisis_violencia_domestica(df_delitos_sinteticos)
    assert "proporcion_domestica_pct" in dom
    assert "tasa_arresto_domestico_pct" in dom
    assert dom["delitos_domesticos"] + dom["delitos_no_domesticos"] == len(df_delitos_sinteticos)
