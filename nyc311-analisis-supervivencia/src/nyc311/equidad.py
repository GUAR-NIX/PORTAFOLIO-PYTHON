"""Equidad territorial y evolución mensual con estandarización indirecta por tipo de queja.

Comparar barrios con el tiempo bruto mezcla dos cosas: **qué** se reporta en cada zona (un ruido de
fiesta se cierra en horas; una plaga en el edificio, en semanas) y **cómo** se atiende. Para aislar lo
segundo se usa la razón observado/esperado (O/E), la misma lógica que la mortalidad estandarizada:

1. Resultado binario: «cerrada en ≤ 7 días». Como la censura es solo administrativa y la cohorte termina
   26 días antes del corte, ese resultado está **observado para todas** las solicitudes (no hay sesgo).
2. Esperado de cada solicitud = tasa de toda la ciudad en su celda `tipo_queja × descriptor`
   (o del tipo si la celda tiene < 30 casos).
3. O/E de un grupo = cerradas observadas / esperadas. O/E < 1: se cierran menos de lo que su mezcla de
   quejas predice (más lento); O/E > 1: más rápido. IC 95 % aproximado con la varianza binomial Σp(1−p).

Es **asociación**, no causalidad: un O/E bajo puede reflejar recursos, pero también casos más difíciles
dentro de la misma celda, edificios más viejos, reportes repetidos o cómo cada agencia «cierra».
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

HORIZONTE_DIAS = 7.0
HORIZONTES = {"1 h": 1 / 24, "3 h": 3 / 24, "8 h": 8 / 24, "1 día": 1.0, "7 días": 7.0}
MIN_CELDA = 30


def marcar_resultado(df: pd.DataFrame, horizonte: float = HORIZONTE_DIAS) -> pd.Series:
    """1 si la solicitud se cerró dentro de `horizonte` días (observado para toda la cohorte)."""
    return (df["evento"].eq(1) & df["duracion_dias"].le(horizonte)).astype("int8")


def probabilidad_esperada(df: pd.DataFrame, resultado: pd.Series, min_celda: int = MIN_CELDA) -> pd.Series:
    """Tasa de la ciudad en la celda tipo × descriptor de cada solicitud (respaldo: tasa del tipo)."""
    tmp = pd.DataFrame({"tipo": df["tipo_queja"], "desc": df["descriptor"], "y": resultado})
    celda = tmp.groupby(["tipo", "desc"], observed=True)["y"].agg(["mean", "size"])
    tipo = tmp.groupby("tipo", observed=True)["y"].mean()
    p_celda = pd.MultiIndex.from_arrays([tmp["tipo"], tmp["desc"]])
    p = celda["mean"].reindex(p_celda).to_numpy()
    n = celda["size"].reindex(p_celda).to_numpy()
    p_tipo = tipo.reindex(tmp["tipo"]).to_numpy()
    return pd.Series(np.where(n >= min_celda, p, p_tipo), index=df.index, name="esperado")


def razon_oe(observado: pd.Series, esperado: pd.Series, grupos: pd.Series, min_n: int = 1) -> pd.DataFrame:
    """O/E por grupo con IC 95 % y z (desvío respecto de lo esperado en unidades de error estándar)."""
    # float64: el resultado llega como int8 y `100 * suma` se desbordaría en grupos pequeños
    tmp = pd.DataFrame({"g": grupos, "o": observado.astype("float64"), "e": esperado, "v": esperado * (1 - esperado)})
    agg = tmp.groupby("g", observed=True).agg(n=("o", "size"), observadas=("o", "sum"), esperadas=("e", "sum"), var=("v", "sum"))
    agg = agg.loc[agg["n"] >= min_n].copy()
    ee = np.sqrt(agg["var"]) / agg["esperadas"]
    agg["o_entre_e"] = agg["observadas"] / agg["esperadas"]
    agg["ic_inf"] = agg["o_entre_e"] - 1.96 * ee
    agg["ic_sup"] = agg["o_entre_e"] + 1.96 * ee
    agg["z"] = (agg["observadas"] - agg["esperadas"]) / np.sqrt(agg["var"])
    agg["p_valor"] = 2 * stats.norm.sf(np.abs(agg["z"]))
    agg["pct_cerradas_7d"] = 100 * agg["observadas"] / agg["n"]
    agg["pct_esperado_7d"] = 100 * agg["esperadas"] / agg["n"]
    return agg.drop(columns="var").reset_index().rename(columns={"g": grupos.name or "grupo"})


def benjamini_hochberg(p: np.ndarray, q: float = 0.05) -> np.ndarray:
    """Máscara de hallazgos significativos controlando la tasa de falsos descubrimientos (FDR)."""
    p = np.asarray(p, dtype="float64")
    orden = np.argsort(p)
    umbral = q * np.arange(1, p.size + 1) / p.size
    pasa = p[orden] <= umbral
    k = np.flatnonzero(pasa).max() + 1 if pasa.any() else 0
    mascara = np.zeros(p.size, dtype=bool)
    mascara[orden[:k]] = True
    return mascara
