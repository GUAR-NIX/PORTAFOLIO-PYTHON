"""
Calidad del catálogo y homogeneización de magnitudes.

Problemas reales del catálogo del USGS que se resuelven aquí:

* **Varias escalas de magnitud.** ComCat mezcla Mw (mww, mwc, mwb, mwr…), mb (ondas de cuerpo), Ms (ondas
  superficiales) y magnitudes locales (ml, md) de redes regionales. mb y Ms **no** equivalen a Mw: mb se
  satura cerca de 6 y subestima/sobreestima según el rango. Se convierten a Mw con las relaciones globales
  de Scordilis (2006), ajustadas con datos del ISC y del NEIC:

      Mw = 0,85·mb + 1,03            (3,5 ≤ mb ≤ 6,2)
      Mw = 0,67·Ms + 2,07            (3,0 ≤ Ms ≤ 6,1)
      Mw = 0,99·Ms + 0,08            (6,2 ≤ Ms ≤ 8,2)

  Las magnitudes locales (ml, md) y las de tipo desconocido se toman como Mw ≈ M (supuesto documentado:
  no hay una relación publicada para cada red). Fuera del rango de validez se aplica la recta más cercana
  y el evento queda marcado.
* **Duplicados**: por ``id`` (fronteras de las páginas) y "casi duplicados" (dos ``id`` a < 16 s y < 50 km,
  el mismo sismo reportado por dos redes); se conserva el de mejor magnitud (Mw > Ms > mb > local).
* **Profundidad**: eventos sin profundidad y eventos con profundidad **fija** (10, 33 o 35 km, valores que
  pone el localizador cuando no la puede resolver) se marcan; no se imputan.
* Se dejan solo ``type == earthquake`` (se quitan explosiones, voladuras de canteras, etc.).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .geo import distancia_km

FAMILIA_MW = "Mw"
PRIORIDAD = {"Mw": 0, "Ms": 1, "mb": 2, "Local": 3, "Desconocida": 4}
PROFUNDIDADES_FIJAS = (10.0, 33.0, 35.0)


def familia_magnitud(tipo: str | float) -> str:
    t = str(tipo).strip().lower() if isinstance(tipo, str) else ""
    if t.startswith("mw") or t in {"mi", "mint"}:
        return "Mw"
    if t in {"mb"}:
        return "mb"
    if t.startswith("ms"):
        return "Ms"
    if t in {"ml", "md", "mlr", "mlv", "mc", "mh", "mlg", "mb_lg", "lg", "mn", "mlh"}:
        return "Local"
    return "Desconocida"


def a_mw(mag: pd.Series, familia: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Magnitud homogénea Mw y bandera de 'conversión fuera del rango de validez'."""
    mag = mag.astype(float)
    mw = mag.copy()
    fuera = pd.Series(False, index=mag.index)

    es_mb = familia == "mb"
    mw[es_mb] = 0.85 * mag[es_mb] + 1.03
    fuera |= es_mb & ((mag < 3.5) | (mag > 6.2))

    es_ms = familia == "Ms"
    bajo = es_ms & (mag <= 6.15)
    alto = es_ms & (mag > 6.15)
    mw[bajo] = 0.67 * mag[bajo] + 2.07
    mw[alto] = 0.99 * mag[alto] + 0.08
    fuera |= es_ms & ((mag < 3.0) | (mag > 8.2))
    return mw, fuera


def casi_duplicados(df: pd.DataFrame, segundos: float = 16, km: float = 50) -> pd.Index:
    """Índices de eventos que repiten a otro (mismo sismo con otro ``id``). Conserva el de mejor magnitud."""
    d = df.sort_values("tiempo")
    t = (d["tiempo"] - pd.Timestamp("1900-01-01", tz="UTC")).dt.total_seconds().to_numpy()
    lat, lon = d["latitud"].to_numpy(), d["longitud"].to_numpy()
    prioridad = d["familia_mag"].map(PRIORIDAD).to_numpy()
    indices = d.index.to_numpy()
    quitar = set()
    for i in range(len(d) - 1):
        j = i + 1
        while j < len(d) and t[j] - t[i] <= segundos:
            if indices[i] not in quitar and indices[j] not in quitar and \
                    distancia_km(lat[i], lon[i], lat[j], lon[j]) <= km:
                quitar.add(indices[j] if prioridad[j] >= prioridad[i] else indices[i])
            j += 1
    return pd.Index(sorted(quitar))


