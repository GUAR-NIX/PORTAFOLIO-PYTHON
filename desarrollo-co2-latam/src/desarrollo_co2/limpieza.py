"""
Lectura y limpieza de las dos fuentes hasta un formato común: una fila por país (ISO3) y año.

Decisiones:
* La llave es el código ISO 3166-1 alfa-3, nunca el nombre: el Banco Mundial dice
  "Venezuela, RB" y OWID "Venezuela"; con nombres la unión perdería filas sin avisar.
* Los valores faltantes NO se imputan. Se documentan en una tabla de cobertura
  (qué años faltan por país y variable) y cada análisis decide qué hacer con ellos.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import config


# ---------------------------------------------------------------------------
# Banco Mundial
# ---------------------------------------------------------------------------
def leer_bm_json(ruta: Path | str) -> pd.DataFrame:
    """JSON crudo de la API v2 -> tabla larga (iso3, anio, indicador, valor)."""
    registros = json.loads(Path(ruta).read_text(encoding="utf-8"))
    filas = [{
        "iso3": r["countryiso3code"],
        "anio": int(r["date"]),
        "indicador": r["indicator"]["id"],
        "valor": r["value"],
    } for r in registros]
    df = pd.DataFrame(filas, columns=["iso3", "anio", "indicador", "valor"])
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    return df


def bm_a_ancho(largo: pd.DataFrame, nombres: dict[str, str] = config.INDICADORES_BM) -> pd.DataFrame:
    """Tabla larga -> una columna por indicador, con los nombres del panel."""
    duplicados = largo.duplicated(["iso3", "anio", "indicador"]).sum()
    if duplicados:
        raise ValueError(f"{duplicados} filas repetidas (iso3, anio, indicador) en el Banco Mundial")
    ancho = (largo.pivot(index=["iso3", "anio"], columns="indicador", values="valor")
             .rename(columns=nombres).reset_index())
    ancho.columns.name = None
    for col in nombres.values():  # un indicador sin ningún dato igual debe existir como columna
        if col not in ancho:
            ancho[col] = float("nan")
    return ancho[["iso3", "anio", *nombres.values()]]


def leer_banco_mundial(carpeta: Path = config.CRUDOS) -> pd.DataFrame:
    largo = pd.concat([leer_bm_json(carpeta / f"bm_{c}.json") for c in config.INDICADORES_BM],
                      ignore_index=True)
    return bm_a_ancho(largo)


# ---------------------------------------------------------------------------
# Our World in Data
# ---------------------------------------------------------------------------
def leer_owid(ruta: Path | str = config.CRUDOS / "owid-co2-data.csv", paises: list[str] | None = None,
              anio_inicio: int = config.ANIO_INICIO, anio_fin: int = config.ANIO_FIN) -> pd.DataFrame:
    """CSV de OWID -> solo los países y años del estudio, columnas renombradas.

    OWID mezcla países con agregados (World, South America…) que no tienen iso_code: se descartan
    al filtrar por la lista de ISO3.
    """
    paises = paises or list(config.PAISES)
    owid = pd.read_csv(ruta, usecols=["iso_code", "year", *config.COLUMNAS_OWID])
    owid = owid[owid["iso_code"].isin(paises) & owid["year"].between(anio_inicio, anio_fin)]
    owid = owid.rename(columns={"iso_code": "iso3", "year": "anio", **config.COLUMNAS_OWID})
    owid["iso3"] = owid["iso3"].astype(str)
    return completar_combustibles(owid.reset_index(drop=True))


COMBUSTIBLES = ["co2_petroleo_mt", "co2_gas_mt", "co2_carbon_mt", "co2_cemento_mt", "co2_quema_mt"]


def completar_combustibles(owid: pd.DataFrame, tolerancia: float = 0.02) -> pd.DataFrame:
    """OWID deja vacío el CO2 de un combustible que el país no usa (p. ej. gas en Nicaragua).

    Única excepción a "no imputar": se pone 0 **solo** cuando las fuentes que sí tienen dato ya
    suman el CO2 total (±2 %), es decir, cuando el vacío es lógicamente un cero. Sin esto, el
    agregado regional por combustible quedaría vacío y las participaciones saldrían mal.
    """
    o = owid.copy()
    suma = o[COMBUSTIBLES].sum(axis=1, min_count=1)
    cuadra = (suma - o["co2_mt"]).abs() <= tolerancia * o["co2_mt"]
    o.loc[cuadra, COMBUSTIBLES] = o.loc[cuadra, COMBUSTIBLES].fillna(0)
    return o


# ---------------------------------------------------------------------------
# Validaciones y cobertura
# ---------------------------------------------------------------------------
def validar_paises(df: pd.DataFrame, fuente: str, paises: list[str] | None = None) -> dict:
    """Comprueba que los ISO3 de una fuente coincidan con la lista del estudio."""
    esperados = set(paises or config.PAISES)
    presentes = set(df["iso3"].unique())
    return {
        "fuente": fuente,
        "faltan": sorted(esperados - presentes),
        "sobran": sorted(presentes - esperados),
        "ok": presentes == esperados,
    }


def rangos_compactos(anios) -> str:
    """[1990, 1991, 1992, 1995] -> '1990–1992, 1995'."""
    anios = sorted({int(a) for a in anios})
    if not anios:
        return ""
    tramos, inicio, previo = [], anios[0], anios[0]
    for a in anios[1:]:
        if a != previo + 1:
            tramos.append((inicio, previo))
            inicio = a
        previo = a
    tramos.append((inicio, previo))
    return ", ".join(str(i) if i == f else f"{i}–{f}" for i, f in tramos)


def cobertura(panel: pd.DataFrame, columnas: list[str], anio_inicio: int = config.ANIO_INICIO,
              anio_fin: int | None = None) -> pd.DataFrame:
    """Para cada variable y país: años con dato, primer/último año y años faltantes en el rango."""
    anio_fin = anio_fin or int(panel["anio"].max())
    rango = set(range(anio_inicio, anio_fin + 1))
    filas = []
    for col in columnas:
        for iso3, g in panel.groupby("iso3"):
            con_dato = set(g.loc[g[col].notna(), "anio"].astype(int)) & rango
            filas.append({
                "variable": col, "iso3": iso3, "anios_con_dato": len(con_dato),
                "pct_completo": round(100 * len(con_dato) / len(rango), 1),
                "primer_anio": min(con_dato) if con_dato else None,
                "ultimo_anio": max(con_dato) if con_dato else None,
                "anios_faltantes": rangos_compactos(rango - con_dato),
            })
    return pd.DataFrame(filas)


def resumen_cobertura(cob: pd.DataFrame) -> pd.DataFrame:
    """Una fila por variable: cuántos países completos, parciales y sin ningún dato."""
    return (cob.assign(estado=pd.cut(cob["pct_completo"], [-1, 0, 99.9, 100],
                                     labels=["sin datos", "parcial", "completo"]))
            .pivot_table(index="variable", columns="estado", values="iso3", aggfunc="count", observed=False)
            .reindex(columns=["completo", "parcial", "sin datos"]).fillna(0).astype(int)
            .assign(pct_medio=cob.groupby("variable")["pct_completo"].mean().round(1)))
