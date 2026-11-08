"""
Descomposición de Kaya con LMDI aditivo (Ang, 2004).

    CO2 = Población × (PIB / Población) × (Energía / PIB) × (CO2 / Energía)

El LMDI reparte el cambio del CO2 entre los cuatro factores **sin residuo**: la suma de los
efectos es exactamente CO2_final − CO2_inicial. Nota: el CO2 incluye cemento y quema de gas,
que no son energía; quedan dentro del factor "carbono de la energía".
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FACTORES = {
    "poblacion": "Población",
    "riqueza": "PIB per cápita",
    "intensidad_energetica": "Energía por USD de PIB",
    "carbono_energia": "CO2 por unidad de energía",
}


def media_logaritmica(a: float, b: float) -> float:
    """L(a, b) = (a − b) / (ln a − ln b), con L(a, a) = a."""
    if a <= 0 or b <= 0:
        return np.nan
    return a if np.isclose(a, b) else (a - b) / (np.log(a) - np.log(b))


def factores(fila: pd.Series) -> dict[str, float]:
    return {
        "poblacion": fila["poblacion_bm"],
        "riqueza": fila["pib_ppa"] / fila["poblacion_bm"],
        "intensidad_energetica": fila["energia_twh"] / fila["pib_ppa"],
        "carbono_energia": fila["co2_mt"] / fila["energia_twh"],
    }


def lmdi(fila0: pd.Series, fila1: pd.Series) -> dict[str, float]:
    """Efecto de cada factor (en Mt de CO2) entre dos observaciones."""
    c0, c1 = fila0["co2_mt"], fila1["co2_mt"]
    peso = media_logaritmica(c1, c0)
    f0, f1 = factores(fila0), factores(fila1)
    efectos = {k: peso * np.log(f1[k] / f0[k]) for k in FACTORES}
    efectos["total"] = c1 - c0
    return efectos


BASE = ["poblacion_bm", "pib_ppa", "energia_twh", "co2_mt"]


def descomponer(panel: pd.DataFrame, iso3: str, inicio: int, fin: int, ventana: int = 1) -> pd.DataFrame:
    """Efectos en Mt y en % del CO2 inicial para un país o la región.

    Con ``ventana`` > 1 los extremos son promedios de ese número de años (p. ej. 2000–2002 y
    2022–2024), igual que en la tabla de desacople.
    """
    g = panel[panel["iso3"] == iso3].set_index("anio")[BASE]
    fila0 = g.loc[inicio:inicio + ventana - 1].mean()
    fila1 = g.loc[fin - ventana + 1:fin].mean()
    ef = lmdi(fila0, fila1)
    c0 = fila0["co2_mt"]
    t = pd.DataFrame({"factor": [FACTORES.get(k, "Cambio total") for k in ef],
                      "mt": list(ef.values())})
    t["pct_co2_inicial"] = 100 * t["mt"] / c0
    t.insert(0, "iso3", iso3)
    return t
