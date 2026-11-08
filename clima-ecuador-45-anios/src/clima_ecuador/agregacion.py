"""
De bloques horarios en UTC a series diarias, mensuales y regionales en hora local.

1. ``unir_horario``: concatena los Parquet de cada variable (años y trozos), quita el solape entre el último
   year_2021.om y el primer trozo, y deja una tabla larga ``punto × hora_utc``.
2. ``variables_derivadas``: viento a partir de u/v, humedad relativa (Magnus) y corrección de la temperatura por
   la diferencia entre la altitud de la ciudad y la altitud media de la celda de 25 km (gradiente de −6,5 °C/km).
3. ``a_diario``: agrega por día **local** (UTC−5; Galápagos UTC−6). Solo se aceptan días con las 24 horas.
   La lluvia y la radiación de la hora t son lo acumulado en la hora que termina en t, así que el día D las suma
   de 01:00 a 24:00 (la misma convención que la API diaria de Open-Meteo).
4. ``a_mensual`` y ``promedio_regional``.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import config


# ---------------------------------------------------------------------------
# Horario
# ---------------------------------------------------------------------------
def _clave_bloque(ruta: Path) -> tuple[int, int]:
    tipo, numero = ruta.stem.split("_")
    return (0 if tipo == "year" else 1, int(numero))


def leer_variable(variable: str, carpeta: Path = config.ERA5_CRUDO) -> tuple[pd.DataFrame, dict]:
    """Une los bloques de una variable. Devuelve la tabla ancha (hora × punto) y un control del solape."""
    rutas = sorted((carpeta / variable).glob("*.parquet"), key=_clave_bloque)
    if not rutas:
        raise FileNotFoundError(f"No hay bloques de {variable} en {carpeta}: ejecuta descargar_datos.py")
    partes = [pd.read_parquet(r) for r in rutas]
    df = pd.concat(partes)
    repetidas = df.index.duplicated(keep="first")   # el primer trozo de 2022 empieza el 23-12-2021
    solape = df[df.index.duplicated(keep=False)]
    if len(solape):
        a = solape[~solape.index.duplicated(keep="first")]
        b = solape[solape.index.duplicated(keep="first")]
        dif = float(np.nanmax(np.abs(a.to_numpy() - b.loc[a.index].to_numpy())))
    else:
        dif = 0.0
    control = {"variable": variable, "bloques": len(rutas), "horas_solapadas": int(repetidas.sum()),
               "max_dif_solape": round(dif, 4)}
    return df[~repetidas].sort_index(), control


def unir_horario(carpeta: Path = config.ERA5_CRUDO, anio_inicio: int = config.ANIO_INICIO,
                 anio_fin: int = config.ANIO_FIN) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Tabla larga punto × hora_utc con las 7 variables crudas de ERA5 (float32)."""
    largas, controles = [], []
    desde = pd.Timestamp(f"{anio_inicio}-01-01")
    hasta = pd.Timestamp(f"{anio_fin + 1}-01-01 07:00")
    for variable, columna in config.VARIABLES_S3.items():
        ancha, control = leer_variable(variable, carpeta)
        controles.append(control)
        ancha = ancha.loc[(ancha.index >= desde) & (ancha.index < hasta)]
        larga = ancha.rename_axis(columns="punto").stack(future_stack=True).rename(columna)
        largas.append(larga.astype("float32"))
    horario = pd.concat(largas, axis=1).reset_index()
    horario["punto"] = horario["punto"].astype("category")
    return horario, pd.DataFrame(controles)


def humedad_relativa(temp: np.ndarray, punto_rocio: np.ndarray) -> np.ndarray:
    """Humedad relativa (%) con la fórmula de Magnus (Alduchov y Eskridge, 1996)."""
    a, b = 17.625, 243.04
    hr = 100 * np.exp(a * punto_rocio / (b + punto_rocio) - a * temp / (b + temp))
    return np.clip(hr, 0, 100)


def ajuste_altitud(celdas: pd.DataFrame) -> pd.Series:
    """°C que se suman a la temperatura de la celda para llevarla a la altitud del punto."""
    return (config.GRADIENTE_TERMICO * (celdas["altitud"] - celdas["altitud_celda"])).set_axis(celdas["punto"])


