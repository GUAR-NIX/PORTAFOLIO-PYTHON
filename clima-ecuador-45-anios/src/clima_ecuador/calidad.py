"""
Controles de calidad de la serie horaria y diaria.

Un reanálisis no tiene "sensores rotos", pero la cadena de descarga sí puede fallar: horas que faltan, bloques
mal alineados en el tiempo, unidades equivocadas, celdas cambiadas. Cada control devuelve una tabla y el pipeline
falla si un control crítico no pasa.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

RANGOS = {  # límites físicos plausibles para Ecuador (horario)
    "temp": (-15, 45), "punto_rocio": (-40, 35), "precip": (0, 150), "radiacion": (0, 1400),
    "viento": (0, 200), "rafagas": (0, 300), "humedad": (0, 100),
}


def completitud(horario: pd.DataFrame, anio_inicio: int = config.ANIO_INICIO,
                anio_fin: int = config.ANIO_FIN) -> pd.DataFrame:
    """Horas presentes y valores faltantes por punto y variable frente a las horas esperadas."""
    esperadas = int((pd.Timestamp(f"{anio_fin + 1}-01-01 07:00") - pd.Timestamp(f"{anio_inicio}-01-01"))
                    / pd.Timedelta(hours=1))
    cols = [c for c in RANGOS if c in horario]
    g = horario.groupby("punto", observed=True)
    t = g[cols].count()
    t.columns = [f"n_{c}" for c in cols]
    t.insert(0, "horas", g.size())
    t.insert(1, "horas_esperadas", esperadas)
    # El viento puede tener horas anuladas a propósito (picos espurios): se reporta aparte
    t["pct_completo"] = 100 * t[[f"n_{c}" for c in cols if c != "viento"]].min(axis=1) / esperadas
    t["pct_viento"] = 100 * t["n_viento"] / esperadas if "viento" in cols else np.nan
    return t.reset_index()


def huecos_tiempo(horario: pd.DataFrame) -> pd.DataFrame:
    """Saltos distintos de 1 hora y marcas de tiempo repetidas dentro de cada punto."""
    filas = []
    for punto, d in horario.groupby("punto", observed=True):
        t = d["hora_utc"].sort_values()
        pasos = t.diff().dropna()
        filas.append({"punto": punto, "duplicadas": int(t.duplicated().sum()),
                      "saltos": int((pasos != pd.Timedelta(hours=1)).sum())})
    return pd.DataFrame(filas)


def fuera_de_rango(horario: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for c, (bajo, alto) in RANGOS.items():
        if c in horario:
            v = horario[c]
            filas.append({"variable": c, "minimo": float(v.min()), "maximo": float(v.max()),
                          "limite_bajo": bajo, "limite_alto": alto,
                          "fuera": int(((v < bajo) | (v > alto)).sum())})
    return pd.DataFrame(filas)


def filtrar_viento_espurio(horario: pd.DataFrame, margen: float = 20.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Anula el viento de las horas en que supera a la ráfaga máxima de esa misma hora en más de ``margen`` km/h.

    El viento medio no puede ser mayor que la ráfaga: son picos espurios de las componentes u/v de ERA5
    (llegan a 250 km/h en Guayaquil con ráfagas de 17 km/h). Devuelve la tabla corregida y las horas anuladas.
    """
    malo = horario["viento"] > horario["rafagas"] + margen
    anuladas = horario.loc[malo, ["punto", "hora_utc", "viento", "rafagas"]].copy()
    corregido = horario.copy()
    corregido.loc[malo, "viento"] = np.nan
    return corregido, anuladas


def valores_pegados(horario: pd.DataFrame, columna: str = "temp", horas: int = 24) -> pd.DataFrame:
    """Rachas de ≥ ``horas`` horas con el mismo valor (síntoma típico de datos de relleno)."""
    filas = []
    for punto, d in horario.groupby("punto", observed=True):
        v = d.sort_values("hora_utc")[columna].to_numpy()
        cambio = np.concatenate([[True], v[1:] != v[:-1]])
        grupos = np.cumsum(cambio)
        largos = np.bincount(grupos)
        filas.append({"punto": punto, "rachas_pegadas": int((largos >= horas).sum())})
    return pd.DataFrame(filas)


