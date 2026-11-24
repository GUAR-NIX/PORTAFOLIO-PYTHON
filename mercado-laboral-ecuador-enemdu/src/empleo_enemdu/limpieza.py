"""Limpieza, tipado, variables derivadas oficiales INEC y unión persona-hogar (ENEMDU 2025)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from empleo_enemdu.config import (
    AREAS,
    CONDACT_ETIQUETAS,
    DIR_MUESTRA,
    DIR_PROCESADOS,
    DIR_RAW,
    GRUPO_OCUPACION,
    NIVEL_INSTRUCCION,
    P15_A_ETNIA,
    PROVINCIA_A_REGION_INEC,
    PROVINCIAS,
    RAMA_ACTIVIDAD,
    SECEMP_ETIQUETAS,
    SEXO,
)

COLUMNAS_PERSONAS_RAW = [
    "area",
    "ciudad",
    "prov",
    "dominio",
    "estrato",
    "upm",
    "fexp",
    "p02",
    "p03",
    "p05a",
    "p06",
    "p10a",
    "p10b",
    "p15",
    "p24",
    "p37",
    "p42",
    "p51a",
    "nnivins",
    "ingrl",
    "ingpc",
    "condact",
    "empleo",
    "desempleo",
    "secemp",
    "grupo1",
    "rama1",
    "pobreza",
    "epobreza",
    "id_vivienda",
    "id_hogar",
    "id_persona",
    "periodo",
    "mes",
]


def _a_numerico(serie: pd.Series) -> pd.Series:
    """Convierte cadenas con coma decimal o espacios en blanco a float64."""
    if pd.api.types.is_numeric_dtype(serie):
        return serie.astype(np.float64)
    limpia = (
        serie.astype(str)
        .str.strip()
        .replace({"": np.nan, "nan": np.nan, "None": np.nan})
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(limpia, errors="coerce")


def calcular_escolaridad_egb(p10a: pd.Series, p10b: pd.Series) -> pd.Series:
    """Calcula años de escolaridad homologados a EGB (fórmula oficial INEC tabulados)."""
    a = p10a.to_numpy(dtype=np.float64)
    b = np.nan_to_num(p10b.to_numpy(dtype=np.float64), nan=0.0)
    esc = np.select(
        [
            a == 1,
            a == 2,
            a == 3,
            a == 4,
            a == 5,
            a == 6,
            a == 7,
            a == 8,
            a == 9,
            a == 10,
        ],
        [
            0.0,
            b,
            0.0,
            1.0 + b,
            b,
            7.0 + b,
            10.0 + b,
            13.0 + b,
            13.0 + b,
            18.0 + b,
        ],
        default=np.nan,
    )
    return pd.Series(esc, index=p10a.index, dtype=np.float64)


def calcular_escolaridad_clasica(p10a: pd.Series, p10b: pd.Series) -> pd.Series:
    """Calcula años de escolaridad en escala clásica Mincer (primaria=6, secundaria=12, univ=17)."""
    a = p10a.to_numpy(dtype=np.float64)
    b = np.nan_to_num(p10b.to_numpy(dtype=np.float64), nan=0.0)
    esc = np.select(
        [
            a == 1,
            a == 2,
            a == 3,
            a == 4,
            a == 5,
            a == 6,
            a == 7,
            a == 8,
            a == 9,
            a == 10,
        ],
        [
            0.0,
            b,
            0.0,
            b,
            np.maximum(b - 1.0, 0.0),
            6.0 + b,
            9.0 + b,
            12.0 + b,
            12.0 + b,
            17.0 + b,
        ],
        default=np.nan,
    )
    return pd.Series(esc, index=p10a.index, dtype=np.float64)


def cargar_y_limpiar_microdatos(
    dir_raw: Path = DIR_RAW,
    anio: int = 2025,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Carga microdatos de personas y vivienda del año indicado, aplica reglas de limpieza y audita centinelas."""
    ruta_personas = dir_raw / f"BDDenemdu_personas_{anio}_anual.csv"
    ruta_vivienda = dir_raw / f"BDDenemdu_vivienda_{anio}_anual.csv"

    df = pd.read_csv(
        ruta_personas,
        sep=";",
        usecols=COLUMNAS_PERSONAS_RAW,
        dtype={"estrato": str, "upm": str, "id_vivienda": str, "id_hogar": str, "id_persona": str},
        low_memory=False,
    )

    df["fexp"] = _a_numerico(df["fexp"])
    cols_num = [
        "area",
        "ciudad",
        "prov",
        "dominio",
        "p02",
        "p03",
        "p05a",
        "p06",
        "p10a",
        "p10b",
        "p15",
        "p24",
        "p37",
        "p42",
        "p51a",
        "nnivins",
        "ingrl",
        "ingpc",
        "condact",
        "empleo",
        "desempleo",
        "secemp",
        "grupo1",
        "rama1",
        "pobreza",
        "epobreza",
        "periodo",
        "mes",
    ]
    for c in cols_num:
        df[c] = _a_numerico(df[c])

    # Auditoría de códigos centinela antes de limpiar
    n_ingrl_999999 = int((df["ingrl"] >= 999999).sum())
    n_ingrl_neg1 = int((df["ingrl"] == -1).sum())
    media_ingrl_cruda = float(df["ingrl"].dropna().mean())
    n_horas_999 = int(((df["p24"] >= 999) | (df["p51a"] >= 999)).sum())
    n_edad_99 = int((df["p03"] >= 99).sum())

    # Unión 1 a N con vivienda/hogar para tamaño de hogar y características de vivienda
    if ruta_vivienda.exists():
        df_viv = pd.read_csv(
            ruta_vivienda,
            sep=";",
            usecols=["id_hogar", "vi07", "vi10", "vi14"],
            dtype={"id_hogar": str},
            low_memory=False,
        ).drop_duplicates(subset=["id_hogar"])
        for c in ("vi07", "vi10", "vi14"):
            df_viv[c] = _a_numerico(df_viv[c])
        df = df.merge(df_viv, on="id_hogar", how="left", validate="many_to_one")

    tam_hogar = df.groupby("id_hogar")["id_persona"].transform("count")
    df["tamano_hogar"] = tam_hogar.astype(np.int16)

    # Reglas oficiales de la sintaxis INEC (00 Indicadores de Mercado Laboral.sps)
    df.loc[df["p03"] < 15, "condact"] = 0
    df["petn"] = ((df["p03"] >= 15) & (df["p03"] <= 99)).astype(np.int8)
    df["pean"] = (df["petn"].eq(1) & df["condact"].isin([1, 2, 3, 4, 5, 6, 7, 8])).astype(np.int8)
    df["pein"] = (df["petn"].eq(1) & df["condact"].eq(9)).astype(np.int8)
    df["empleo_ind"] = (df["petn"].eq(1) & df["condact"].isin([1, 2, 3, 4, 5, 6])).astype(np.int8)
    df["adec"] = (df["petn"].eq(1) & df["condact"].eq(1)).astype(np.int8)
    df["sub"] = (df["petn"].eq(1) & df["condact"].isin([2, 3])).astype(np.int8)
    df["sub_h"] = (df["petn"].eq(1) & df["condact"].eq(2)).astype(np.int8)
    df["sub_w"] = (df["petn"].eq(1) & df["condact"].eq(3)).astype(np.int8)
    df["oinad"] = (df["petn"].eq(1) & df["condact"].eq(4)).astype(np.int8)
    df["nr"] = (df["petn"].eq(1) & df["condact"].eq(5)).astype(np.int8)
    df["nc"] = (df["petn"].eq(1) & df["condact"].eq(6)).astype(np.int8)
    df["desem"] = (df["petn"].eq(1) & df["condact"].isin([7, 8])).astype(np.int8)
    df["desemab"] = (df["petn"].eq(1) & df["condact"].eq(7)).astype(np.int8)
    df["desemoc"] = (df["petn"].eq(1) & df["condact"].eq(8)).astype(np.int8)

    df["formal"] = (df["empleo_ind"].eq(1) & df["secemp"].eq(1)).astype(np.int8)
    df["informal"] = (df["empleo_ind"].eq(1) & df["secemp"].eq(2)).astype(np.int8)
    df["empdom"] = (df["empleo_ind"].eq(1) & df["secemp"].eq(3)).astype(np.int8)
    df["nocla"] = (df["empleo_ind"].eq(1) & df["secemp"].eq(4)).astype(np.int8)

    # Limpieza de ingresos y horas trabajadas
    df["ingrl_limpio"] = df["ingrl"].where((df["ingrl"] >= 0) & (df["ingrl"] < 999999), np.nan)
    df["ingrl_positivo"] = df["ingrl_limpio"].where(df["ingrl_limpio"] > 0, np.nan)
    df["ingpc_limpio"] = df["ingpc"].where((df["ingpc"] >= 0) & (df["ingpc"] < 999999), np.nan)

    p24_limpio = df["p24"].where((df["p24"] > 0) & (df["p24"] < 140), np.nan)
    p51a_limpio = df["p51a"].where((df["p51a"] > 0) & (df["p51a"] < 140), np.nan)
    df["horas_semana"] = p51a_limpio.combine_first(p24_limpio)
    df["salario_hora"] = np.where(
        df["ingrl_positivo"].notna() & (df["horas_semana"] >= 1.0),
        df["ingrl_positivo"] / (df["horas_semana"] * 4.333333333333333),
        np.nan,
    )
    df["log_salario_hora"] = np.log(df["salario_hora"])
    df["log_ingrl"] = np.log(df["ingrl_positivo"])

    # Escolaridad y experiencia potencial (Mincer)
    df["escolaridad_egb"] = calcular_escolaridad_egb(df["p10a"], df["p10b"])
    df["escolaridad"] = calcular_escolaridad_clasica(df["p10a"], df["p10b"])
    edad_efectiva = df["p03"].where(df["p03"] < 98, np.nan)
    df["experiencia"] = np.maximum(edad_efectiva - df["escolaridad"] - 6.0, 0.0)
    df["experiencia_cuad"] = (df["experiencia"] ** 2) / 100.0

    # Afiliación a seguridad social contributiva (IESS general, voluntario, campesino, ISSFA/ISSPOL)
    df["afiliado_seguro"] = df["p05a"].isin([1, 2, 3, 4]).astype(np.int8)

    # Etiquetas categóricas en español
    prov_int = df["prov"].fillna(-1).astype(int)
    df["provincia_nombre"] = prov_int.map(PROVINCIAS).fillna("Otra")
    df["region_natural"] = prov_int.map(PROVINCIA_A_REGION_INEC).fillna("Otra")
    df["area_nombre"] = df["area"].fillna(-1).astype(int).map(AREAS).fillna("Desconocida")
    df["sexo_nombre"] = df["p02"].fillna(-1).astype(int).map(SEXO).fillna("Desconocido")
    df["mujer"] = (df["p02"] == 2).astype(np.int8)
    df["rural"] = (df["area"] == 2).astype(np.int8)
    df["etnia_nombre"] = df["p15"].fillna(-1).astype(int).map(P15_A_ETNIA)
    df["nivel_instruccion_nombre"] = (
        df["nnivins"].fillna(-1).astype(int).map(NIVEL_INSTRUCCION).fillna("Sin dato")
    )
    df["condact_nombre"] = (
        df["condact"].fillna(-1).astype(int).map(CONDACT_ETIQUETAS).fillna("Sin dato")
    )
    df["sector_nombre"] = (
        df["secemp"].fillna(-1).astype(int).map(SECEMP_ETIQUETAS).fillna("Fuera de ocupados")
    )
    df["rama_nombre"] = (
        df["rama1"].fillna(-1).astype(int).map(RAMA_ACTIVIDAD).fillna("No especificada")
    )
    df["grupo_ocupacion_nombre"] = (
        df["grupo1"].fillna(-1).astype(int).map(GRUPO_OCUPACION).fillna("No especificado")
    )

    media_ingrl_limpia = float(
        np.average(
            df.loc[df["empleo_ind"].eq(1) & df["ingrl_positivo"].notna(), "ingrl_positivo"],
            weights=df.loc[df["empleo_ind"].eq(1) & df["ingrl_positivo"].notna(), "fexp"],
        )
    )

    informe_calidad = {
        "filas_totales_personas": int(len(df)),
        "hogares_unicos": int(df["id_hogar"].nunique()),
        "viviendas_unicas": int(df["id_vivienda"].nunique()),
        "upm_unicas": int(df["upm"].nunique()),
        "estratos_unicos": int(df["estrato"].nunique()),
        "poblacion_total_expandida": round(float(df["fexp"].sum()), 2),
        "pet_expandida": round(float(df.loc[df["petn"].eq(1), "fexp"].sum()), 2),
        "pea_expandida": round(float(df.loc[df["pean"].eq(1), "fexp"].sum()), 2),
        "ocupados_expandidos": round(float(df.loc[df["empleo_ind"].eq(1), "fexp"].sum()), 2),
        "centinelas_detectados": {
            "ingrl_999999_no_informa": n_ingrl_999999,
            "ingrl_menos_1_sin_ingreso": n_ingrl_neg1,
            "horas_999_no_informa": n_horas_999,
            "edad_99_tope": n_edad_99,
            "media_ingrl_cruda_sin_limpiar_usd": round(media_ingrl_cruda, 2),
            "media_ingrl_limpia_ponderada_usd": round(media_ingrl_limpia, 2),
            "factor_distorsion_centinela": round(media_ingrl_cruda / media_ingrl_limpia, 2),
        },
    }
    return df, informe_calidad


