"""
Desagrupamiento (declustering) de Gardner y Knopoff (1974).

Los periodos de retorno suponen sismos independientes (proceso de Poisson). Las réplicas violan ese
supuesto: Pedernales 2016 trajo cientos de sismos en pocas semanas. Gardner-Knopoff quita los eventos que
caen dentro de una ventana espacio-temporal de un sismo mayor:

    L(M) = 10^(0,1238·M + 0,983) km
    T(M) = 10^(0,032·M + 2,7389) días   si M ≥ 6,5
           10^(0,5409·M − 0,547) días   si M < 6,5

Se recorre el catálogo de mayor a menor magnitud; cada evento que aún es "principal" marca como réplica
(o premonitor) a los menores dentro de su ventana, antes o después.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .geo import distancia_km


def ventana_gk(m) -> tuple[np.ndarray, np.ndarray]:
    m = np.asarray(m, dtype=float)
    distancia = 10 ** (0.1238 * m + 0.983)
    dias = np.where(m >= 6.5, 10 ** (0.032 * m + 2.7389), 10 ** (0.5409 * m - 0.547))
    return distancia, dias


def gardner_knopoff(df: pd.DataFrame, col_mag: str = "mw") -> pd.Series:
    """True si el evento es principal (independiente). Requiere tiempo, latitud y longitud."""
    t = (df["tiempo"] - pd.Timestamp("1900-01-01", tz="UTC")).dt.total_seconds().to_numpy() / 86400
    lat, lon = df["latitud"].to_numpy(), df["longitud"].to_numpy()
    m = df[col_mag].to_numpy(dtype=float)
    distancia, dias = ventana_gk(m)

    orden_t = np.argsort(t)
    t_ord = t[orden_t]
    principal = np.ones(len(df), dtype=bool)
    for i in np.argsort(-m, kind="stable"):
        if not principal[i]:
            continue
        a, z = np.searchsorted(t_ord, [t[i] - dias[i], t[i] + dias[i]], side="left")
        candidatos = orden_t[a:z]
        candidatos = candidatos[(candidatos != i) & principal[candidatos] & (m[candidatos] <= m[i])]
        if len(candidatos) == 0:
            continue
        cerca = distancia_km(lat[i], lon[i], lat[candidatos], lon[candidatos]) <= distancia[i]
        principal[candidatos[cerca]] = False
    return pd.Series(principal, index=df.index, name="principal")