def alineacion_horaria(horario: pd.DataFrame) -> pd.DataFrame:
    """Radiación media por hora local: debe ser ~0 de noche y máxima cerca del mediodía solar.

    Si la conversión de UTC a hora local estuviera mal, el pico se movería de hora.
    """
    h = horario.assign(hora=horario["hora_local"].dt.hour)
    media = h.groupby(["punto", "hora"], observed=True)["radiacion"].mean().unstack()
    return pd.DataFrame({"punto": media.index, "hora_pico": media.idxmax(axis=1).to_numpy(),
                         "radiacion_00h": media[0].to_numpy().round(2),
                         "radiacion_pico": media.max(axis=1).to_numpy().round(1)})


def consistencia_diaria(diario: pd.DataFrame) -> pd.DataFrame:
    """Tmín ≤ Tmed ≤ Tmáx, lluvia ≥ 0 y días esperados por punto."""
    esperados = (pd.Timestamp(f"{config.ANIO_FIN}-12-31") - pd.Timestamp(f"{config.ANIO_INICIO}-01-01")).days + 1
    g = diario.groupby("punto")
    t = pd.DataFrame({
        "dias": g.size(), "dias_esperados": esperados,
        "tmin_mayor_tmed": g.apply(lambda d: int((d["tmin"] > d["tmed"] + 1e-6).sum())),
        "tmed_mayor_tmax": g.apply(lambda d: int((d["tmed"] > d["tmax"] + 1e-6).sum())),
        "lluvia_negativa": g.apply(lambda d: int((d["precip"] < 0).sum())),
    })
    return t.reset_index()


def comparar_con_api(diario: pd.DataFrame, muestra: pd.DataFrame) -> pd.DataFrame:
    """Diferencias entre la agregación propia (celda cruda) y la API diaria de Open-Meteo (``elevation=nan``)."""
    pares = {"tmed_celda": "temperature_2m_mean", "tmax_celda": "temperature_2m_max", "tmin_celda": "temperature_2m_min",
             "precip": "precipitation_sum", "humedad": "relative_humidity_2m_mean",
             "viento_max": "wind_speed_10m_max", "radiacion": "shortwave_radiation_sum"}
    m = diario.merge(muestra, left_on=["punto", "fecha"], right_on=["ciudad", "fecha"], how="inner")
    filas = []
    for propio, api in pares.items():
        dif = (m[propio] - m[api]).dropna()
        filas.append({"variable": propio, "variable_api": api, "dias": len(dif),
                      "dif_media": float(dif.mean()), "dif_abs_media": float(dif.abs().mean()),
                      "dif_abs_p99": float(dif.abs().quantile(0.99)), "correlacion": float(m[propio].corr(m[api]))})
    return pd.DataFrame(filas)


def resumen(controles: dict[str, pd.DataFrame]) -> dict:
    """Resumen de una línea por control (para el JSON de resultados y el notebook)."""
    r = {}
    if "completitud" in controles:
        r["pct_completo_min"] = float(controles["completitud"]["pct_completo"].min())
    if "huecos" in controles:
        r["saltos"] = int(controles["huecos"]["saltos"].sum())
        r["duplicadas"] = int(controles["huecos"]["duplicadas"].sum())
    if "rangos" in controles:
        r["fuera_de_rango"] = int(controles["rangos"]["fuera"].sum())
    if "pegados" in controles:
        r["rachas_pegadas"] = int(controles["pegados"]["rachas_pegadas"].sum())
    if "alineacion" in controles:
        a = controles["alineacion"]
        r["hora_pico_radiacion"] = sorted(set(int(h) for h in a["hora_pico"]))
        r["radiacion_medianoche_max"] = float(a["radiacion_00h"].max())
    if "viento_espurio" in controles:
        v = controles["viento_espurio"]
        r["viento_espurio_horas"] = int(len(v))
        r["viento_espurio_pct"] = float(100 * len(v) / max(controles["completitud"]["horas"].sum(), 1)) \
            if "completitud" in controles else None
        r["viento_espurio_horas_utc"] = v["hora_utc"].dt.hour.value_counts().head(3).to_dict()
    if "consistencia" in controles:
        c = controles["consistencia"]
        r["inconsistencias_diarias"] = int(c[["tmin_mayor_tmed", "tmed_mayor_tmax", "lluvia_negativa"]].sum().sum())
    return r
