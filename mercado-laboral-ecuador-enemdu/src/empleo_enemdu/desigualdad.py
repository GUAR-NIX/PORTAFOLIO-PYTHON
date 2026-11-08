"""Desigualdad de ingresos (Lorenz, Gini, Palma, deciles) y vínculo mercado laboral-pobreza."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from empleo_enemdu.config import SBU_USD_2025
from empleo_enemdu.encuesta import DisenoMuestralENEMDU, cuantil_ponderado, estimar_razon_dominio


def gini_ponderado(valores: np.ndarray, pesos: np.ndarray) -> float:
    """Calcula el coeficiente de Gini ponderado exacto por integración trapezoidal de Lorenz."""
    valido = np.isfinite(valores) & np.isfinite(pesos) & (valores >= 0) & (pesos > 0)
    x = valores[valido]
    w = pesos[valido]
    orden = np.argsort(x, kind="mergesort")
    x = x[orden]
    w = w[orden]

    w_norm = w / np.sum(w)
    yw = x * w_norm
    suma_yw = float(np.sum(yw))
    if suma_yw <= 0:
        return 0.0
    yw_norm = yw / suma_yw

    cum_y = np.concatenate([[0.0], np.cumsum(yw_norm)])
    return float(1.0 - np.sum((cum_y[1:] + cum_y[:-1]) * w_norm))


def curva_lorenz_y_deciles(
    valores: np.ndarray | pd.Series,
    pesos: np.ndarray | pd.Series,
    *,
    n_puntos: int = 101,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    """Calcula la curva de Lorenz interpolada, participación por deciles y ratios de desigualdad."""
    x = np.asarray(valores, dtype=np.float64)
    w = np.asarray(pesos, dtype=np.float64)
    valido = np.isfinite(x) & np.isfinite(w) & (x >= 0) & (w > 0)
    x = x[valido]
    w = w[valido]

    orden = np.argsort(x, kind="mergesort")
    x = x[orden]
    w = w[orden]

    w_norm = w / np.sum(w)
    yw = x * w_norm
    yw_norm = yw / np.sum(yw)

    p_acum = np.concatenate([[0.0], np.cumsum(w_norm)])
    l_acum = np.concatenate([[0.0], np.cumsum(yw_norm)])

    rejilla_p = np.linspace(0.0, 1.0, n_puntos)
    rejilla_l = np.interp(rejilla_p, p_acum, l_acum)
    df_lorenz = pd.DataFrame(
        {
            "poblacion_acum_pct": np.round(rejilla_p * 100.0, 2),
            "ingreso_acum_pct": np.round(rejilla_l * 100.0, 4),
            "igualdad_pct": np.round(rejilla_p * 100.0, 2),
        }
    )

    # Participación por deciles (1 a 10)
    cortes = np.linspace(0.0, 1.0, 11)
    l_cortes = np.interp(cortes, p_acum, l_acum)
    part_decil = np.diff(l_cortes) * 100.0
    cortes_usd = cuantil_ponderado(x, w, np.linspace(0.05, 0.95, 10))

    df_deciles = pd.DataFrame(
        {
            "decil": [f"D{i}" for i in range(1, 11)],
            "numero_decil": list(range(1, 11)),
            "participacion_ingreso_pct": np.round(part_decil, 2),
            "ingreso_mediano_decil_usd": np.round(cortes_usd, 2),
        }
    )

    gini = float(1.0 - np.sum((l_acum[1:] + l_acum[:-1]) * w_norm))
    palma = float(part_decil[9] / max(np.sum(part_decil[:4]), 1e-12))
    p10, p50, p90 = cuantil_ponderado(x[x > 0], w[x > 0], [0.10, 0.50, 0.90])
    ratio_p90_p10 = float(p90 / max(p10, 1e-12))

    resumen = {
        "gini": round(gini, 4),
        "indice_palma": round(palma, 2),
        "ratio_p90_p10": round(ratio_p90_p10, 2),
        "participacion_d10_pct": round(float(part_decil[9]), 2),
        "participacion_d1_a_d4_pct": round(float(np.sum(part_decil[:4])), 2),
        "p10_usd": round(float(p10), 2),
        "p50_usd": round(float(p50), 2),
        "p90_usd": round(float(p90), 2),
    }
    return df_lorenz, df_deciles, resumen


def analizar_desigualdad_y_pobreza(
    df: pd.DataFrame,
    diseno: DisenoMuestralENEMDU | None = None,
) -> dict[str, Any]:
    """Calcula Gini, Lorenz, pobreza por condición de actividad y simulación contrafactual."""
    if diseno is None:
        diseno = DisenoMuestralENEMDU.desde_dataframe(df)

    # 1. Desigualdad del ingreso per cápita del hogar (conciliado con Gini oficial INEC = 0.451)
    m_ingpc = df["ingpc_limpio"].notna()
    df_lorenz_pc, df_deciles_pc, res_pc = curva_lorenz_y_deciles(
        df.loc[m_ingpc, "ingpc_limpio"], df.loc[m_ingpc, "fexp"]
    )

    # 2. Desigualdad del ingreso laboral mensual de los ocupados (total, formal e informal)
    m_ocup_ing = df["empleo_ind"].eq(1) & df["ingrl_positivo"].notna()
    df_lorenz_lab, df_deciles_lab, res_lab = curva_lorenz_y_deciles(
        df.loc[m_ocup_ing, "ingrl_positivo"], df.loc[m_ocup_ing, "fexp"]
    )
    m_for_ing = m_ocup_ing & df["formal"].eq(1)
    m_inf_ing = m_ocup_ing & df["informal"].eq(1)
    gini_formal = gini_ponderado(
        df.loc[m_for_ing, "ingrl_positivo"].to_numpy(),
        df.loc[m_for_ing, "fexp"].to_numpy(),
    )
    gini_informal = gini_ponderado(
        df.loc[m_inf_ing, "ingrl_positivo"].to_numpy(),
        df.loc[m_inf_ing, "fexp"].to_numpy(),
    )

    # 3. Tasas de pobreza y pobreza extrema por condición laboral de la PEA (con diseño complejo)
    pean = df["pean"].eq(1).to_numpy()
    pob_valida = df["pobreza"].isin([0, 1]).to_numpy()
    epob_valida = df["epobreza"].isin([0, 1]).to_numpy()

    grupos_condact = [
        ("Empleo adecuado/pleno", df["adec"].eq(1).to_numpy()),
        ("Subempleo", df["sub"].eq(1).to_numpy()),
        ("Otro empleo no pleno", df["oinad"].eq(1).to_numpy()),
        ("Empleo no remunerado", df["nr"].eq(1).to_numpy()),
        ("Desempleo", df["desem"].eq(1).to_numpy()),
        ("Sector formal (ocupados)", df["formal"].eq(1).to_numpy()),
        ("Sector informal (ocupados)", df["informal"].eq(1).to_numpy()),
    ]

    pobreza_por_condicion: list[dict[str, Any]] = []
    for etiqueta, masc_c in grupos_condact:
        est_p = estimar_razon_dominio(
            diseno,
            df["pobreza"],
            pean & pob_valida & masc_c,
            indicador="Pobreza por ingresos",
            dominio=etiqueta,
        )
        est_ep = estimar_razon_dominio(
            diseno,
            df["epobreza"],
            pean & epob_valida & masc_c,
            indicador="Pobreza extrema",
            dominio=etiqueta,
        )
        pobreza_por_condicion.append(
            {
                "condicion_laboral": etiqueta,
                "pobreza_pct": round(est_p.estimacion * 100.0, 2),
                "pobreza_ee_pct": round(est_p.error_estandar * 100.0, 2),
                "pobreza_ic95_inf": round(est_p.limite_inferior * 100.0, 2),
                "pobreza_ic95_sup": round(est_p.limite_superior * 100.0, 2),
                "pobreza_extrema_pct": round(est_ep.estimacion * 100.0, 2),
                "pobreza_extrema_ee_pct": round(est_ep.error_estandar * 100.0, 2),
                "poblacion_pea_expandida": round(est_p.poblacion_expandida, 0),
            }
        )

    # 4. Ejercicio contable contrafactual de formalización al SBU (USD 470)
    # Umbral implícito de pobreza en la base (máximo ingpc entre quienes tienen pobreza == 1)
    linea_pobreza_usd = float(df.loc[df["pobreza"] == 1, "ingpc_limpio"].max())
    linea_epobreza_usd = float(df.loc[df["epobreza"] == 1, "ingpc_limpio"].max())

    # En los hogares con al menos un ocupado informal que gana menos del SBU,
    # ¿qué pasa con el ingreso per cápita si el principal perceptor informal alcanza el SBU?
    ocup_inf_bajo = (
        df["informal"].eq(1)
        & df["ingrl_limpio"].notna()
        & (df["ingrl_limpio"] < SBU_USD_2025)
    )
    brecha_sbu_persona = np.where(
        ocup_inf_bajo, SBU_USD_2025 - df["ingrl_limpio"].fillna(0.0), 0.0
    )
    df_sim = pd.DataFrame(
        {
            "id_hogar": df["id_hogar"],
            "fexp": df["fexp"],
            "ingpc_actual": df["ingpc_limpio"],
            "pobreza_actual": df["pobreza"],
            "epobreza_actual": df["epobreza"],
            "tamano_hogar": df["tamano_hogar"],
            "brecha_sbu": brecha_sbu_persona,
        }
    )
    max_incremento_hogar = df_sim.groupby("id_hogar")["brecha_sbu"].transform("max")
    ingpc_contrafactual = df_sim["ingpc_actual"] + (
        max_incremento_hogar / np.maximum(df_sim["tamano_hogar"], 1)
    )

    m_pob = df_sim["pobreza_actual"].isin([0, 1]) & df_sim["ingpc_actual"].notna()
    w_pob = df_sim.loc[m_pob, "fexp"].to_numpy()
    tasa_pob_actual = float(np.average(df_sim.loc[m_pob, "pobreza_actual"], weights=w_pob) * 100.0)
    tasa_pob_contra = float(
        np.average(
            (ingpc_contrafactual.loc[m_pob] <= linea_pobreza_usd).astype(float),
            weights=w_pob,
        )
        * 100.0
    )
    personas_salen_pobreza = float(
        np.sum(
            w_pob
            * (
                df_sim.loc[m_pob, "pobreza_actual"].to_numpy()
                - (ingpc_contrafactual.loc[m_pob] <= linea_pobreza_usd).to_numpy(dtype=float)
            )
        )
    )

    return {
        "linea_pobreza_observada_usd": round(linea_pobreza_usd, 2),
        "linea_pobreza_extrema_observada_usd": round(linea_epobreza_usd, 2),
        "ingreso_per_capita_hogar": res_pc,
        "ingreso_laboral_ocupados": {
            **res_lab,
            "gini_sector_formal": round(gini_formal, 4),
            "gini_sector_informal": round(gini_informal, 4),
        },
        "curva_lorenz_ingpc": df_lorenz_pc.to_dict(orient="records"),
        "curva_lorenz_laboral": df_lorenz_lab.to_dict(orient="records"),
        "deciles_ingpc": df_deciles_pc.to_dict(orient="records"),
        "deciles_laboral": df_deciles_lab.to_dict(orient="records"),
        "pobreza_por_condicion_laboral": pobreza_por_condicion,
        "simulacion_contrafactual_sbu": {
            "sbu_referencia_usd": SBU_USD_2025,
            "tasa_pobreza_actual_pct": round(tasa_pob_actual, 2),
            "tasa_pobreza_contrafactual_pct": round(tasa_pob_contra, 2),
            "reduccion_pobreza_pp": round(tasa_pob_actual - tasa_pob_contra, 2),
            "personas_que_saldrian_de_pobreza": round(personas_salen_pobreza, 0),
        },
    }
