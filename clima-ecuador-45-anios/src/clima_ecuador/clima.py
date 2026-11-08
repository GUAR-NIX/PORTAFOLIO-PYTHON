"""Climatología 1981–2010, anomalías mensuales y anuales, y estacionalidad (mensual y horaria)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

VARIABLES = ["tmax", "tmin", "tmed", "precip", "humedad", "viento_max", "radiacion"]


def climatologia_mensual(mensual: pd.DataFrame, referencia: tuple[int, int] = config.PERIODO_REFERENCIA,
                         grupo: str = "punto") -> pd.DataFrame:
    """Media de cada mes del año en el periodo de referencia (la "normal" de la OMM)."""
    ref = mensual[mensual["mes"].dt.year.between(*referencia)]
    cols = [c for c in VARIABLES if c in ref]
    return ref.assign(m=ref["mes"].dt.month).groupby([grupo, "m"])[cols].mean().reset_index()


def anomalias_mensuales(mensual: pd.DataFrame, referencia: tuple[int, int] = config.PERIODO_REFERENCIA,
                        grupo: str = "punto") -> pd.DataFrame:
    """Anomalía = valor − normal del mismo mes. Lluvia también en % de la normal."""
    clim = climatologia_mensual(mensual, referencia, grupo)
    m = mensual.assign(m=mensual["mes"].dt.month).merge(clim, on=[grupo, "m"], suffixes=("", "_normal"))
    salida = m[[grupo, "mes"]].copy()
    for c in [c for c in VARIABLES if c in mensual]:
        salida[c] = m[c] - m[f"{c}_normal"]
    salida["precip_pct"] = 100 * m["precip"] / m["precip_normal"].where(m["precip_normal"] > 1) - 100
    return salida.sort_values([grupo, "mes"]).reset_index(drop=True)


def anomalias_anuales(anual: pd.DataFrame, referencia: tuple[int, int] = config.PERIODO_REFERENCIA,
                      grupo: str = "punto") -> pd.DataFrame:
    ref = anual[anual["anio"].between(*referencia)]
    cols = [c for c in VARIABLES if c in anual]
    normal = ref.groupby(grupo)[cols].mean()
    a = anual.set_index(grupo)
    salida = (a[cols] - normal.reindex(a.index)).assign(anio=a["anio"]).reset_index()
    salida["precip_pct"] = 100 * (a["precip"] / normal["precip"].reindex(a.index)).to_numpy() - 100
    return salida


def ranking_anios(anom_region: pd.DataFrame, variable: str = "tmed", n: int = 5) -> pd.DataFrame:
    """Los ``n`` años más cálidos (o con mayor valor) de cada región."""
    return (anom_region.sort_values(variable, ascending=False).groupby("region").head(n)
            .sort_values(["region", variable], ascending=[True, False]))


def ciclo_diurno(horario: pd.DataFrame, puntos: list[str] | None = None,
                 periodo: tuple[int, int] = (1991, 2020)) -> pd.DataFrame:
    """Media de temperatura, lluvia y humedad por hora local y región (normal 1991–2020)."""
    h = horario[horario["hora_local"].dt.year.between(*periodo)]
    if puntos is not None:
        h = h[h["punto"].isin(puntos)]
    regiones = {c: v[3] for c, v in config.CIUDADES.items()}
    h = h.assign(region=h["punto"].astype(str).map(regiones), hora=h["hora_local"].dt.hour)
    h = h.dropna(subset=["region"])
    # Lluvia y radiación de ERA5 en Open-Meteo son de la hora que *termina* en "hora"
    por_punto = h.groupby(["region", "punto", "hora"], observed=True).agg(
        temp=("temp", "mean"), precip=("precip", "mean"), humedad=("humedad", "mean"),
        radiacion=("radiacion", "mean")).reset_index()
    return por_punto.groupby(["region", "hora"])[["temp", "precip", "humedad", "radiacion"]].mean().reset_index()


def estacionalidad_lluvia(clim_region: pd.DataFrame) -> pd.DataFrame:
    """Mes más lluvioso, más seco y concentración estacional (% de la lluvia anual en los 4 meses más lluviosos)."""
    filas = []
    for region, d in clim_region.groupby("region"):
        p = d.set_index("m")["precip"]
        top4 = p.sort_values(ascending=False).head(4)
        filas.append({"region": region, "lluvia_anual_mm": float(p.sum()), "mes_mas_lluvioso": int(p.idxmax()),
                      "mes_mas_seco": int(p.idxmin()), "pct_4_meses": float(100 * top4.sum() / p.sum()),
                      "indice_estacionalidad": float(np.abs(p - p.sum() / 12).sum() / p.sum())})
    return pd.DataFrame(filas)
