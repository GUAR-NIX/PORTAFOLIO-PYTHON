"""Kaplan-Meier, medianas con IC, tiempo medio restringido y log-rank, vectorizados con numpy.

Por qué implementarlos aquí y no llamar siempre a lifelines: con 7 millones de solicitudes y duraciones
al segundo hay millones de tiempos distintos; estas versiones agregan por tiempo único con
`np.unique` + `np.bincount` y calculan el log-rank por bloques, así que la memoria no crece con
(grupos × tiempos). Las pruebas comprueban que dan lo mismo que lifelines y que un ejemplo de libro.

Convenciones (iguales a lifelines):
* Varianza de Greenwood e IC «exponencial» (escala log(-log S)), que nunca sale de [0, 1].
* Mediana = primer tiempo con S(t) ≤ 0,5. Su IC = tiempos en que las bandas inferior y superior cruzan 0,5
  (Brookmeyer-Crowley). Si la banda superior nunca baja de 0,5, el límite superior es infinito.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


def kaplan_meier(duraciones: np.ndarray, eventos: np.ndarray, alfa: float = 0.05) -> pd.DataFrame:
    """Tabla de vida de Kaplan-Meier en cada tiempo distinto observado (eventos o censuras).

    Columnas: tiempo, en_riesgo, eventos, censurados, supervivencia, ic_inferior, ic_superior.
    La supervivencia en `tiempo` incluye los eventos ocurridos en ese instante (función continua a la derecha).
    """
    d = np.asarray(duraciones, dtype="float64")
    e = np.asarray(eventos, dtype="float64")
    if d.size == 0:
        raise ValueError("No hay observaciones")
    if np.isnan(d).any() or (d < 0).any():
        raise ValueError("Duraciones nulas o negativas")
    tiempos, idx = np.unique(d, return_inverse=True)
    eventos_t = np.bincount(idx, weights=e, minlength=tiempos.size)
    total_t = np.bincount(idx, minlength=tiempos.size).astype("float64")
    en_riesgo = d.size - np.concatenate(([0.0], np.cumsum(total_t)[:-1]))

    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.cumprod(1.0 - eventos_t / en_riesgo)
        termino = np.where(en_riesgo > eventos_t, eventos_t / (en_riesgo * (en_riesgo - eventos_t)), np.inf)
        termino = np.where(eventos_t == 0, 0.0, termino)
        greenwood = np.cumsum(termino)
        z = stats.norm.ppf(1 - alfa / 2)
        log_s = np.log(s)
        sd = np.sqrt(greenwood) / log_s  # negativo: log S < 0
        superior = np.exp(-np.exp(np.log(-log_s) + z * sd))
        inferior = np.exp(-np.exp(np.log(-log_s) - z * sd))
    # Antes del primer evento S = 1 y la banda es degenerada (igual que lifelines)
    sin_eventos = log_s == 0
    superior = np.where(sin_eventos, 1.0, superior)
    inferior = np.where(sin_eventos, 1.0, inferior)
    # Si S llega a 0 la banda colapsa en 0
    inferior = np.where(s == 0, 0.0, inferior)
    superior = np.where(s == 0, 0.0, superior)

    return pd.DataFrame(
        {
            "tiempo": tiempos,
            "en_riesgo": en_riesgo.astype("int64"),
            "eventos": eventos_t.astype("int64"),
            "censurados": (total_t - eventos_t).astype("int64"),
            "supervivencia": s,
            "ic_inferior": np.nan_to_num(inferior, nan=0.0),
            "ic_superior": np.nan_to_num(superior, nan=1.0),
        }
    )


def evaluar(tabla: pd.DataFrame, t: float | np.ndarray, columna: str = "supervivencia") -> np.ndarray:
    """Valor de la curva escalonada en los tiempos `t` (S = 1 antes del primer tiempo)."""
    t = np.atleast_1d(np.asarray(t, dtype="float64"))
    pos = np.searchsorted(tabla["tiempo"].to_numpy(), t, side="right") - 1
    valores = tabla[columna].to_numpy()
    return np.where(pos >= 0, valores[np.clip(pos, 0, None)], 1.0)


def _cruce(tiempos: np.ndarray, curva: np.ndarray, p: float) -> float:
    debajo = np.flatnonzero(curva <= p)
    return float(tiempos[debajo[0]]) if debajo.size else float("inf")


def mediana_con_ic(tabla: pd.DataFrame, p: float = 0.5) -> tuple[float, float, float]:
    """(mediana, ic_inferior, ic_superior) del tiempo hasta el evento (cuantil `1-p` del tiempo)."""
    t = tabla["tiempo"].to_numpy()
    return (
        _cruce(t, tabla["supervivencia"].to_numpy(), p),
        _cruce(t, tabla["ic_inferior"].to_numpy(), p),
        _cruce(t, tabla["ic_superior"].to_numpy(), p),
    )


def tiempo_medio_restringido(tabla: pd.DataFrame, tau: float) -> float:
    """RMST: área bajo S(t) entre 0 y `tau` = tiempo medio de resolución «topado» en tau.

    Es la alternativa honesta al promedio cuando hay censura: no exige que todos cierren.
    """
    t = tabla["tiempo"].to_numpy()
    s = tabla["supervivencia"].to_numpy()
    t_ = np.concatenate(([0.0], t[t < tau], [tau]))
    s_ = np.concatenate(([1.0], s[t < tau]))
    return float(np.sum(s_ * np.diff(t_)))


@dataclass
class ResultadoLogRank:
    estadistico: float
    grados_libertad: int
    p_valor: float
    resumen: pd.DataFrame  # por grupo: n, observados, esperados, O/E


def logrank(duraciones: np.ndarray, eventos: np.ndarray, grupos: np.ndarray, bloque: int = 200_000) -> ResultadoLogRank:
    """Prueba log-rank de k grupos (H0: misma función de supervivencia en todos).

    Para cada tiempo con eventos compara los eventos observados de cada grupo con los esperados si el
    riesgo fuera común (eventos totales × proporción en riesgo del grupo). El estadístico es
    (O−E)ᵀ V⁻¹ (O−E) con k−1 grados de libertad. Se acumula por bloques de tiempos para acotar la RAM.
    """
    d = np.asarray(duraciones, dtype="float64")
    e = np.asarray(eventos).astype(bool)
    g_cod, g_nombres = pd.factorize(pd.Series(grupos), sort=True)
    k = len(g_nombres)
    if k < 2:
        raise ValueError("Se necesitan al menos 2 grupos")

    t_evento = np.unique(d[e])
    ordenadas = [np.sort(d[g_cod == j]) for j in range(k)]
    eventos_ordenados = [np.sort(d[(g_cod == j) & e]) for j in range(k)]

    observados = np.zeros(k)
    esperados = np.zeros(k)
    varianza = np.zeros((k, k))
    for inicio in range(0, t_evento.size, bloque):
        t = t_evento[inicio : inicio + bloque]
        n_g = np.vstack([o.size - np.searchsorted(o, t, side="left") for o in ordenadas])  # en riesgo (k × T)
        d_g = np.vstack(
            [np.searchsorted(eo, t, side="right") - np.searchsorted(eo, t, side="left") for eo in eventos_ordenados]
        )
        n = n_g.sum(axis=0).astype("float64")
        dt = d_g.sum(axis=0).astype("float64")
        frac = n_g / n
        observados += d_g.sum(axis=1)
        esperados += (dt * frac).sum(axis=1)
        factor = np.where(n > 1, dt * (n - dt) / np.maximum(n - 1, 1), 0.0)
        varianza += np.diag((factor * frac).sum(axis=1)) - (factor * frac) @ frac.T

    dif = (observados - esperados)[:-1]
    estadistico = float(dif @ np.linalg.solve(varianza[:-1, :-1], dif))
    gl = k - 1
    resumen = pd.DataFrame(
        {
            "grupo": list(g_nombres),
            "n": np.bincount(g_cod, minlength=k),
            "observados": observados.astype("int64"),
            "esperados": esperados,
            "o_entre_e": observados / esperados,
        }
    )
    return ResultadoLogRank(estadistico, gl, float(stats.chi2.sf(estadistico, gl)), resumen)


def resumen_por_grupo(
    df: pd.DataFrame, grupo: str, taus: tuple[float, ...] = (1.0, 7.0, 30.0), tau_rmst: float = 90.0, min_n: int = 1
) -> pd.DataFrame:
    """Mediana KM con IC, % cerradas a 1/7/30 días, RMST y comparación con el promedio ingenuo, por grupo."""
    filas = []
    for nombre, sub in df.groupby(grupo, observed=True):
        if len(sub) < min_n:
            continue
        dur = sub["duracion_dias"].to_numpy()
        ev = sub["evento"].to_numpy()
        tabla = kaplan_meier(dur, ev)
        med, lo, hi = mediana_con_ic(tabla)
        fila = {
            grupo: nombre,
            "n": len(sub),
            "pct_censuradas": 100 * (1 - ev.mean()),
            "mediana_km_dias": med,
            "mediana_ic_inf": lo,
            "mediana_ic_sup": hi,
            "promedio_ingenuo_cerradas_dias": float(dur[ev == 1].mean()) if ev.any() else np.nan,
            "mediana_ingenua_cerradas_dias": float(np.median(dur[ev == 1])) if ev.any() else np.nan,
            f"rmst_{int(tau_rmst)}d": tiempo_medio_restringido(tabla, tau_rmst),
        }
        for tau in taus:
            fila[f"pct_cerradas_{int(tau)}d"] = 100 * (1 - float(evaluar(tabla, tau)[0]))
        filas.append(fila)
    return pd.DataFrame(filas).sort_values("n", ascending=False).reset_index(drop=True)


def curva_en_rejilla(duraciones: np.ndarray, eventos: np.ndarray, rejilla: np.ndarray) -> pd.DataFrame:
    """Curva KM (con banda) evaluada en una rejilla fija de tiempos: compacta para guardar y graficar."""
    tabla = kaplan_meier(duraciones, eventos)
    return pd.DataFrame(
        {
            "tiempo": rejilla,
            "supervivencia": evaluar(tabla, rejilla),
            "ic_inferior": evaluar(tabla, rejilla, "ic_inferior"),
            "ic_superior": evaluar(tabla, rejilla, "ic_superior"),
        }
    )
