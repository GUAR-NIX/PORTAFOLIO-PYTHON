"""
Periodos de retorno y probabilidades a partir del ajuste de Gutenberg-Richter.

**Advertencia:** esto estima una **frecuencia media de largo plazo**, no predice cuándo ni dónde ocurrirá
el próximo sismo. Supone que los sismos principales siguen un proceso de Poisson (sin memoria) y que la
recta de Gutenberg-Richter se puede extrapolar hasta M7, cosa que en la realidad tiene un tope (la
magnitud máxima que admite cada falla) y que este análisis no modela.

    λ(M ≥ m) = λ(M ≥ Mc) · 10^(−b·(m − Mc))        tasa anual
    T(m)     = 1 / λ                                periodo de retorno medio (años)
    P(≥1 en t años) = 1 − exp(−λ·t)                 Poisson
"""
from __future__ import annotations

import numpy as np
from scipy import stats

from .gutenberg_richter import LOG10_E, a_clases


def tasa_anual(m_objetivo: float, tasa_mc: float, b: float, mc: float) -> float:
    return float(tasa_mc * 10 ** (-b * (m_objetivo - mc)))


def probabilidad(tasa: float, anios: float = 1.0) -> float:
    return float(1 - np.exp(-tasa * anios))


def retorno_con_incertidumbre(m, mc: float, anios: float, objetivos=(6.0, 7.0), dm: float = 0.1,
                              n_boot: int = 1000, semilla: int = 42) -> list[dict]:
    """Tasa, periodo de retorno y probabilidades con IC 95 % por bootstrap paramétrico-no paramétrico:
    se remuestrean las magnitudes (incertidumbre de b) y el número de eventos ~ Poisson (incertidumbre de a)."""
    m = a_clases(m, dm)
    m = m[m >= mc - 1e-9]
    n = len(m)
    b = LOG10_E / (m.mean() - (mc - dm / 2))
    rng = np.random.default_rng(semilla)
    bs = np.array([LOG10_E / (rng.choice(m, n).mean() - (mc - dm / 2)) for _ in range(n_boot)])
    ns = rng.poisson(n, n_boot)
    filas = []
    for objetivo in objetivos:
        tasa = tasa_anual(objetivo, n / anios, b, mc)
        tasas = ns / anios * 10 ** (-bs * (objetivo - mc))
        bajo, alto = np.percentile(tasas, [2.5, 97.5])
        filas.append({
            "magnitud": objetivo, "tasa_anual": tasa, "tasa_ic95": [float(bajo), float(alto)],
            "periodo_retorno_anios": 1 / tasa, "periodo_ic95": [float(1 / alto), float(1 / bajo)],
            "prob_anual": probabilidad(tasa, 1), "prob_anual_ic95": [probabilidad(bajo), probabilidad(alto)],
            "prob_50_anios": probabilidad(tasa, 50),
            "prob_50_anios_ic95": [probabilidad(bajo, 50), probabilidad(alto, 50)],
        })
    return filas


def tasa_empirica(conteo: int, anios: float) -> dict:
    """Línea base: contar sismos y dividir por los años, con IC exacto de Poisson (Garwood)."""
    bajo = stats.chi2.ppf(0.025, 2 * conteo) / 2 if conteo > 0 else 0.0
    alto = stats.chi2.ppf(0.975, 2 * (conteo + 1)) / 2
    tasa = conteo / anios
    return {"conteo": int(conteo), "anios": anios, "tasa_anual": tasa,
            "tasa_ic95": [float(bajo / anios), float(alto / anios)],
            "periodo_retorno_anios": (1 / tasa) if conteo else None,
            "prob_anual": probabilidad(tasa)}