def variables_derivadas(horario: pd.DataFrame, celdas: pd.DataFrame) -> pd.DataFrame:
    h = horario.copy()
    h["humedad"] = humedad_relativa(h["temp"].to_numpy(), h["punto_rocio"].to_numpy()).astype("float32")
    h["viento"] = (np.hypot(h["viento_u"], h["viento_v"]) * 3.6).astype("float32")   # km/h, como la API
    h["rafagas"] = (h["rafagas"] * 3.6).astype("float32")
    ajuste = h["punto"].astype(str).map(ajuste_altitud(celdas)).astype("float32")
    h["temp_celda"] = h["temp"]
    h["temp"] = h["temp"] + ajuste
    h["punto_rocio"] = h["punto_rocio"] + ajuste     # se conserva la humedad relativa de la celda
    region = h["punto"].astype(str).map(celdas.set_index("punto")["region"])
    desfase = region.map(config.desfase_utc).astype(int)
    h["hora_local"] = h["hora_utc"] + pd.to_timedelta(desfase, unit="h")
    return h.drop(columns=["viento_u", "viento_v"])


# ---------------------------------------------------------------------------
# Diario, mensual y regional
# ---------------------------------------------------------------------------
def a_diario(horario: pd.DataFrame, anio_inicio: int = config.ANIO_INICIO,
             anio_fin: int = config.ANIO_FIN) -> pd.DataFrame:
    """Agrega por día local. ``radiacion`` pasa de W/m² medios por hora a MJ/m² por día."""
    h = horario.assign(fecha=horario["hora_local"].dt.floor("D"))
    g = h.groupby(["punto", "fecha"], observed=True)
    d = g.agg(tmax=("temp", "max"), tmin=("temp", "min"), tmed=("temp", "mean"),
              tmax_celda=("temp_celda", "max"), tmin_celda=("temp_celda", "min"), tmed_celda=("temp_celda", "mean"),
              humedad=("humedad", "mean"), viento_max=("viento", "max"), rafagas_max=("rafagas", "max"),
              horas=("temp", "count"))
    # Acumuladas: la hora que termina a las 00:00 pertenece al día anterior
    fecha_acum = (horario["hora_local"] - pd.Timedelta(hours=1)).dt.floor("D")
    acum = horario[["punto"] + config.ACUMULADAS].assign(fecha=fecha_acum).groupby(["punto", "fecha"], observed=True)
    suma = acum[config.ACUMULADAS].sum()
    suma["horas_acum"] = acum.size()
    d = d.join(suma)
    d["radiacion"] = d["radiacion"] * 3600 / 1e6
    d = d.reset_index()
    d = d[d["horas_acum"] == 24].drop(columns="horas_acum")
    d = d[(d["horas"] == 24) & d["fecha"].dt.year.between(anio_inicio, anio_fin)]
    d["punto"] = d["punto"].astype(str)
    for c in d.columns.difference(["punto", "fecha", "horas"]):
        d[c] = d[c].astype("float32").round(2)
    return d.drop(columns="horas").reset_index(drop=True)


def a_mensual(diario: pd.DataFrame, min_dias: float = 0.9) -> pd.DataFrame:
    """Medias mensuales (lluvia: suma). Un mes cuenta solo si tiene al menos el 90 % de sus días."""
    d = diario.assign(mes=diario["fecha"].dt.to_period("M").dt.to_timestamp())
    g = d.groupby(["punto", "mes"])
    m = g.agg(tmax=("tmax", "mean"), tmin=("tmin", "mean"), tmed=("tmed", "mean"), precip=("precip", "sum"),
              humedad=("humedad", "mean"), viento_max=("viento_max", "mean"), radiacion=("radiacion", "mean"),
              dias=("tmax", "count")).reset_index()
    completo = m["dias"] >= min_dias * m["mes"].dt.days_in_month
    m.loc[~completo, ["tmax", "tmin", "tmed", "precip", "humedad", "viento_max", "radiacion"]] = np.nan
    return m.drop(columns="dias")


def a_anual(mensual: pd.DataFrame) -> pd.DataFrame:
    """Medias anuales (lluvia: suma) solo con años de 12 meses completos."""
    m = mensual.assign(anio=mensual["mes"].dt.year)
    cols = ["tmax", "tmin", "tmed", "humedad", "viento_max", "radiacion"]
    a = m.groupby(["punto", "anio"])[cols].mean()
    a["precip"] = m.groupby(["punto", "anio"])["precip"].sum(min_count=12)
    completos = m.groupby(["punto", "anio"])["tmed"].count() == 12
    return a[completos].reset_index()


def solo_ciudades(df: pd.DataFrame, columna: str = "punto") -> pd.DataFrame:
    return df[df[columna].isin(config.CIUDADES)].copy()


def con_region(df: pd.DataFrame, columna: str = "punto") -> pd.DataFrame:
    regiones = {c: v[3] for c, v in config.CIUDADES.items()}
    return df.assign(region=df[columna].map(regiones))


def promedio_regional(df: pd.DataFrame, columnas: list[str], tiempo: str) -> pd.DataFrame:
    """Media simple de las ciudades de cada región (cada ciudad pesa igual)."""
    d = con_region(solo_ciudades(df))
    return d.groupby(["region", tiempo])[columnas].mean().reset_index()
