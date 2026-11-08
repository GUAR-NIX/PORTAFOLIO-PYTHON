"""Cálculo de indicadores oficiales del mercado laboral y reconciliación contra tabulados INEC."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from empleo_enemdu.config import PROVINCIAS, SBU_USD_2025
from empleo_enemdu.encuesta import (
    DisenoMuestralENEMDU,
    cuantil_ponderado,
    estimar_razon_dominio,
    prueba_diferencia_dominios,
)


DEFINICION_INDICADORES_LABORALES: list[tuple[str, str, str]] = [
    ("Empleo Bruto", "empleo_ind", "petn"),
    ("Empleo Global", "empleo_ind", "pean"),
    ("Empleo Adecuado/Pleno", "adec", "pean"),
    ("Subempleo", "sub", "pean"),
    ("Empleo no Remunerado", "nr", "pean"),
    ("Otro Empleo no pleno", "oinad", "pean"),
    ("Desempleo", "desem", "pean"),
    ("Participación Global", "pean", "petn"),
    ("Participación Bruta", "pean", "_todos"),
    ("Sector informal", "informal", "empleo_ind"),
]


def calcular_indicadores_nacionales_y_area(
    df: pd.DataFrame,
    diseno: DisenoMuestralENEMDU | None = None,
) -> pd.DataFrame:
    """Calcula los 10 indicadores laborales con diseño complejo para Nacional, Urbano y Rural."""
    if diseno is None:
        diseno = DisenoMuestralENEMDU.desde_dataframe(df)

    df_aux = df.copy()
    df_aux["_todos"] = 1

    dominios = {
        "Total": np.ones(len(df_aux), dtype=bool),
        "Urbano": (df_aux["area"] == 1).to_numpy(),
        "Rural": (df_aux["area"] == 2).to_numpy(),
        "Quito": (df_aux["dominio"] == 1).to_numpy(),
        "Guayaquil": (df_aux["dominio"] == 2).to_numpy(),
        "Cuenca": (df_aux["dominio"] == 3).to_numpy(),
        "Machala": (df_aux["dominio"] == 4).to_numpy(),
        "Ambato": (df_aux["dominio"] == 5).to_numpy(),
    }

    filas: list[dict[str, Any]] = []
    for nombre_ind, col_num, col_den in DEFINICION_INDICADORES_LABORALES:
        y_num = df_aux[col_num].to_numpy(dtype=np.float64)
        base_den = df_aux[col_den].eq(1).to_numpy()
        for nombre_dom, masc_dom in dominios.items():
            masc = base_den & masc_dom
            est = estimar_razon_dominio(
                diseno,
                y_num,
                masc,
                indicador=nombre_ind,
                dominio=nombre_dom,
            )
            media_sin_ponderar = float(np.mean(y_num[masc])) * 100.0
            filas.append(
                {
                    "indicador": nombre_ind,
                    "dominio": nombre_dom,
                    "estimacion_pct": round(est.estimacion * 100.0, 4),
                    "sin_ponderar_pct": round(media_sin_ponderar, 4),
                    "sesgo_sin_ponderar_pp": round(media_sin_ponderar - est.estimacion * 100.0, 4),
                    "ee_complejo_pct": round(est.error_estandar * 100.0, 4),
                    "ee_mas_pct": round(est.error_estandar_mas * 100.0, 4),
                    "razon_ee_complejo_vs_mas": round(est.deft, 2),
                    "ic95_inf_pct": round(est.limite_inferior * 100.0, 4),
                    "ic95_sup_pct": round(est.limite_superior * 100.0, 4),
                    "cv_pct": round(est.coeficiente_variacion, 2),
                    "deff": round(est.deff, 2),
                    "deft": round(est.deft, 2),
                    "n_muestral": est.n_muestral,
                    "n_efectivo": round(est.n_efectivo, 1),
                    "poblacion_expandida": round(est.poblacion_expandida, 1),
                }
            )
    return pd.DataFrame(filas)


def reconciliar_con_tabulados_inec(
    df_calculado: pd.DataFrame,
    df_oficial_2025: pd.DataFrame,
) -> pd.DataFrame:
    """Cruza las estimaciones complejas propias contra los tabulados oficiales INEC 2025."""
    cruce = df_calculado.merge(
        df_oficial_2025,
        on=["indicador", "dominio"],
        how="inner",
    )
    cruce["dif_indicador_pp"] = (
        cruce["estimacion_pct"].round(1) - cruce["indicador_oficial_pct"].round(1)
    ).round(2)
    cruce["dif_ee_pp"] = (
        cruce["ee_complejo_pct"].round(1) - cruce["ee_oficial_pct"].round(1)
    ).round(2)
    cruce["dif_cv"] = (cruce["cv_pct"].round(1) - cruce["cv_oficial"].round(1)).round(2)
    cruce["reconcilia_ok"] = (
        (cruce["dif_indicador_pp"].abs() <= 0.1) & (cruce["dif_ee_pp"].abs() <= 0.1)
    )
    return cruce


def resumen_por_provincia(
    df: pd.DataFrame,
    diseno: DisenoMuestralENEMDU | None = None,
) -> pd.DataFrame:
    """Calcula indicadores laborales, informalidad, cobertura IESS e ingresos en las 24 provincias."""
    if diseno is None:
        diseno = DisenoMuestralENEMDU.desde_dataframe(df)

    pean = df["pean"].eq(1).to_numpy()
    ocup = df["empleo_ind"].eq(1).to_numpy()
    pob_val = df["pobreza"].isin([0, 1]).to_numpy()

    filas: list[dict[str, Any]] = []
    for cod_prov, nombre_prov in sorted(PROVINCIAS.items()):
        if cod_prov == 90:
            continue
        m_prov = (df["prov"] == cod_prov).to_numpy()
        if int(np.sum(m_prov & pean)) == 0:
            continue

        est_adec = estimar_razon_dominio(
            diseno, df["adec"], m_prov & pean, indicador="Empleo Adecuado", dominio=nombre_prov
        )
        est_sub = estimar_razon_dominio(
            diseno, df["sub"], m_prov & pean, indicador="Subempleo", dominio=nombre_prov
        )
        est_des = estimar_razon_dominio(
            diseno, df["desem"], m_prov & pean, indicador="Desempleo", dominio=nombre_prov
        )
        est_inf = estimar_razon_dominio(
            diseno, df["informal"], m_prov & ocup, indicador="Informalidad", dominio=nombre_prov
        )
        est_pob = estimar_razon_dominio(
            diseno, df["pobreza"], m_prov & pob_val, indicador="Pobreza", dominio=nombre_prov
        )

        m_ing = m_prov & ocup & df["ingrl_positivo"].notna().to_numpy()
        ing_vals = df.loc[m_ing, "ingrl_positivo"].to_numpy()
        ing_pesos = df.loc[m_ing, "fexp"].to_numpy()
        mediana_ing = float(cuantil_ponderado(ing_vals, ing_pesos, [0.5])[0])
        media_ing = float(np.average(ing_vals, weights=ing_pesos))

        afiliado_tasa = float(
            np.average(df.loc[m_prov & ocup, "afiliado_seguro"], weights=df.loc[m_prov & ocup, "fexp"])
        )
        region = df.loc[m_prov, "region_natural"].iloc[0]

        filas.append(
            {
                "cod_prov": cod_prov,
                "provincia": nombre_prov,
                "region_natural": region,
                "pea_expandida": round(est_adec.poblacion_expandida, 0),
                "n_muestral_pea": est_adec.n_muestral,
                "empleo_adecuado_pct": round(est_adec.estimacion * 100.0, 2),
                "empleo_adecuado_ee_pct": round(est_adec.error_estandar * 100.0, 2),
                "subempleo_pct": round(est_sub.estimacion * 100.0, 2),
                "desempleo_pct": round(est_des.estimacion * 100.0, 2),
                "informalidad_pct": round(est_inf.estimacion * 100.0, 2),
                "informalidad_ee_pct": round(est_inf.error_estandar * 100.0, 2),
                "afiliacion_seguro_pct": round(afiliado_tasa * 100.0, 2),
                "pobreza_pct": round(est_pob.estimacion * 100.0, 2),
                "ingreso_laboral_mediano_usd": round(mediana_ing, 2),
                "ingreso_laboral_medio_usd": round(media_ing, 2),
            }
        )

    return pd.DataFrame(filas).sort_values("empleo_adecuado_pct", ascending=False).reset_index(drop=True)


def resumen_por_subgrupos(df: pd.DataFrame) -> pd.DataFrame:
    """Desagrega tasas laborales e ingresos por sexo, área, grupo de edad, etnia y educación."""
    df_pea = df.loc[df["pean"].eq(1)].copy()
    df_pea["grupo_edad"] = pd.cut(
        df_pea["p03"],
        bins=[14, 24, 34, 44, 64, 120],
        labels=["15 a 24 años", "25 a 34 años", "35 a 44 años", "45 a 64 años", "65 años y más"],
    ).astype(str)

    dimensiones = [
        ("Sexo", "sexo_nombre"),
        ("Área", "area_nombre"),
        ("Grupo de edad", "grupo_edad"),
        ("Autoidentificación étnica", "etnia_nombre"),
        ("Nivel de instrucción", "nivel_instruccion_nombre"),
    ]

    filas: list[dict[str, Any]] = []
    for nombre_dim, col in dimensiones:
        for categoria, sub in df_pea.groupby(col, dropna=True):
            if categoria in ("Sin dato", "Desconocido", "nan", "None") or len(sub) < 30:
                continue
            w = sub["fexp"].to_numpy()
            sub_ocup = sub.loc[sub["empleo_ind"].eq(1)]
            w_ocup = sub_ocup["fexp"].to_numpy()
            sub_ing = sub_ocup.loc[sub_ocup["ingrl_positivo"].notna()]
            sub_hr = sub_ocup.loc[sub_ocup["salario_hora"].notna()]

            filas.append(
                {
                    "dimension": nombre_dim,
                    "categoria": str(categoria),
                    "n_muestral_pea": int(len(sub)),
                    "pea_expandida": round(float(np.sum(w)), 0),
                    "empleo_adecuado_pct": round(float(np.average(sub["adec"], weights=w) * 100.0), 2),
                    "subempleo_pct": round(float(np.average(sub["sub"], weights=w) * 100.0), 2),
                    "otro_no_pleno_pct": round(float(np.average(sub["oinad"], weights=w) * 100.0), 2),
                    "no_remunerado_pct": round(float(np.average(sub["nr"], weights=w) * 100.0), 2),
                    "desempleo_pct": round(float(np.average(sub["desem"], weights=w) * 100.0), 2),
                    "informalidad_pct": round(
                        float(np.average(sub_ocup["informal"], weights=w_ocup) * 100.0), 2
                    ),
                    "afiliacion_seguro_pct": round(
                        float(np.average(sub_ocup["afiliado_seguro"], weights=w_ocup) * 100.0), 2
                    ),
                    "ingreso_mediano_usd": round(
                        float(
                            cuantil_ponderado(
                                sub_ing["ingrl_positivo"].to_numpy(),
                                sub_ing["fexp"].to_numpy(),
                                [0.5],
                            )[0]
                        ),
                        2,
                    ),
                    "ingreso_medio_usd": round(
                        float(np.average(sub_ing["ingrl_positivo"], weights=sub_ing["fexp"])), 2
                    ),
                    "salario_hora_medio_usd": round(
                        float(np.average(sub_hr["salario_hora"], weights=sub_hr["fexp"])), 2
                    ),
                    "horas_semana_media": round(
                        float(
                            np.average(
                                sub_ocup.loc[sub_ocup["horas_semana"].notna(), "horas_semana"],
                                weights=sub_ocup.loc[sub_ocup["horas_semana"].notna(), "fexp"],
                            )
                        ),
                        1,
                    ),
                }
            )
    return pd.DataFrame(filas)


def resumen_por_rama_actividad(df: pd.DataFrame) -> pd.DataFrame:
    """Analiza las principales ramas de actividad económica (CIIU) en los ocupados."""
    ocup = df.loc[df["empleo_ind"].eq(1) & df["rama1"].notna()].copy()
    total_ocup = float(ocup["fexp"].sum())

    filas: list[dict[str, Any]] = []
    for rama_cod, sub in ocup.groupby("rama1"):
        w = sub["fexp"].to_numpy()
        peso_total = float(np.sum(w))
        if peso_total / total_ocup < 0.01:
            continue
        sub_ing = sub.loc[sub["ingrl_positivo"].notna()]
        sub_hr = sub.loc[sub["salario_hora"].notna()]
        filas.append(
            {
                "rama_cod": int(rama_cod),
                "rama_nombre": sub["rama_nombre"].iloc[0],
                "ocupados_expandidos": round(peso_total, 0),
                "participacion_ocupados_pct": round((peso_total / total_ocup) * 100.0, 2),
                "informalidad_pct": round(float(np.average(sub["informal"], weights=w) * 100.0), 2),
                "empleo_adecuado_pct": round(float(np.average(sub["adec"], weights=w) * 100.0), 2),
                "mujeres_pct": round(float(np.average(sub["mujer"], weights=w) * 100.0), 2),
                "ingreso_mediano_usd": round(
                    float(
                        cuantil_ponderado(
                            sub_ing["ingrl_positivo"].to_numpy(),
                            sub_ing["fexp"].to_numpy(),
                            [0.5],
                        )[0]
                    ),
                    2,
                ),
                "ingreso_medio_usd": round(
                    float(np.average(sub_ing["ingrl_positivo"], weights=sub_ing["fexp"])), 2
                ),
                "salario_hora_medio_usd": round(
                    float(np.average(sub_hr["salario_hora"], weights=sub_hr["fexp"])), 2
                ),
            }
        )
    return pd.DataFrame(filas).sort_values("ocupados_expandidos", ascending=False).reset_index(drop=True)


def resumen_ingresos_por_sector(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Mediana ponderada del ingreso laboral y % bajo el SBU en los sectores formal e informal."""
    ocup = df.loc[df["empleo_ind"].eq(1) & df["ingrl_positivo"].notna()]
    resumen: dict[str, dict[str, float]] = {}
    for etiqueta, col in [("sector_formal", "formal"), ("sector_informal", "informal")]:
        sub = ocup.loc[ocup[col].eq(1)]
        vals = sub["ingrl_positivo"].to_numpy()
        w = sub["fexp"].to_numpy()
        resumen[etiqueta] = {
            "n_muestral": int(len(sub)),
            "ingreso_mediano_usd": round(float(cuantil_ponderado(vals, w, [0.5])[0]), 2),
            "bajo_sbu_pct": round(float(np.average(vals < SBU_USD_2025, weights=w) * 100.0), 2),
        }
    return resumen


