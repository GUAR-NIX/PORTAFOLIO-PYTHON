"""
Desacople entre crecimiento económico (PIB real, PPA) y emisiones de CO2.

Clasificación (convención OCDE, con la elasticidad de Tapio como medida continua):

* **Absoluto**: el PIB crece y el CO2 baja.
* **Relativo**: ambos crecen, pero el CO2 más despacio que el PIB (baja la intensidad).
* **Sin desacople**: el CO2 crece igual o más rápido que el PIB.
* **Recesión**: el PIB no creció en el periodo; bajar emisiones así no es desacople.

Para que un año atípico no decida la etiqueta, el valor inicial y el final son promedios de
``config.VENTANA_EXTREMOS`` años (p. ej. 2000–2002 y 2022–2024).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def tasa_anual(inicial: float, final: float, anios: float) -> float:
    """Tasa de crecimiento anual compuesta, en %."""
    if anios <= 0 or not np.isfinite(inicial) or not np.isfinite(final) or inicial <= 0 or final <= 0:
        return np.nan
    return 100 * ((final / inicial) ** (1 / anios) - 1)


def clasificar(crec_pib: float, crec_co2: float) -> str:
    """Etiqueta de desacople a partir de las tasas de crecimiento (cualquier unidad común)."""
    if not (np.isfinite(crec_pib) and np.isfinite(crec_co2)):
        return "Sin datos"
    if crec_pib <= 0:
        return "Recesión"
    if crec_co2 < 0:
        return "Absoluto"
    if crec_co2 < crec_pib:
        return "Relativo"
    return "Sin desacople"


def elasticidad(crec_pib: float, crec_co2: float) -> float:
    """Elasticidad de Tapio: %ΔCO2 / %ΔPIB. <0 absoluto, 0–0,8 relativo, ~1 acoplado."""
    if not (np.isfinite(crec_pib) and np.isfinite(crec_co2)) or crec_pib == 0:
        return np.nan
    return crec_co2 / crec_pib


TAPIO = [
    "Desacople fuerte", "Desacople débil", "Acoplamiento expansivo", "Desacople negativo expansivo",
    "Desacople recesivo", "Acoplamiento recesivo", "Desacople negativo débil", "Desacople negativo fuerte",
]


def clasificar_tapio(crec_pib: float, crec_co2: float) -> str:
    """Los 8 estados de Tapio (2005): usa bandas de elasticidad 0,8–1,2 como "acoplado",
    así un país con elasticidad 0,95 no queda como "desacoplado" por una décima."""
    if not (np.isfinite(crec_pib) and np.isfinite(crec_co2)) or crec_pib == 0:
        return "Sin datos"
    e = crec_co2 / crec_pib
    if crec_pib > 0:
        if crec_co2 < 0:
            return "Desacople fuerte"
        return "Desacople débil" if e < 0.8 else ("Acoplamiento expansivo" if e <= 1.2 else "Desacople negativo expansivo")
    if crec_co2 > 0:
        return "Desacople negativo fuerte"
    return "Desacople recesivo" if e > 1.2 else ("Acoplamiento recesivo" if e >= 0.8 else "Desacople negativo débil")


def _promedio_ventana(serie: pd.Series, desde: int, hasta: int) -> float:
    """Promedio de los años [desde, hasta]; exige que estén todos (si no, NaN)."""
    tramo = serie.reindex(range(desde, hasta + 1))
    return float(tramo.mean()) if tramo.notna().all() else np.nan


def extremos(serie: pd.Series, inicio: int, fin: int, ventana: int = config.VENTANA_EXTREMOS) -> tuple[float, float]:
    """Valor inicial (primeros ``ventana`` años) y final (últimos ``ventana`` años) del periodo."""
    return (_promedio_ventana(serie, inicio, inicio + ventana - 1),
            _promedio_ventana(serie, fin - ventana + 1, fin))


def tabla_desacople(panel: pd.DataFrame, inicio: int = config.PERIODO_DESACOPLE[0],
                    fin: int = config.PERIODO_DESACOPLE[1], col_co2: str = "co2_mt", col_pib: str = "pib_ppa",
                    ventana: int = config.VENTANA_EXTREMOS) -> pd.DataFrame:
    """Una fila por país (y la región) con tasas, elasticidad y clasificación del periodo."""
    # años entre los centros de las dos ventanas: es el horizonte real de la tasa
    anios = (fin - (ventana - 1) / 2) - (inicio + (ventana - 1) / 2)
    filas = []
    for (iso3, pais), g in panel.groupby(["iso3", "pais"], sort=False):
        g = g.set_index("anio")
        pib0, pib1 = extremos(g[col_pib], inicio, fin, ventana)
        co20, co21 = extremos(g[col_co2], inicio, fin, ventana)
        cp, cc = tasa_anual(pib0, pib1, anios), tasa_anual(co20, co21, anios)
        filas.append({
            "iso3": iso3, "pais": pais,
            "crec_pib_anual": cp, "crec_co2_anual": cc,
            "cambio_pib_pct": 100 * (pib1 / pib0 - 1) if pib0 else np.nan,
            "cambio_co2_pct": 100 * (co21 / co20 - 1) if co20 else np.nan,
            "cambio_intensidad_pct": 100 * ((co21 / pib1) / (co20 / pib0) - 1) if pib0 and pib1 else np.nan,
            "elasticidad": elasticidad(cp, cc),
            "categoria": clasificar(cp, cc),
            "tapio": clasificar_tapio(cp, cc),
        })
    t = pd.DataFrame(filas)
    t["categoria"] = pd.Categorical(t["categoria"], config.CATEGORIAS_DESACOPLE)
    return t.sort_values(["categoria", "crec_co2_anual"]).reset_index(drop=True)


def conteo_categorias(tabla: pd.DataFrame, excluir_region: bool = True) -> pd.Series:
    t = tabla[tabla["iso3"] != config.REGION] if excluir_region else tabla
    return t["categoria"].value_counts().reindex(config.CATEGORIAS_DESACOPLE, fill_value=0)


def comparar_medidas(panel: pd.DataFrame, inicio: int, fin: int,
                     medidas: dict[str, str] | None = None) -> pd.DataFrame:
    """Clasificación del mismo periodo con distintas medidas de CO2 (prueba de robustez)."""
    medidas = medidas or {"Territorial": "co2_mt", "Consumo": "co2_consumo_mt", "Con uso de suelo": "co2_con_luc_mt"}
    cols = {nombre: tabla_desacople(panel, inicio, fin, col_co2=col).set_index(["iso3", "pais"])["categoria"]
            for nombre, col in medidas.items()}
    return pd.DataFrame(cols).reset_index()


def desacople_movil(panel: pd.DataFrame, ventana_anios: int = config.VENTANA_MOVIL,
                    col_co2: str = "co2_mt") -> pd.DataFrame:
    """Clasificación de cada país en ventanas móviles de ``ventana_anios`` (sin promedios en los extremos)."""
    anio_max = int(panel.dropna(subset=[col_co2, "pib_ppa"])["anio"].max())
    anio_min = int(panel["anio"].min())
    sub = panel[panel["iso3"] != config.REGION]
    filas = []
    for fin in range(anio_min + ventana_anios, anio_max + 1):
        t = tabla_desacople(sub, fin - ventana_anios, fin, col_co2=col_co2, ventana=1)
        for _, f in t.iterrows():
            filas.append({"fin": fin, "iso3": f["iso3"], "pais": f["pais"], "categoria": f["categoria"]})
    return pd.DataFrame(filas)


def serie_indice(panel: pd.DataFrame, iso3: str, base: int,
                 columnas=("pib_ppa", "co2_mt", "poblacion_bm", "intensidad_co2_kg_usd")) -> pd.DataFrame:
    """Series del país indexadas a 100 en el año ``base``."""
    g = panel[panel["iso3"] == iso3].set_index("anio")[list(columnas)]
    return 100 * g / g.loc[base]