def _parsear_valor_tabulado(val: str) -> float:
    """Convierte '62,0%' o '10,4' o '0,451' a float."""
    s = str(val).strip().replace("%", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def cargar_tabulados_oficiales_inec(
    dir_raw: Path = DIR_RAW,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lee `1. Estimadores.csv` de Mercado Laboral, Educación y Pobreza (2018-2025)."""
    base_tab = dir_raw / "tabulados_csv"
    ruta_ml = base_tab / "00 ENEMDU_Anual_2025_Tabulados_Mercado_Laboral_CSV" / "1. Estimadores.csv"

    lineas = ruta_ml.read_bytes().decode("cp1252", errors="replace").splitlines()
    encabezados = [c.strip() for c in lineas[3].split(";")[3:]]

    registros_serie: list[dict[str, Any]] = []
    registros_2025: list[dict[str, Any]] = []

    for linea in lineas[4:]:
        partes = [p.strip() for p in linea.split(";")]
        if len(partes) < 6 or not partes[0].isdigit():
            continue
        anio = int(partes[0])
        indicador = partes[1]
        tipo_est = partes[2]
        valores = partes[3 : 3 + len(encabezados)]

        if tipo_est == "Indicador":
            for dom, v_str in zip(encabezados, valores):
                if not dom:
                    continue
                registros_serie.append(
                    {
                        "anio": anio,
                        "indicador": indicador,
                        "dominio": dom,
                        "valor_pct": _parsear_valor_tabulado(v_str),
                    }
                )
        if anio == 2025:
            for dom, v_str in zip(encabezados, valores):
                if not dom:
                    continue
                registros_2025.append(
                    {
                        "indicador": indicador,
                        "tipo_estimador": tipo_est,
                        "dominio": dom,
                        "valor": _parsear_valor_tabulado(v_str),
                    }
                )

    df_serie = pd.DataFrame(registros_serie)
    df_2025_largo = pd.DataFrame(registros_2025)
    df_2025_piv = (
        df_2025_largo.pivot_table(
            index=["indicador", "dominio"],
            columns="tipo_estimador",
            values="valor",
            aggfunc="first",
        )
        .reset_index()
        .rename(
            columns={
                "Indicador": "indicador_oficial_pct",
                "Error estándar": "ee_oficial_pct",
                "Límite inferior": "ic_inf_oficial_pct",
                "Límite superior": "ic_sup_oficial_pct",
                "Coeficiente de variación": "cv_oficial",
            }
        )
    )
    return df_serie, df_2025_piv


def guardar_datos_procesados(
    df: pd.DataFrame,
    df_serie: pd.DataFrame,
    df_oficial_2025: pd.DataFrame,
    *,
    dir_procesados: Path = DIR_PROCESADOS,
    dir_muestra: Path = DIR_MUESTRA,
) -> dict[str, str]:
    """Guarda el subconjunto analítico PEA en Parquet, las tablas históricas y la muestra de tests."""
    dir_procesados.mkdir(parents=True, exist_ok=True)
    dir_muestra.mkdir(parents=True, exist_ok=True)

    cols_guardar = [
        "id_persona",
        "id_hogar",
        "estrato",
        "upm",
        "fexp",
        "mes",
        "area",
        "area_nombre",
        "rural",
        "prov",
        "provincia_nombre",
        "region_natural",
        "dominio",
        "p02",
        "sexo_nombre",
        "mujer",
        "p03",
        "p15",
        "etnia_nombre",
        "nnivins",
        "p10a",
        "nivel_instruccion_nombre",
        "escolaridad",
        "escolaridad_egb",
        "experiencia",
        "experiencia_cuad",
        "condact",
        "condact_nombre",
        "petn",
        "pean",
        "pein",
        "empleo_ind",
        "adec",
        "sub",
        "sub_h",
        "sub_w",
        "oinad",
        "nr",
        "desem",
        "secemp",
        "sector_nombre",
        "formal",
        "informal",
        "empdom",
        "afiliado_seguro",
        "rama1",
        "rama_nombre",
        "grupo1",
        "grupo_ocupacion_nombre",
        "p42",
        "horas_semana",
        "ingrl_limpio",
        "ingrl_positivo",
        "salario_hora",
        "log_salario_hora",
        "log_ingrl",
        "ingpc_limpio",
        "pobreza",
        "epobreza",
        "tamano_hogar",
    ]
    # Guardamos las personas de 15 años y más (PET) en Parquet comprimido (< 6 MB)
    df_pet = df.loc[df["petn"].eq(1), cols_guardar].copy()
    ruta_pet = dir_procesados / "enemdu_pet_2025.parquet"
    df_pet.to_parquet(ruta_pet, index=False, compression="zstd")

    ruta_serie = dir_procesados / "serie_historica_2018_2025.csv"
    df_serie.to_csv(ruta_serie, index=False, encoding="utf-8")

    ruta_oficial = dir_procesados / "estimadores_oficiales_2025.csv"
    df_oficial_2025.to_csv(ruta_oficial, index=False, encoding="utf-8")

    # Muestra estratificada de 80 UPM completas (~5.000 filas) para pruebas sin red
    rng = np.random.default_rng(42)
    upms_unicas = df["upm"].drop_duplicates().to_numpy()
    upms_muestra = rng.choice(upms_unicas, size=min(120, len(upms_unicas)), replace=False)
    df_muestra = df.loc[df["upm"].isin(upms_muestra), cols_guardar].copy()
    ruta_muestra = dir_muestra / "muestra_enemdu_2025.parquet"
    df_muestra.to_parquet(ruta_muestra, index=False, compression="zstd")

    return {
        "parquet_pet": str(ruta_pet),
        "csv_serie": str(ruta_serie),
        "csv_oficial_2025": str(ruta_oficial),
        "parquet_muestra": str(ruta_muestra),
    }


def leer_referencia_oficial_pobreza(dir_raw: Path = DIR_RAW, anio: int = 2025) -> dict[str, float]:
    """Lee del tabulado oficial de Pobreza y Desigualdad el Gini y la pobreza nacional publicados."""
    ruta = (
        dir_raw
        / "tabulados_csv"
        / "03 ENEMDU_Anual_2025_Tabulados_Pobreza_Desigualdad_CSV"
        / "1. Estimadores.csv"
    )
    buscados = {
        "Coeficiente de desigualdad de Gini": "gini_oficial",
        "Pobreza por ingresos": "pobreza_oficial_pct",
        "Pobreza extrema por ingresos": "pobreza_extrema_oficial_pct",
    }
    referencia: dict[str, float] = {}
    for linea in ruta.read_bytes().decode("cp1252", errors="replace").splitlines():
        celdas = linea.split(";")
        if len(celdas) > 3 and celdas[0].strip() == str(anio) and celdas[2].strip() == "Indicador":
            clave = buscados.get(celdas[1].strip())
            if clave:
                referencia[clave] = _parsear_valor_tabulado(celdas[3])
    return referencia