def limpiar(crudo: pd.DataFrame, dm: float = 0.1, semilla: int = 42) -> tuple[pd.DataFrame, dict]:
    """Catálogo crudo del USGS → catálogo limpio con Mw homogénea + informe de calidad."""
    informe: dict = {"filas_crudas": int(len(crudo))}
    df = crudo.drop_duplicates("id").copy()
    informe["duplicados_por_id"] = int(len(crudo) - len(df))

    tipos = df["type"].fillna("desconocido").value_counts()
    informe["tipos_evento"] = {k: int(v) for k, v in tipos.items()}
    df = df[df["type"] == "earthquake"].copy()

    df = df.rename(columns={"time": "tiempo", "latitude": "latitud", "longitude": "longitud",
                            "depth": "profundidad_km", "mag": "mag_original", "magType": "tipo_mag",
                            "place": "lugar", "depthError": "error_profundidad",
                            "horizontalError": "error_horizontal", "magError": "error_mag"})
    df["tiempo"] = pd.to_datetime(df["tiempo"], utc=True, format="ISO8601")
    df["tipo_mag"] = df["tipo_mag"].fillna("desconocido").str.lower()
    df["familia_mag"] = df["tipo_mag"].map(familia_magnitud)

    sin_mag = df["mag_original"].isna()
    informe["sin_magnitud"] = int(sin_mag.sum())
    df = df[~sin_mag].copy()

    # "Dithering": mb y Ms vienen redondeados a 0,1; al multiplicarlos por 0,85 o 0,67 dos valores de mb
    # caen en la misma clase de Mw cada pocos pasos y aparecen picos falsos en el histograma (que engañan
    # a la máxima curvatura). Se reparte cada magnitud dentro de su clase de reporte (±0,05) antes de
    # convertir, con semilla fija.
    rng = np.random.default_rng(semilla)
    ruido = rng.uniform(-dm / 2, dm / 2, len(df))
    mw, fuera = a_mw(df["mag_original"] + ruido, df["familia_mag"])
    df["mw_continua"] = mw
    # Se redondea a la clase de 0,1 para Mc y el valor b (se suma 1e-9 para no depender del redondeo bancario)
    df["mw"] = np.round(np.floor(mw / dm + 0.5 + 1e-9) * dm, 1)
    df["conversion_fuera_de_rango"] = fuera

    casi = casi_duplicados(df)
    informe["casi_duplicados"] = int(len(casi))
    df = df.drop(index=casi)

    sin_prof = df["profundidad_km"].isna()
    fija = df["profundidad_km"].isin(PROFUNDIDADES_FIJAS) & \
        (df["error_profundidad"].isna() | (df["error_profundidad"] == 0))
    df["profundidad_fija"] = fija
    informe["sin_profundidad"] = int(sin_prof.sum())
    informe["profundidad_fija"] = int(fija.sum())
    informe["profundidad_fija_pct"] = round(100 * fija.mean(), 1) if len(df) else 0.0
    df["clase_profundidad"] = pd.cut(df["profundidad_km"], [-10, 70, 300, 800],
                                     labels=["Superficial (<70 km)", "Intermedia (70–300 km)",
                                             "Profunda (>300 km)"])

    fam = df["familia_mag"].value_counts()
    informe["familias_magnitud"] = {k: int(v) for k, v in fam.items()}
    informe["tipos_magnitud_top"] = {k: int(v) for k, v in df["tipo_mag"].value_counts().head(12).items()}
    informe["conversion_fuera_de_rango"] = int(fuera.loc[df.index].sum())
    informe["cambio_medio_mb_a_mw"] = _cambio_medio(df, "mb")
    informe["cambio_medio_ms_a_mw"] = _cambio_medio(df, "Ms")
    informe["filas_limpias"] = int(len(df))
    informe["anio_min"] = int(df["tiempo"].dt.year.min()) if len(df) else None
    informe["anio_max"] = int(df["tiempo"].dt.year.max()) if len(df) else None

    df["anio"] = df["tiempo"].dt.year
    columnas = ["id", "tiempo", "anio", "latitud", "longitud", "profundidad_km", "profundidad_fija",
                "clase_profundidad", "mag_original", "tipo_mag", "familia_mag", "mw", "mw_continua",
                "conversion_fuera_de_rango", "error_profundidad", "error_horizontal", "error_mag",
                "net", "status", "lugar"]
    return df[columnas].sort_values("tiempo").reset_index(drop=True), informe


def _cambio_medio(df: pd.DataFrame, familia: str) -> float | None:
    sel = df["familia_mag"] == familia
    if not sel.any():
        return None
    return round(float((df.loc[sel, "mw_continua"] - df.loc[sel, "mag_original"]).mean()), 3)


def asignar_zona(df: pd.DataFrame, zonas: dict[str, tuple[float, float, float, float]]) -> pd.Series:
    """Nombre de la zona del Cinturón (o NaN) según cajas lat/lon que no se solapan."""
    zona = pd.Series(pd.NA, index=df.index, dtype="object")
    for nombre, (la0, la1, lo0, lo1) in zonas.items():
        dentro = df["latitud"].between(la0, la1) & df["longitud"].between(lo0, lo1) & zona.isna()
        zona[dentro] = nombre
    return zona
