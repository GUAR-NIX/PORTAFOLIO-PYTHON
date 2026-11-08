"""Pruebas del análisis espacial: tasas anuales, grilla, Getis-Ord Gi* y estabilidad (Jaccard)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from delitos_chicago.espacial import (
    METROS_POR_PIE,
    conteos_grilla,
    estabilidad_hotspots,
    gi_estrella,
    hotspots_gi,
    jaccard,
    pesos_reina,
    resumen_areas,
    tasas_anuales_area,
)


def _gi_formula(y: np.ndarray, w) -> np.ndarray:
    """Gi* de Getis y Ord (1992) / Ord y Getis (1995) con pesos binarios e i como vecino de sí mismo."""
    n = len(y)
    W = np.eye(n)
    for i, vecinos in w.neighbors.items():
        W[i, vecinos] = 1.0
    media, s = y.mean(), np.sqrt((y**2).mean() - y.mean() ** 2)
    sw, sw2 = W.sum(1), (W**2).sum(1)
    return (W @ y - media * sw) / (s * np.sqrt((n * sw2 - sw**2) / (n - 1)))


def _grilla(n: int = 12, foco: bool = True, anio: int = 2020, semilla: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    celdas = pd.DataFrame([(x, y) for x in range(n) for y in range(n)], columns=["cx", "cy"])
    celdas["delitos"] = rng.poisson(20, len(celdas))
    if foco:
        bloque = celdas["cx"].between(2, 4) & celdas["cy"].between(2, 4)
        celdas.loc[bloque, "delitos"] += 80
    celdas["anio"] = anio
    return celdas


def test_gi_estrella_coincide_con_la_formula() -> None:
    celdas = _grilla()
    w = pesos_reina(celdas)
    assert w.cardinalities[0] == 3 and max(w.cardinalities.values()) == 8  # esquina y celda interior
    z = gi_estrella(celdas["delitos"].to_numpy(), w)
    np.testing.assert_allclose(z, _gi_formula(celdas["delitos"].to_numpy(float), w), atol=1e-10)


def test_hotspots_detectan_el_foco_inyectado() -> None:
    gi = hotspots_gi(_grilla())
    hot = gi[gi["hotspot"]]
    assert len(hot) > 0
    assert hot["cx"].between(1, 5).all() and hot["cy"].between(1, 5).all()
    assert gi.query("cx == 3 and cy == 3")["hotspot"].item()
    # Sin foco, la corrección FDR no debe declarar hotspots en ruido de Poisson
    assert not hotspots_gi(_grilla(foco=False, semilla=1))["hotspot"].any()


def test_jaccard_y_estabilidad() -> None:
    assert jaccard({1, 2, 3}, {2, 3, 4}) == 0.5
    assert jaccard(set(), set()) == 1.0
    gi = pd.concat([hotspots_gi(_grilla(anio=a, semilla=a)) for a in (2020, 2021)], ignore_index=True)
    tabla, resumen = estabilidad_hotspots(gi)
    assert tabla["jaccard_vs_anio_anterior"].isna().iloc[0]
    assert 0.5 < tabla["jaccard_vs_anio_anterior"].iloc[1] <= 1.0  # el mismo foco persiste
    assert resumen["celdas_hotspot_todos_los_anios"] <= resumen["celdas_hotspot_alguna_vez"]


def test_conteos_grilla_asigna_celdas_y_completa_ceros() -> None:
    lado = 1000 / METROS_POR_PIE  # 1 km en pies
    df = pd.DataFrame({
        "coord_x": [0.5 * lado, 0.6 * lado, 1.5 * lado, 1.5 * lado, 0.0],
        "coord_y": [0.5 * lado, 0.7 * lado, 0.5 * lado, 0.5 * lado, 0.0],
        "anio": [2020, 2020, 2020, 2021, 2020],
    })
    g = conteos_grilla(df, [2020, 2021]).set_index(["cx", "cy", "anio"])["delitos"]
    assert g[(0, 0, 2020)] == 2 and g[(1, 0, 2020)] == 1
    assert g[(0, 0, 2021)] == 0  # año sin delitos en una celda del área de estudio
    assert len(g) == 4  # la coordenada 0 (sin georreferencia) se descarta


def test_tasas_anuales_por_area() -> None:
    poblacion = pd.Series({1: 1000, 2: 50_000})
    df = pd.DataFrame({
        "area_comunitaria": [1] * 10 + [2] * 100 + [1] * 20 + [3] * 5,
        "anio": [2020] * 110 + [2021] * 20 + [2020] * 5,
        "arresto": [True] * 5 + [False] * 130,
    })
    tasas = tasas_anuales_area(df, poblacion).set_index(["anio", "area_comunitaria"])
    assert tasas.loc[(2020, 1), "tasa_100k"] == 1000.0  # 10 delitos / 1000 hab × 100 000
    assert tasas.loc[(2020, 2), "tasa_100k"] == 200.0
    assert tasas.loc[(2020, 1), "rank_tasa"] == 1 and tasas.loc[(2020, 2), "rank_volumen"] == 1
    assert 3 not in tasas.index.get_level_values(1)  # área sin población no entra
    resumen = resumen_areas(tasas.reset_index(), pd.Series({1: "Uno", 2: "Dos"})).set_index("area_comunitaria")
    assert resumen.loc[1, "tasa_anual_100k"] == 1500  # media de 1000 (2020) y 2000 (2021): tasa anual, no acumulada