def contrastes_hipotesis_complejos(
    df: pd.DataFrame,
    diseno: DisenoMuestralENEMDU | None = None,
) -> list[dict[str, Any]]:
    """Ejecuta pruebas de diferencia de proporciones bajo diseño complejo en pares clave."""
    if diseno is None:
        diseno = DisenoMuestralENEMDU.desde_dataframe(df)

    pean = df["pean"].eq(1).to_numpy()
    ocup = df["empleo_ind"].eq(1).to_numpy()
    hombre = (df["p02"] == 1).to_numpy()
    mujer = (df["p02"] == 2).to_numpy()
    urbano = (df["area"] == 1).to_numpy()
    rural = (df["area"] == 2).to_numpy()

    pruebas = [
        (
            "Empleo adecuado: Hombre vs Mujer (PEA)",
            df["adec"],
            pean & hombre,
            pean & mujer,
            "Hombre",
            "Mujer",
        ),
        (
            "Empleo adecuado: Urbano vs Rural (PEA)",
            df["adec"],
            pean & urbano,
            pean & rural,
            "Urbano",
            "Rural",
        ),
        (
            "Sector informal: Rural vs Urbano (Ocupados)",
            df["informal"],
            ocup & rural,
            ocup & urbano,
            "Rural",
            "Urbano",
        ),
        (
            "Sector informal: Mujer vs Hombre (Ocupados)",
            df["informal"],
            ocup & mujer,
            ocup & hombre,
            "Mujer",
            "Hombre",
        ),
    ]

    resultados: list[dict[str, Any]] = []
    for titulo, serie_y, m_a, m_b, nom_a, nom_b in pruebas:
        res = prueba_diferencia_dominios(
            diseno, serie_y, m_a, m_b, nombre_a=nom_a, nombre_b=nom_b
        )
        resultados.append(
            {
                "contraste": titulo,
                "grupo_a": nom_a,
                "grupo_b": nom_b,
                "tasa_a_pct": round(float(res["estimacion_a"]) * 100.0, 2),
                "tasa_b_pct": round(float(res["estimacion_b"]) * 100.0, 2),
                "diferencia_pp": round(float(res["diferencia"]) * 100.0, 2),
                "ee_complejo_pp": round(float(res["error_estandar_complejo"]) * 100.0, 2),
                "ee_independiente_pp": round(float(res["error_estandar_independiente"]) * 100.0, 2),
                "estadistico_t": round(float(res["estadistico_t"]), 2),
                "p_valor": float(res["p_valor"]),
                "ic95_inf_pp": round(float(res["ic95_inferior"]) * 100.0, 2),
                "ic95_sup_pp": round(float(res["ic95_superior"]) * 100.0, 2),
            }
        )
    return resultados
