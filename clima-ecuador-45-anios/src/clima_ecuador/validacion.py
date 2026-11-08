"""
Validación de ERA5 contra estaciones de superficie (NOAA GHCN-Daily), una fuente independiente.

ERA5 representa celdas de ~25 km con una topografía suavizada: en los Andes una celda mezcla valles, laderas y
páramos. Se compara la celda de ERA5 de cada estación (temperatura corregida a la altitud de la estación) con:
* **sesgo** medio de Tmáx, Tmín y lluvia;
* **correlación de anomalías diarias** (sin el ciclo anual, que inflaría cualquier correlación);
* **correlación de la lluvia mensual** y **frecuencia de días húmedos** (ERA5 tiende a llover poco y todos los días).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def unir_estaciones(diario: pd.DataFrame, ghcn: pd.DataFrame) -> pd.DataFrame:
    """Une la serie diaria de ERA5 en el punto ``est_<id>`` con la estación del mismo id."""
    e = diario[diario["punto"].str.startswith("est_")].copy()
    e["estacion"] = e["punto"].str.removeprefix("est_")
    m = e.merge(ghcn, on=["estacion", "fecha"], suffixes=("_era5", "_est"))
    m["nombre"] = m["estacion"].map({k: v[0] for k, v in config.ESTACIONES.items()})
    m["region"] = m["estacion"].map({k: v[4] for k, v in config.ESTACIONES.items()})
    return m


def _anomalia_diaria(fecha: pd.Series, valor: pd.Series) -> pd.Series:
    clim = valor.groupby(fecha.dt.month).transform("mean")
    return valor - clim


def metricas(unidas: pd.DataFrame, min_dias: int = 365) -> pd.DataFrame:
    filas = []
    for (est, nombre, region), d in unidas.groupby(["estacion", "nombre", "region"]):
        fila = {"estacion": est, "nombre": nombre, "region": region,
                "altitud": config.ESTACIONES[est][3], "desde": d["fecha"].min().year, "hasta": d["fecha"].max().year}
        for v in ["tmax", "tmin"]:
            ok = d[[f"{v}_era5", f"{v}_est"]].dropna()
            ok = ok.join(d["fecha"])
            fila[f"dias_{v}"] = len(ok)
            if len(ok) >= min_dias:
                fila[f"sesgo_{v}"] = float((ok[f"{v}_era5"] - ok[f"{v}_est"]).mean())
                fila[f"r_anom_{v}"] = float(_anomalia_diaria(ok["fecha"], ok[f"{v}_era5"])
                                            .corr(_anomalia_diaria(ok["fecha"], ok[f"{v}_est"])))
        p = d[["fecha", "precip_era5", "precip_est"]].dropna()
        fila["dias_precip"] = len(p)
        if len(p) >= min_dias:
            mes = p.assign(mes=p["fecha"].dt.to_period("M")).groupby("mes")
            conteo = mes.size()
            mensual = mes[["precip_era5", "precip_est"]].sum()[conteo >= 20]
            fila["lluvia_era5_mm_anio"] = float(p["precip_era5"].mean() * 365.25)
            fila["lluvia_est_mm_anio"] = float(p["precip_est"].mean() * 365.25)
            fila["ratio_lluvia"] = fila["lluvia_era5_mm_anio"] / max(fila["lluvia_est_mm_anio"], 1e-9)
            fila["r_lluvia_mensual"] = float(mensual["precip_era5"].corr(mensual["precip_est"])) \
                if len(mensual) >= 12 else np.nan
            fila["dias_humedos_era5_pct"] = float(100 * (p["precip_era5"] >= 1).mean())
            fila["dias_humedos_est_pct"] = float(100 * (p["precip_est"] >= 1).mean())
            fila["r_lluvia_diaria"] = float(p["precip_era5"].corr(p["precip_est"]))
        filas.append(fila)
    return pd.DataFrame(filas)
