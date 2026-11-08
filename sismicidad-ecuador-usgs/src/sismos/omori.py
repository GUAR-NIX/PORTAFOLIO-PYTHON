"""
Réplicas: ley de Omori-Utsu ajustada por máxima verosimilitud (Ogata, 1983).

    λ(t) = K / (t + c)^p          réplicas por día, t = días desde el sismo principal

* p ≈ 1 es lo típico (Omori, 1894); c absorbe la pérdida de réplicas en las primeras horas, cuando las
  ondas del principal y de las primeras réplicas tapan a las pequeñas.
* Verosimilitud de un proceso de Poisson no homogéneo en [S, T]:
      log L = Σ log λ(t_i) − ∫_S^T λ(t) dt
  Para c y p dados, K tiene solución cerrada (K = N / ∫(t+c)^−p dt), así que se optimizan solo c y p.
* Errores estándar con la inversa del hessiano numérico de −log L en (K, c, p).
* Líneas base: Omori original (p = 1 fijo) y un decaimiento **exponencial** λ(t) = A·e^(−t/τ); se
  comparan por AIC.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import optimize

from .geo import distancia_km


def seleccionar_replicas(df: pd.DataFrame, principal: dict, radio_km: float, dias: float) -> pd.DataFrame:
    t0 = pd.Timestamp(principal["tiempo"])
    d = df[(df["tiempo"] > t0) & (df["tiempo"] <= t0 + pd.Timedelta(days=dias)) & (df["id"] != principal["id"])]
    dist = distancia_km(principal["latitud"], principal["longitud"], d["latitud"].to_numpy(),
                        d["longitud"].to_numpy())
    d = d.assign(distancia_km=dist, dias=(d["tiempo"] - t0).dt.total_seconds() / 86400)
    return d[d["distancia_km"] <= radio_km].sort_values("dias").reset_index(drop=True)


def _integral(c: float, p: float, s: float, t: float) -> float:
    if abs(p - 1) < 1e-8:
        return float(np.log((t + c) / (s + c)))
    return float(((t + c) ** (1 - p) - (s + c) ** (1 - p)) / (1 - p))


def log_verosimilitud(k: float, c: float, p: float, tiempos, s: float, t: float) -> float:
    tiempos = np.asarray(tiempos, dtype=float)
    return float(len(tiempos) * np.log(k) - p * np.log(tiempos + c).sum() - k * _integral(c, p, s, t))


def _k_optimo(c, p, n, s, t):
    return n / _integral(c, p, s, t)


def ajustar_omori_utsu(tiempos, s: float, t: float, p_fijo: float | None = None) -> dict:
    """Ajuste MLE. ``p_fijo=1`` da la ley de Omori original (línea base)."""
    tiempos = np.asarray(tiempos, dtype=float)
    n = len(tiempos)

    def menos_logl(x):
        c = np.exp(x[0])
        p = p_fijo if p_fijo is not None else x[1]
        if not 0.2 < p < 3:
            return 1e12
        return -log_verosimilitud(_k_optimo(c, p, n, s, t), c, p, tiempos, s, t)

    x0s = [[np.log(c0)] + ([] if p_fijo is not None else [p0]) for c0 in (0.005, 0.05, 0.5) for p0 in (0.8, 1.1)]
    mejor = min((optimize.minimize(menos_logl, x0, method="Nelder-Mead",
                                   options={"xatol": 1e-8, "fatol": 1e-8, "maxiter": 4000}) for x0 in x0s),
                key=lambda r: r.fun)
    c = float(np.exp(mejor.x[0]))
    p = float(p_fijo if p_fijo is not None else mejor.x[1])
    k = float(_k_optimo(c, p, n, s, t))
    logl = -float(mejor.fun)
    n_par = 2 if p_fijo is not None else 3

    # Errores estándar: hessiano numérico de −log L en los parámetros libres
    libres = [k, c] + ([] if p_fijo is not None else [p])

    def f(v):
        pp = p_fijo if p_fijo is not None else v[2]
        if v[0] <= 0 or v[1] <= 0:
            return 1e12
        return -log_verosimilitud(v[0], v[1], pp, tiempos, s, t)

    errores = _errores_hessiano(f, np.array(libres))
    nombres = ["K", "c", "p"][:len(libres)]
    return {"modelo": "Omori (p=1)" if p_fijo is not None else "Omori-Utsu", "n": n, "K": k, "c": c,
            "p": p, **{f"se_{nm}": float(e) for nm, e in zip(nombres, errores)},
            "log_verosimilitud": logl, "aic": 2 * n_par - 2 * logl, "s": s, "t": t}


def ajustar_exponencial(tiempos, s: float, t: float) -> dict:
    """Línea base: λ(t) = A·exp(−t/τ). A tiene solución cerrada para cada τ."""
    tiempos = np.asarray(tiempos, dtype=float)
    n = len(tiempos)

    def integral(tau):
        return tau * (np.exp(-s / tau) - np.exp(-t / tau))

    def menos_logl(log_tau):
        tau = np.exp(log_tau[0])
        a = n / integral(tau)
        return -(n * np.log(a) - tiempos.sum() / tau - n)

    r = optimize.minimize(menos_logl, [np.log(10.0)], method="Nelder-Mead")
    tau = float(np.exp(r.x[0]))
    logl = -float(r.fun)
    return {"modelo": "Exponencial", "n": n, "A": float(n / integral(tau)), "tau_dias": tau,
            "log_verosimilitud": logl, "aic": 2 * 2 - 2 * logl}


def tasa_omori(tiempo, k, c, p):
    return k / (np.asarray(tiempo, dtype=float) + c) ** p


def acumulado_omori(tiempo, k, c, p, s: float = 0.0):
    tiempo = np.asarray(tiempo, dtype=float)
    return np.array([k * _integral(c, p, s, x) for x in tiempo])


def _errores_hessiano(f, x: np.ndarray) -> np.ndarray:
    h = np.maximum(np.abs(x) * 1e-4, 1e-7)
    n = len(x)
    hess = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            ei, ej = np.eye(n)[i] * h[i], np.eye(n)[j] * h[j]
            hess[i, j] = (f(x + ei + ej) - f(x + ei - ej) - f(x - ei + ej) + f(x - ei - ej)) / (4 * h[i] * h[j])
    try:
        cov = np.linalg.inv(hess)
        return np.sqrt(np.clip(np.diag(cov), 0, None))
    except np.linalg.LinAlgError:
        return np.full(n, np.nan)


def simular_omori(k: float, c: float, p: float, s: float, t: float, semilla: int = 0) -> np.ndarray:
    """Tiempos de réplicas sintéticos por inversión de la integral (para las pruebas)."""
    rng = np.random.default_rng(semilla)
    total = k * _integral(c, p, s, t)
    n = rng.poisson(total)
    u = rng.uniform(0, 1, n) * _integral(c, p, s, t)
    if abs(p - 1) < 1e-8:
        x = (s + c) * np.exp(u) - c
    else:
        x = ((s + c) ** (1 - p) + u * (1 - p)) ** (1 / (1 - p)) - c
    return np.sort(x)
