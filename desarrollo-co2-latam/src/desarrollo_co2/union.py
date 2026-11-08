"""
Unión de Banco Mundial + OWID en un panel país-año, variables derivadas y agregado regional.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, limpieza


def unir(bm: pd.DataFrame, owid: pd.DataFrame) -> pd.DataFrame:
    """Unión externa por (iso3, anio). ``validate`` garantiza que no haya filas repetidas."""
    panel = bm.merge(owid, on=["iso3", "anio"], how="outer", validate="one_to_one", indicator="origen")
    panel["origen"] = panel["origen"].map({"both": "ambas", "left_only": "solo_bm", "right_only": "solo_owid"})
    panel.insert(1, "pais", panel["iso3"].map(config.PAISES))
    return panel.sort_values(["iso3", "anio"]).reset_index(drop=True)


def diferencia_poblacion(panel: pd.DataFrame) -> pd.DataFrame:
    """Control cruzado: población del Banco Mundial vs la de OWID (fuente: ONU), en %."""
    d = panel.dropna(subset=["poblacion_bm", "poblacion_owid"]).copy()
    d["dif_pct"] = 100 * (d["poblacion_owid"] / d["poblacion_bm"] - 1)
    return (d.groupby(["iso3", "pais"])["dif_pct"]
            .agg(media="mean", max_abs=lambda s: s.abs().max()).round(2).reset_index()
            .sort_values("max_abs", ascending=False))


def agregar_derivadas(panel: pd.DataFrame) -> pd.DataFrame:
    """Indicadores relativos que se usan en todo el análisis."""
    p = panel.copy()
    pob = p["poblacion_bm"]
    # en los países viene del Banco Mundial; en el agregado regional se calcula
    p["pib_pc_ppa"] = p.get("pib_pc_ppa", pd.Series(np.nan, index=p.index)).fillna(p["pib_ppa"] / pob)
    p["co2_pc_t"] = p["co2_mt"] * 1e6 / pob                       # t por persona
    p["co2_consumo_pc_t"] = p["co2_consumo_mt"] * 1e6 / pob
    p["intensidad_co2_kg_usd"] = p["co2_mt"] * 1e9 / p["pib_ppa"]  # kg CO2 por USD PPA de 2021
    p["energia_pc_mwh"] = p["energia_twh"] * 1e6 / pob
    p["intensidad_energia_kwh_usd"] = p["energia_twh"] * 1e9 / p["pib_ppa"]
    p["carbono_energia_kg_kwh"] = p["co2_mt"] / p["energia_twh"]   # Mt/TWh = kg/kWh
    p["comercio_neto_co2_pct"] = 100 * (p["co2_consumo_mt"] / p["co2_mt"] - 1)  # >0: importa emisiones
    p["petroleo_pct_co2"] = 100 * p["co2_petroleo_mt"] / p["co2_mt"]
    return p.replace([np.inf, -np.inf], np.nan)


def miembros_region(panel: pd.DataFrame, anio_inicio: int = config.ANIO_INICIO,
                    anio_fin: int | None = None, columnas=("pib_ppa", "co2_mt", "poblacion_bm")) -> list[str]:
    """Países con todas las ``columnas`` en todos los años: solo ellos entran al agregado."""
    anio_fin = anio_fin or int(panel["anio"].max())
    rango = panel[panel["anio"].between(anio_inicio, anio_fin)]
    n_anios = anio_fin - anio_inicio + 1
    completos = rango.dropna(subset=list(columnas)).groupby("iso3")["anio"].nunique()
    return sorted(completos[completos == n_anios].index)


def agregado_regional(panel: pd.DataFrame, miembros: list[str]) -> pd.DataFrame:
    """Suma de los países miembros. Si en un año falta un miembro, la suma queda vacía
    (sumar con huecos haría parecer que las emisiones bajan cuando en realidad falta un dato)."""
    sub = panel[panel["iso3"].isin(miembros)]
    cols = [c for c in config.SUMABLES if c in sub]
    region = sub.groupby("anio")[cols].sum(min_count=len(miembros))
    completos = sub.groupby("anio")[cols].count()
    region = region.where(completos == len(miembros))
    region = region.reset_index()
    region.insert(0, "iso3", config.REGION)
    region.insert(1, "pais", config.NOMBRE_REGION)
    return region


def construir_panel(carpeta=config.CRUDOS) -> tuple[pd.DataFrame, dict]:
    """Lee las fuentes en caché, valida, une y agrega. Devuelve el panel y un informe de calidad."""
    bm = limpieza.leer_banco_mundial(carpeta)
    owid = limpieza.leer_owid(carpeta / "owid-co2-data.csv")
    informe = {
        "filas_bm": len(bm), "filas_owid": len(owid),
        "validacion": [limpieza.validar_paises(bm, "Banco Mundial"), limpieza.validar_paises(owid, "OWID")],
    }
    panel = unir(bm, owid)
    informe["origen"] = panel["origen"].value_counts().to_dict()
    informe["diferencia_poblacion"] = diferencia_poblacion(panel)
    miembros = miembros_region(panel)
    informe["miembros_region"] = miembros
    informe["excluidos_region"] = sorted(set(config.PAISES) - set(miembros))
    panel = pd.concat([panel.drop(columns="origen"), agregado_regional(panel, miembros)], ignore_index=True)
    panel = agregar_derivadas(panel)
    return panel, informe
