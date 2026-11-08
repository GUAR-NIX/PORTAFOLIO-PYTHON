"""
El Niño–Oscilación del Sur (ENOS) y el clima del Ecuador.

* Índice **ONI** de NOAA: media móvil de 3 meses de la anomalía de temperatura del mar en Niño 3.4.
  El Niño si ONI ≥ +0,5 °C, La Niña si ≤ −0,5 °C.
* **Correlación con rezago**: anomalía mensual local en el mes t contra ONI en t − k (k = 0…6): ¿el Pacífico
  avisa con meses de anticipación?
* **Significancia con tamaño efectivo** (Bretherton et al. 1999): ONI y las anomalías locales están muy
  autocorrelacionadas, así que hay muchos menos datos independientes que meses. n_ef = n (1 − r₁ρ₁)/(1 + r₁ρ₁).
* **Compuestos**: anomalía media de la lluvia por fase de ENOS en la temporada lluviosa de la Costa (ene–abr).
* **ONI frente a Niño 1+2**: el ONI mide el Pacífico central; Niño 1+2, el mar frente a la costa. En 2015-16 el ONI
  marcó récord y la Costa tuvo lluvia normal: lo que manda en la Costa es el calentamiento del Pacífico oriental.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from . import config


def autocorrelacion_1(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    return float(np.sum(x[:-1] * x[1:]) / np.sum(x ** 2))


def correlacion_efectiva(x: np.ndarray, y: np.ndarray) -> dict:
    """Pearson con p calculado sobre el tamaño efectivo de muestra (Bretherton 1999)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    ok = ~(np.isnan(x) | np.isnan(y))
    x, y = x[ok], y[ok]
    n = len(x)
    r = float(np.corrcoef(x, y)[0, 1])
    r1, r2 = autocorrelacion_1(x), autocorrelacion_1(y)
    n_ef = float(np.clip(n * (1 - r1 * r2) / (1 + r1 * r2), 3, n))
    t = r * np.sqrt((n_ef - 2) / max(1 - r ** 2, 1e-12))
    p = float(2 * stats.t.sf(abs(t), n_ef - 2))
    p_ingenuo = float(stats.pearsonr(x, y)[1])
    return {"r": r, "n": n, "n_efectivo": n_ef, "p": p, "p_ingenuo": p_ingenuo}


def correlaciones_rezago(anomalias: pd.DataFrame, oni: pd.DataFrame, variables: list[str],
                         grupo: str = "punto", rezagos=config.REZAGOS_ONI) -> pd.DataFrame:
    """Correlación de cada serie mensual de anomalías con el ONI adelantado ``k`` meses."""
    o = oni.set_index("fecha")["oni"]
    filas = []
    for clave, d in anomalias.groupby(grupo):
        d = d.set_index("mes").sort_index()
        for k in rezagos:
            oni_k = o.shift(k, freq="MS").reindex(d.index)
            for var in variables:
                res = correlacion_efectiva(oni_k.to_numpy(), d[var].to_numpy())
                filas.append({grupo: clave, "variable": var, "rezago": k, **res})
    t = pd.DataFrame(filas)
    t["significativa"] = t["p"] < config.ALFA
    return t


def mejor_rezago(correlaciones: pd.DataFrame, grupo: str = "punto") -> pd.DataFrame:
    """El rezago con la correlación de mayor valor absoluto para cada serie."""
    idx = correlaciones.assign(a=correlaciones["r"].abs()).groupby([grupo, "variable"])["a"].idxmax()
    return correlaciones.loc[idx].reset_index(drop=True)


def compuestos(mensual_region: pd.DataFrame, oni: pd.DataFrame, meses: tuple[int, ...] = (1, 2, 3, 4),
               variable: str = "precip_pct") -> pd.DataFrame:
    """Anomalía media de ``variable`` en ``meses`` según la fase ENOS de ese mismo mes."""
    d = mensual_region.merge(oni.rename(columns={"fecha": "mes"}), on="mes", how="inner")
    d = d[d["mes"].dt.month.isin(meses)]
    t = d.groupby(["region", "fase"])[variable].agg(["mean", "median", "count"]).reset_index()
    return t.rename(columns={"mean": "media", "median": "mediana", "count": "meses"})


def episodios_fuertes(anomalias_region: pd.DataFrame, oni: pd.DataFrame, umbral: float = 1.5) -> pd.DataFrame:
    """Lluvia de la Costa en los meses de El Niño fuerte (ONI ≥ 1,5) frente a la normal, por episodio."""
    o = oni[oni["oni"] >= umbral].copy()
    if o.empty:
        return pd.DataFrame()
    # Un episodio = meses consecutivos sobre el umbral
    indice_mes = o["fecha"].dt.year * 12 + o["fecha"].dt.month
    o["episodio"] = (indice_mes.diff() != 1).cumsum()
    filas = []
    for _, e in o.groupby("episodio"):
        inicio, fin = e["fecha"].min(), e["fecha"].max()
        # La lluvia responde con un poco de retraso: se cuentan hasta 3 meses después del fin del episodio
        ventana = anomalias_region[(anomalias_region["mes"] >= inicio)
                                   & (anomalias_region["mes"] <= fin + pd.DateOffset(months=3))]
        for region, v in ventana.groupby("region"):
            filas.append({"inicio": inicio.strftime("%Y-%m"), "fin": fin.strftime("%Y-%m"),
                          "oni_max": float(e["oni"].max()), "region": region,
                          "lluvia_pct_normal": float(v["precip_pct"].mean() + 100),
                          "anomalia_tmed": float(v["tmed"].mean())})
    return pd.DataFrame(filas)


def temporada_lluviosa(anomalias_region: pd.DataFrame, indices: dict[str, pd.DataFrame],
                       meses: tuple[int, ...] = (1, 2, 3, 4)) -> pd.DataFrame:
    """Por año: anomalía media de la lluvia de ``meses`` por región y la media de cada índice en esos meses."""
    a = anomalias_region[anomalias_region["mes"].dt.month.isin(meses)]
    t = a.assign(anio=a["mes"].dt.year).pivot_table(index="anio", columns="region", values="precip_pct", aggfunc="mean")
    for nombre, df in indices.items():
        d = df[df["fecha"].dt.month.isin(meses)]
        t[nombre] = d.groupby(d["fecha"].dt.year)[nombre].mean()
    return t.reset_index()


def comparar_indices(temporada: pd.DataFrame, regiones: list[str], indices: list[str]) -> pd.DataFrame:
    """Correlación (Spearman y Pearson) entre la lluvia de la temporada y cada índice, por región."""
    filas = []
    for region in regiones:
        for ind in indices:
            d = temporada[[region, ind]].dropna()
            filas.append({"region": region, "indice": ind, "n_anios": len(d),
                          "r_pearson": float(d[region].corr(d[ind])),
                          "r_spearman": float(stats.spearmanr(d[region], d[ind])[0]),
                          "p_spearman": float(stats.spearmanr(d[region], d[ind])[1])})
    return pd.DataFrame(filas)
