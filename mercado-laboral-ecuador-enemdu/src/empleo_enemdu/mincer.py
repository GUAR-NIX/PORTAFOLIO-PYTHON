"""Ecuación salarial de Mincer con Mínimos Cuadrados Ponderados (WLS) y errores agrupados por UPM."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm


def preparar_muestra_mincer(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra ocupados de 15 a 75 años con salario por hora positivo y variables completas."""
    cond = (
        df["empleo_ind"].eq(1)
        & df["p03"].between(15, 75)
        & df["salario_hora"].notna()
        & (df["salario_hora"] > 0.15)
        & (df["salario_hora"] < 250.0)
        & df["escolaridad"].notna()
        & df["experiencia"].notna()
        & df["fexp"].gt(0)
    )
    sub = df.loc[cond].copy()
    sub["indigena"] = (sub["etnia_nombre"] == "Indígena").astype(np.float64)
    sub["afro_montubio"] = sub["etnia_nombre"].isin(["Afroecuatoriano", "Montubio"]).astype(
        np.float64
    )

    # Niveles educativos detallados (efecto diploma)
    if "p10a" in sub.columns:
        p10a = sub["p10a"].fillna(1).astype(int)
        sub["nivel_credencial"] = np.select(
            [
                p10a.isin([1, 2, 3]),
                p10a.isin([4, 5]),
                p10a.isin([6, 7]),
                p10a == 8,
                p10a == 9,
                p10a == 10,
            ],
            [
                "1_Sin_instruccion",
                "2_Basica_Primaria",
                "3_Bachillerato_Secundaria",
                "4_Superior_Tecnica",
                "5_Superior_Universitaria",
                "6_Posgrado",
            ],
            default="2_Basica_Primaria",
        )
    else:
        nniv = sub["nnivins"].fillna(1).astype(int) if "nnivins" in sub.columns else pd.Series(3, index=sub.index)
        esc = sub["escolaridad"].fillna(0.0)
        sub["nivel_credencial"] = np.select(
            [
                nniv.isin([1, 2]),
                nniv == 3,
                nniv == 4,
                (nniv == 5) & (esc <= 14.5),
                (nniv == 5) & (esc > 14.5) & (esc <= 17.0),
                (nniv == 5) & (esc > 17.0),
            ],
            [
                "1_Sin_instruccion",
                "2_Basica_Primaria",
                "3_Bachillerato_Secundaria",
                "4_Superior_Tecnica",
                "5_Superior_Universitaria",
                "6_Posgrado",
            ],
            default="2_Basica_Primaria",
        )
    return sub


def _ajustar_wls_cluster(
    y: pd.Series,
    X: pd.DataFrame,
    pesos: pd.Series,
    grupos_upm: pd.Series,
) -> tuple[Any, Any]:
    """Ajusta WLS ponderado por `fexp` y devuelve el resultado con EE cluster(UPM) y EE clásico."""
    X_const = sm.add_constant(X, has_constant="add")
    modelo = sm.WLS(y.astype(np.float64), X_const.astype(np.float64), weights=pesos.astype(np.float64))
    res_clasico = modelo.fit()
    res_cluster = modelo.fit(
        cov_type="cluster",
        cov_kwds={"groups": grupos_upm.to_numpy()},
    )
    return res_cluster, res_clasico


def _extraer_Termino(res_cluster: Any, res_clasico: Any, nombre: str) -> dict[str, float]:
    """Extrae coeficiente, retorno porcentual exacto, EE cluster y EE clásico."""
    if nombre not in res_cluster.params.index:
        return {}
    beta = float(res_cluster.params[nombre])
    ee_cl = float(res_cluster.bse[nombre])
    ee_ols = float(res_clasico.bse[nombre])
    pval = float(res_cluster.pvalues[nombre])
    ci_low, ci_high = [float(x) for x in res_cluster.conf_int().loc[nombre]]
    efecto_pct = (np.exp(beta) - 1.0) * 100.0
    return {
        "beta": round(beta, 5),
        "efecto_porcentual": round(float(efecto_pct), 2),
        "ee_cluster_upm": round(ee_cl, 5),
        "ee_ingenuo_wls": round(ee_ols, 5),
        "razon_ee_cluster_vs_ingenuo": round(ee_cl / max(ee_ols, 1e-12), 2),
        "p_valor": pval,
        "ic95_inf": round(ci_low, 5),
        "ic95_sup": round(ci_high, 5),
    }


