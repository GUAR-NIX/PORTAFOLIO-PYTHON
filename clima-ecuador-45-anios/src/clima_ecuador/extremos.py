"""
Índices de extremos al estilo ETCCDI (Expert Team on Climate Change Detection and Indices), por ciudad y año.

Calor (umbral = percentil 90 del día del año en 1981–2010, ventana de 5 días centrada, como el ETCCDI):
* ``tx90p`` / ``tn90p``: % de días con Tmáx / Tmín por encima de su p90.
* ``dias_ola_calor`` y ``olas_calor``: días dentro de rachas de ≥ 3 días seguidos con Tmáx > p90, y número de rachas.
  En el trópico la variación diaria es pequeña: 3 días (no los 6 del WSDI) ya es un evento relevante.
* ``wsdi``: el índice oficial (rachas de ≥ 6 días).

Lluvia:
* ``prcptot`` (mm en días húmedos ≥ 1 mm), ``r20mm`` (días ≥ 20 mm), ``rx1day`` y ``rx5day`` (máximos de 1 y 5 días),
  ``r95ptot`` (mm caídos en días por encima del p95 de los días húmedos de 1981–2010), ``sdii`` (intensidad media).
* Rachas secas: ``cdd`` (máximo de días seguidos con < 1 mm) y ``rachas_secas_10`` (rachas de ≥ 10 días).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def dia_del_anio(fechas: pd.Series) -> np.ndarray:
    """Día del año 1–365; el 29 de febrero se asigna al 28 para no tener un día con 1/4 de datos."""
    f = pd.to_datetime(fechas)
    doy = f.dt.dayofyear.to_numpy().copy()
    bisiesto = f.dt.is_leap_year.to_numpy()
    doy[bisiesto & (doy > 59)] -= 1
    return doy


def umbral_percentil(diario: pd.DataFrame, columna: str, percentil: float = config.PERCENTIL_CALOR,
                     referencia: tuple[int, int] = config.PERIODO_REFERENCIA, ventana: int = 5,
                     solo_humedos: bool = False) -> pd.Series:
    """Percentil del día del año (ventana centrada de ``ventana`` días) en el periodo de referencia.

    Devuelve una serie indexada por día del año (1–365). Con ``solo_humedos`` se usa un único percentil
    (no por día del año) de los días con lluvia ≥ 1 mm, como en R95p.
    """
    ref = diario[diario["fecha"].dt.year.between(*referencia)]
    if solo_humedos:
        humedos = ref.loc[ref[columna] >= config.UMBRAL_DIA_LLUVIA, columna]
        return pd.Series(np.nanpercentile(humedos, percentil) if len(humedos) else np.nan, index=range(1, 366))
    doy = dia_del_anio(ref["fecha"])
    valores = ref[columna].to_numpy()
    medio = ventana // 2
    salida = {}
    for d in range(1, 366):
        vecinos = [((d - 1 + k) % 365) + 1 for k in range(-medio, medio + 1)]
        salida[d] = np.nanpercentile(valores[np.isin(doy, vecinos)], percentil)
    return pd.Series(salida)


def rachas(condicion: np.ndarray) -> list[int]:
    """Longitudes de las rachas de ``True`` consecutivos."""
    c = np.asarray(condicion, dtype=bool)
    if not c.any():
        return []
    bordes = np.diff(np.concatenate([[0], c.astype(int), [0]]))
    inicios = np.flatnonzero(bordes == 1)
    fines = np.flatnonzero(bordes == -1)
    return list(fines - inicios)


def dias_en_rachas(condicion: np.ndarray, minimo: int) -> np.ndarray:
    """Máscara de los días que pertenecen a rachas de al menos ``minimo`` días."""
    c = np.asarray(condicion, dtype=bool)
    salida = np.zeros(len(c), dtype=bool)
    bordes = np.diff(np.concatenate([[0], c.astype(int), [0]]))
    for i, f in zip(np.flatnonzero(bordes == 1), np.flatnonzero(bordes == -1)):
        if f - i >= minimo:
            salida[i:f] = True
    return salida


def indices_ciudad(d: pd.DataFrame) -> pd.DataFrame:
    """Índices anuales de una ciudad (``d``: serie diaria de un solo punto, ordenada y continua)."""
    d = d.sort_values("fecha").reset_index(drop=True)
    doy = dia_del_anio(d["fecha"])
    p90_tx = umbral_percentil(d, "tmax").to_numpy()[doy - 1]
    p90_tn = umbral_percentil(d, "tmin").to_numpy()[doy - 1]
    p95_lluvia = float(umbral_percentil(d, "precip", 95, solo_humedos=True).iloc[0])
    calido = (d["tmax"] > p90_tx).to_numpy()
    noche_calida = (d["tmin"] > p90_tn).to_numpy()
    seco = (d["precip"] < config.UMBRAL_DIA_LLUVIA).to_numpy()
    humedo = ~seco
    precip = d["precip"].to_numpy()
    anio = d["fecha"].dt.year.to_numpy()
    lluvia_5d = pd.Series(precip).rolling(5).sum().to_numpy()

    # Las rachas se calculan sobre toda la serie y luego se asignan al año en que caen sus días
    en_ola = dias_en_rachas(calido, config.DIAS_OLA_CALOR)
    en_wsdi = dias_en_rachas(calido, 6)
    inicio_ola = en_ola & ~np.concatenate([[False], en_ola[:-1]])

    filas = []
    for a in np.unique(anio):
        m = anio == a
        racha_seca = rachas(seco[m])
        filas.append({
            "anio": int(a),
            "tx90p": 100 * calido[m].mean(),
            "tn90p": 100 * noche_calida[m].mean(),
            "dias_ola_calor": int(en_ola[m].sum()),
            "olas_calor": int(inicio_ola[m].sum()),
            "wsdi": int(en_wsdi[m].sum()),
            "prcptot": float(precip[m][humedo[m]].sum()),
            "dias_lluvia": int(humedo[m].sum()),
            "r20mm": int((precip[m] >= config.UMBRAL_LLUVIA_INTENSA).sum()),
            "rx1day": float(precip[m].max()),
            "rx5day": float(np.nanmax(lluvia_5d[m])) if np.isfinite(lluvia_5d[m]).any() else np.nan,
            "r95ptot": float(precip[m][precip[m] > p95_lluvia].sum()),
            "sdii": float(precip[m][humedo[m]].mean()) if humedo[m].any() else 0.0,
            "cdd": int(max(racha_seca, default=0)),
            "rachas_secas_10": int(sum(r >= 10 for r in racha_seca)),
        })
    return pd.DataFrame(filas)


def indices_anuales(diario: pd.DataFrame) -> pd.DataFrame:
    """Índices anuales de todas las ciudades."""
    tablas = []
    for punto, d in diario.groupby("punto"):
        t = indices_ciudad(d)
        t.insert(0, "punto", punto)
        tablas.append(t)
    return pd.concat(tablas, ignore_index=True)


INDICES_CALOR = ["tx90p", "tn90p", "dias_ola_calor", "olas_calor", "wsdi"]
INDICES_LLUVIA = ["prcptot", "dias_lluvia", "r20mm", "rx1day", "rx5day", "r95ptot", "sdii", "cdd", "rachas_secas_10"]
NOMBRES = {
    "tx90p": "Días cálidos (% Tmáx > p90)", "tn90p": "Noches cálidas (% Tmín > p90)",
    "dias_ola_calor": "Días en olas de calor (≥ 3 días)", "olas_calor": "Número de olas de calor",
    "wsdi": "WSDI (días en rachas ≥ 6)", "prcptot": "Lluvia anual en días húmedos (mm)",
    "dias_lluvia": "Días con lluvia ≥ 1 mm", "r20mm": "Días con lluvia intensa (≥ 20 mm)",
    "rx1day": "Lluvia máxima en 1 día (mm)", "rx5day": "Lluvia máxima en 5 días (mm)",
    "r95ptot": "Lluvia en días muy húmedos (> p95, mm)", "sdii": "Intensidad media (mm/día húmedo)",
    "cdd": "Racha seca más larga (días)", "rachas_secas_10": "Rachas secas de ≥ 10 días",
}
