"""Kaplan-Meier y log-rank propios contra un caso de libro y contra lifelines."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from lifelines import KaplanMeierFitter
from lifelines.statistics import multivariate_logrank_test
from lifelines.utils import median_survival_times

from nyc311.supervivencia import (
    curva_en_rejilla,
    evaluar,
    kaplan_meier,
    logrank,
    mediana_con_ic,
    resumen_por_grupo,
    tiempo_medio_restringido,
)

# Freireich et al. (1963), leucemia: remisión en semanas. Ejemplo clásico de Kleinbaum & Klein,
# «Survival Analysis: A Self-Learning Text». evento = 0 marca la censura (el «+» del libro).
MP6_T = [6, 6, 6, 6, 7, 9, 10, 10, 11, 13, 16, 17, 19, 20, 22, 23, 25, 32, 32, 34, 35]
MP6_E = [1, 1, 1, 0, 1, 0, 1, 0, 0, 1, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0]
PLACEBO_T = [1, 1, 2, 2, 3, 4, 4, 5, 5, 8, 8, 8, 8, 11, 11, 12, 12, 15, 17, 22, 23]


def test_km_reproduce_la_tabla_del_libro() -> None:
    tabla = kaplan_meier(np.array(MP6_T), np.array(MP6_E))
    esperado = {6: 0.857, 7: 0.807, 10: 0.753, 13: 0.690, 16: 0.627, 22: 0.538, 23: 0.448}
    for t, s in esperado.items():
        assert evaluar(tabla, t)[0] == pytest.approx(s, abs=5e-4)
    # Entre eventos la curva no cambia (las censuras no la bajan)
    assert evaluar(tabla, 9)[0] == evaluar(tabla, 7)[0]
    assert mediana_con_ic(tabla)[0] == 23


def test_logrank_reproduce_el_libro() -> None:
    """Kleinbaum & Klein informan χ² = 16,79 (1 gl) para 6-MP frente a placebo."""
    d = np.array(MP6_T + PLACEBO_T)
    e = np.array(MP6_E + [1] * len(PLACEBO_T))
    g = np.array(["6-MP"] * 21 + ["placebo"] * 21)
    r = logrank(d, e, g)
    assert r.estadistico == pytest.approx(16.79, abs=0.01)
    assert r.grados_libertad == 1 and r.p_valor < 1e-4
    resumen = r.resumen.set_index("grupo")
    assert resumen.loc["placebo", "observados"] == 21
    assert resumen.loc["placebo", "esperados"] == pytest.approx(10.75, abs=0.01)


@pytest.fixture(scope="module")
def datos_aleatorios() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(7)
    n = 4_000
    g = rng.choice(["a", "b", "c", "d"], n)
    d = np.round(rng.exponential(np.where(g == "b", 6.0, 5.0)), 2)
    d[:50] = 0.0  # cierres instantáneos
    e = (rng.random(n) < 0.75).astype(int)
    return d, e, g


def test_km_coincide_con_lifelines(datos_aleatorios) -> None:
    d, e, _ = datos_aleatorios
    propia = kaplan_meier(d, e)
    kmf = KaplanMeierFitter().fit(d, e)
    ref = kmf.survival_function_.join(kmf.confidence_interval_).reset_index()
    m = propia.merge(ref, left_on="tiempo", right_on="timeline")
    assert len(m) == len(propia)
    np.testing.assert_allclose(m["supervivencia"], m["KM_estimate"], atol=1e-12)
    np.testing.assert_allclose(m["ic_inferior"], m["KM_estimate_lower_0.95"], atol=1e-10)
    np.testing.assert_allclose(m["ic_superior"], m["KM_estimate_upper_0.95"], atol=1e-10)
    med, lo, hi = mediana_con_ic(propia)
    assert med == pytest.approx(kmf.median_survival_time_)
    np.testing.assert_allclose([lo, hi], median_survival_times(kmf.confidence_interval_).to_numpy().ravel())


def test_logrank_k_grupos_coincide_con_lifelines(datos_aleatorios) -> None:
    d, e, g = datos_aleatorios
    propia = logrank(d, e, g, bloque=97)  # bloque pequeño: ejercita la acumulación por bloques
    ref = multivariate_logrank_test(d, g, e)
    assert propia.estadistico == pytest.approx(ref.test_statistic, rel=1e-9)
    assert propia.p_valor == pytest.approx(ref.p_value, rel=1e-6)
    assert propia.grados_libertad == 3


def test_rmst_sin_censura_es_el_promedio() -> None:
    d = np.array([1.0, 2.0, 3.0, 10.0])
    tabla = kaplan_meier(d, np.ones(4))
    assert tiempo_medio_restringido(tabla, 100) == pytest.approx(d.mean())
    # Topado en 2: min(d, 2) promedia (1 + 2 + 2 + 2) / 4
    assert tiempo_medio_restringido(tabla, 2) == pytest.approx(1.75)


def test_censura_total_no_alcanza_la_mediana() -> None:
    tabla = kaplan_meier(np.array([1.0, 2.0, 3.0]), np.zeros(3))
    assert (tabla["supervivencia"] == 1).all()
    assert mediana_con_ic(tabla)[0] == float("inf")


def test_km_rechaza_duraciones_negativas() -> None:
    with pytest.raises(ValueError):
        kaplan_meier(np.array([1.0, -0.5]), np.array([1, 1]))


def test_curva_en_rejilla_y_resumen_por_grupo(datos_aleatorios) -> None:
    d, e, g = datos_aleatorios
    rejilla = np.array([0.0, 1.0, 5.0, 50.0])
    c = curva_en_rejilla(d, e, rejilla)
    assert c["supervivencia"].is_monotonic_decreasing
    assert (c["ic_inferior"] <= c["supervivencia"]).all() and (c["supervivencia"] <= c["ic_superior"]).all()
    df = pd.DataFrame({"duracion_dias": d, "evento": e, "grupo": g})
    r = resumen_por_grupo(df, "grupo")
    assert set(r["grupo"]) == {"a", "b", "c", "d"}
    assert (r["mediana_ic_inf"] <= r["mediana_km_dias"]).all()
    # El promedio de las cerradas ignora las censuradas largas: queda por debajo del RMST sin tope efectivo
    assert (r["pct_cerradas_7d"] > r["pct_cerradas_1d"]).all()