def estimar_modelos_mincer(df: pd.DataFrame) -> dict[str, Any]:
    """Estima las 5 especificaciones de Mincer (base, +formalidad, +controles, formal, informal)."""
    sub = preparar_muestra_mincer(df)
    y = sub["log_salario_hora"]
    w = sub["fexp"]
    upm = sub["upm"]

    # 1. Mincer base
    cols_m1 = ["escolaridad", "experiencia", "experiencia_cuad", "mujer", "rural"]
    res1_cl, res1_ols = _ajustar_wls_cluster(y, sub[cols_m1], w, upm)

    # 2. Mincer + canal de formalidad y seguridad social
    cols_m2 = cols_m1 + ["informal", "afiliado_seguro"]
    res2_cl, res2_ols = _ajustar_wls_cluster(y, sub[cols_m2], w, upm)

    # 3. Mincer completo (+ etnia, efectos fijos de rama CIIU y provincia)
    dummies_rama = pd.get_dummies(
        sub["rama1"].fillna(0).astype(int), prefix="rama", drop_first=True, dtype=np.float64
    )
    dummies_prov = pd.get_dummies(
        sub["prov"].fillna(0).astype(int), prefix="prov", drop_first=True, dtype=np.float64
    )
    X_m3 = pd.concat(
        [
            sub[cols_m2 + ["indigena", "afro_montubio"]],
            dummies_rama,
            dummies_prov,
        ],
        axis=1,
    )
    res3_cl, res3_ols = _ajustar_wls_cluster(y, X_m3, w, upm)

    # 4. Solo sector formal
    sub_for = sub.loc[sub["formal"].eq(1)]
    res_for_cl, res_for_ols = _ajustar_wls_cluster(
        sub_for["log_salario_hora"],
        sub_for[cols_m1],
        sub_for["fexp"],
        sub_for["upm"],
    )

    # 5. Solo sector informal
    sub_inf = sub.loc[sub["informal"].eq(1)]
    res_inf_cl, res_inf_ols = _ajustar_wls_cluster(
        sub_inf["log_salario_hora"],
        sub_inf[cols_m1],
        sub_inf["fexp"],
        sub_inf["upm"],
    )

    # 6. Efecto diploma (credencialismo por nivel educativo completado)
    dummies_cred = pd.get_dummies(
        sub["nivel_credencial"], drop_first=True, dtype=np.float64
    )
    X_cred = pd.concat(
        [
            dummies_cred,
            sub[["experiencia", "experiencia_cuad", "mujer", "rural", "informal", "afiliado_seguro"]],
        ],
        axis=1,
    )
    res_cred_cl, res_cred_ols = _ajustar_wls_cluster(y, X_cred, w, upm)

    # Experiencia en el pico salarial: -beta_exp / (2 * beta_exp2 / 100)
    b_exp = float(res1_cl.params["experiencia"])
    b_exp2 = float(res1_cl.params["experiencia_cuad"]) / 100.0
    exp_pico = -b_exp / (2.0 * b_exp2) if b_exp2 < 0 else float("nan")

    variables_clave = [
        "escolaridad",
        "experiencia",
        "experiencia_cuad",
        "mujer",
        "rural",
        "informal",
        "afiliado_seguro",
        "indigena",
        "afro_montubio",
    ]

    def _resumen_modelo(
        nombre_mod: str, rc: Any, ro: Any, n_obs: int, n_clusters: int
    ) -> dict[str, Any]:
        terminos = {
            v: _extraer_Termino(rc, ro, v)
            for v in variables_clave
            if v in rc.params.index
        }
        return {
            "modelo": nombre_mod,
            "n_observaciones": n_obs,
            "n_upm_clusters": n_clusters,
            "r2_ponderado": round(float(rc.rsquared), 4),
            "r2_ajustado": round(float(rc.rsquared_adj), 4),
            "coeficientes": terminos,
        }

    efectos_diploma: list[dict[str, Any]] = [
        {
            "nivel": "Sin instrucción (referencia)",
            "codigo": "1_Sin_instruccion",
            "beta": 0.0,
            "premio_salarial_pct": 0.0,
            "ic95_inf_pct": 0.0,
            "ic95_sup_pct": 0.0,
        }
    ]
    etiquetas_cred = {
        "2_Basica_Primaria": "Educación Básica / Primaria",
        "3_Bachillerato_Secundaria": "Bachillerato / Secundaria",
        "4_Superior_Tecnica": "Superior Técnica / Tecnológica",
        "5_Superior_Universitaria": "Superior Universitaria",
        "6_Posgrado": "Posgrado (Maestría / PhD)",
    }
    for cod, etiq in etiquetas_cred.items():
        if cod in res_cred_cl.params.index:
            b = float(res_cred_cl.params[cod])
            ci_l, ci_h = [float(x) for x in res_cred_cl.conf_int().loc[cod]]
            efectos_diploma.append(
                {
                    "nivel": etiq,
                    "codigo": cod,
                    "beta": round(b, 4),
                    "premio_salarial_pct": round(float((np.exp(b) - 1.0) * 100.0), 2),
                    "ic95_inf_pct": round(float((np.exp(ci_l) - 1.0) * 100.0), 2),
                    "ic95_sup_pct": round(float((np.exp(ci_h) - 1.0) * 100.0), 2),
                }
            )

    # Perfil salario por hora promedio según escolaridad y sector (para visualización)
    perfil_esc = (
        sub.assign(
            esc_redondeada=sub["escolaridad"].clip(0, 20).round().astype(int),
            sector_bin=np.where(sub["formal"].eq(1), "Formal", "Informal"),
        )
        .groupby(["sector_bin", "esc_redondeada"])
        .apply(
            lambda g: pd.Series(
                {
                    "n_obs": len(g),
                    "salario_hora_medio": float(np.average(g["salario_hora"], weights=g["fexp"])),
                    "ingreso_mensual_medio": float(
                        np.average(g["ingrl_positivo"], weights=g["fexp"])
                    ),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    perfil_esc = perfil_esc.loc[perfil_esc["n_obs"] >= 25].reset_index(drop=True)

    return {
        "n_muestra_mincer": int(len(sub)),
        "experiencia_pico_anios": round(float(exp_pico), 1),
        "modelos": {
            "m1_base": _resumen_modelo(
                "1. Mincer clásico (escolaridad + exp + mujer + rural)",
                res1_cl,
                res1_ols,
                len(sub),
                int(sub["upm"].nunique()),
            ),
            "m2_formalidad": _resumen_modelo(
                "2. + Formalidad y afiliación IESS",
                res2_cl,
                res2_ols,
                len(sub),
                int(sub["upm"].nunique()),
            ),
            "m3_completo": _resumen_modelo(
                "3. + Etnia, EF Rama (21) y EF Provincia (24)",
                res3_cl,
                res3_ols,
                len(sub),
                int(sub["upm"].nunique()),
            ),
            "m4_sector_formal": _resumen_modelo(
                "4. Submuestra Sector Formal",
                res_for_cl,
                res_for_ols,
                len(sub_for),
                int(sub_for["upm"].nunique()),
            ),
            "m5_sector_informal": _resumen_modelo(
                "5. Submuestra Sector Informal",
                res_inf_cl,
                res_inf_ols,
                len(sub_inf),
                int(sub_inf["upm"].nunique()),
            ),
        },
        "efecto_diploma": efectos_diploma,
        "perfil_escolaridad_sector": perfil_esc.to_dict(orient="records"),
    }
