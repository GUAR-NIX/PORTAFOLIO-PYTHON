"""Corte retrospectivo, estandarización O/E y lectura de hazard ratios con datos de juguete."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nyc311.cox import leer_hr
from nyc311.equidad import benjamini_hochberg, marcar_resultado, probabilidad_esperada, razon_oe
from nyc311.sesgo import recensurar


def test_recensurar_convierte_cierres_futuros_en_censura() -> None:
    df = pd.DataFrame(
        {
            "creada": pd.to_datetime(["2025-01-01", "2025-01-01", "2025-01-20"]),
            "cerrada": pd.to_datetime(["2025-01-03", "2025-03-01", None]),
        }
    )
    r = recensurar(df, "2025-01-15")
    assert len(r) == 2  # la creada después del corte ficticio no existía todavía
    assert r["evento"].tolist() == [1, 0]
    assert r["duracion_dias"].tolist() == pytest.approx([2.0, 14.0])


def test_oe_controla_la_mezcla_de_quejas() -> None:
    """Dos barrios con la misma rapidez por tipo pero distinta mezcla: O/E = 1 en ambos."""
    filas = []
    for barrio, n_rapidas, n_lentas in [("A", 80, 20), ("B", 20, 80)]:
        filas += [{"barrio": barrio, "tipo_queja": "ruido", "descriptor": "x", "evento": 1,
                   "duracion_dias": 0.1 if i % 10 else 9.0} for i in range(n_rapidas)]
        filas += [{"barrio": barrio, "tipo_queja": "plaga", "descriptor": "y", "evento": 1,
                   "duracion_dias": 20.0 if i % 2 else 3.0} for i in range(n_lentas)]
    df = pd.DataFrame(filas)
    obs = marcar_resultado(df, 7.0)
    esp = probabilidad_esperada(df, obs, min_celda=1)
    r = razon_oe(obs, esp, df["barrio"].rename("barrio")).set_index("barrio")
    # Sin ajustar, B parece mucho más lento (menos cerradas en 7 días) ...
    assert r.loc["A", "pct_cerradas_7d"] > r.loc["B", "pct_cerradas_7d"] + 20
    # ... pero comparado con lo esperado por su mezcla, no hay diferencia
    assert r["o_entre_e"].to_numpy() == pytest.approx([1.0, 1.0])


def test_benjamini_hochberg() -> None:
    p = np.array([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216])
    assert benjamini_hochberg(p).tolist() == [True, True] + [False] * 8


def test_lectura_de_hazard_ratios() -> None:
    assert leer_hr(0.87, 0.85, 0.88) == "en cada momento, 13 % menos probable cerrarse (más lento)"
    assert leer_hr(1.25, 1.2, 1.3) == "en cada momento, 25 % más probable cerrarse (más rápido)"
    assert leer_hr(1.01, 0.98, 1.04) == "sin diferencia clara con la referencia"
