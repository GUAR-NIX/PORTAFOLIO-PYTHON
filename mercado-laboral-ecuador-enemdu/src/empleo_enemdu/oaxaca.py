"""Descomposición de Kitagawa-Oaxaca-Blinder ponderada y brecha cuantílica de género."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from empleo_enemdu.encuesta import cuantil_ponderado
from empleo_enemdu.mincer import preparar_muestra_mincer


def _wls_numpy(X: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Resuelve Mínimos Cuadrados Ponderados (WLS) de forma vectorizada."""
    raiz_w = np.sqrt(w)[:, None]
    Xw = X * raiz_w
    yw = y * np.sqrt(w)
    beta, _, _, _ = np.linalg.lstsq(Xw, yw, rcond=None)
    return beta


def _calcular_oaxaca_una_pasada(
    X_h: np.ndarray,
    y_h: np.ndarray,
    w_h: np.ndarray,
    X_m: np.ndarray,
    y_m: np.ndarray,
    w_m: np.ndarray,
    X_pool: np.ndarray,
    y_pool: np.ndarray,
    w_pool: np.ndarray,
) -> dict[str, Any]:
    """Ejecuta la descomposición de Oaxaca-Blinder (referencia agrupada de Neumark y referencia masculina)."""
    b_h = _wls_numpy(X_h, y_h, w_h)
    b_m = _wls_numpy(X_m, y_m, w_m)
    # En la especificación agrupada de Neumark / Jann se incluye el indicador de grupo para no sesgar beta*
    b_pool_full = _wls_numpy(X_pool, y_pool, w_pool)
    b_star = b_pool_full[:-1]  # excluye la columna dummy de sexo

    media_xh = np.average(X_h, axis=0, weights=w_h)
    media_xm = np.average(X_m, axis=0, weights=w_m)
    media_yh = float(np.average(y_h, weights=w_h))
    media_ym = float(np.average(y_m, weights=w_m))

    brecha_total = media_yh - media_ym

    # Descomposición agrupada (Neumark / Oaxaca-Ransom)
    contrib_explicada = (media_xh - media_xm) * b_star
    contrib_no_explicada = media_xh * (b_h - b_star) + media_xm * (b_star - b_m)

    explicada_total = float(np.sum(contrib_explicada))
    no_explicada_total = float(np.sum(contrib_no_explicada))

    # Descomposición con referencia masculina (b_h)
    explicada_ref_h = float(np.sum((media_xh - media_xm) * b_h))
    no_explicada_ref_h = float(np.sum(media_xm * (b_h - b_m)))

    return {
        "media_log_h": media_yh,
        "media_log_m": media_ym,
        "brecha_log_total": brecha_total,
        "explicada_log": explicada_total,
        "no_explicada_log": no_explicada_total,
        "explicada_ref_h_log": explicada_ref_h,
        "no_explicada_ref_h_log": no_explicada_ref_h,
        "contrib_explicada": contrib_explicada,
        "contrib_no_explicada": contrib_no_explicada,
        "media_xh": media_xh,
        "media_xm": media_xm,
    }


def descomposicion_oaxaca_blinder(
    df: pd.DataFrame,
    *,
    variable_objetivo: str = "log_salario_hora",
    n_boot: int = 120,
    semilla: int = 42,
) -> dict[str, Any]:
    """Descompone la brecha salarial Hombre - Mujer con pesos muestrales y bootstrap por UPM."""
    sub = preparar_muestra_mincer(df)
    sub = sub.loc[sub[variable_objetivo].notna()].copy()

    # Bloques de variables explicativas
    cols_base = [
        "escolaridad",
        "experiencia",
        "experiencia_cuad",
        "informal",
        "afiliado_seguro",
        "rural",
        "indigena",
        "afro_montubio",
    ]
    dummies_rama = pd.get_dummies(
        sub["rama1"].fillna(0).astype(int), prefix="rama", drop_first=True, dtype=np.float64
    )
    X_df = pd.concat(
        [
            pd.Series(1.0, index=sub.index, name="constante"),
            sub[cols_base].astype(np.float64),
            dummies_rama,
        ],
        axis=1,
    )
    nombres_cols = list(X_df.columns)
    X_mat = X_df.to_numpy(dtype=np.float64)
    y_vec = sub[variable_objetivo].to_numpy(dtype=np.float64)
    w_vec = sub["fexp"].to_numpy(dtype=np.float64)
    es_hombre = (sub["p02"] == 1).to_numpy()
    es_mujer = (sub["p02"] == 2).to_numpy()

    X_pool = np.column_stack([X_mat, es_hombre.astype(np.float64)])

    res_puntual = _calcular_oaxaca_una_pasada(
        X_mat[es_hombre],
        y_vec[es_hombre],
        w_vec[es_hombre],
        X_mat[es_mujer],
        y_vec[es_mujer],
        w_vec[es_mujer],
        X_pool,
        y_vec,
        w_vec,
    )

    # Bootstrap por conglomerados (UPM) para errores estándar e IC 95%
    rng = np.random.default_rng(semilla)
    upm_codes, upm_inv = np.unique(sub["upm"].to_numpy(), return_inverse=True)
    n_upms = len(upm_codes)

    boot_brecha = np.zeros(n_boot)
    boot_exp = np.zeros(n_boot)
    boot_no_exp = np.zeros(n_boot)

    for b in range(n_boot):
        conteos_upm = np.bincount(rng.integers(0, n_upms, size=n_upms), minlength=n_upms)
        mult_i = conteos_upm[upm_inv].astype(np.float64)
        w_boot = w_vec * mult_i
        rb = _calcular_oaxaca_una_pasada(
            X_mat[es_hombre],
            y_vec[es_hombre],
            w_boot[es_hombre],
            X_mat[es_mujer],
            y_vec[es_mujer],
            w_boot[es_mujer],
            X_pool,
            y_vec,
            w_boot,
        )
        boot_brecha[b] = rb["brecha_log_total"]
        boot_exp[b] = rb["explicada_log"]
        boot_no_exp[b] = rb["no_explicada_log"]

    # Agrupación de contribuciones por componente conceptual
    grupos_componentes: dict[str, list[int]] = {
        "Escolaridad (años aprobados)": [nombres_cols.index("escolaridad")],
        "Experiencia potencial": [
            nombres_cols.index("experiencia"),
            nombres_cols.index("experiencia_cuad"),
        ],
        "Formalidad y seguridad social (IESS)": [
            nombres_cols.index("informal"),
            nombres_cols.index("afiliado_seguro"),
        ],
        "Área y etnia": [
            nombres_cols.index("rural"),
            nombres_cols.index("indigena"),
            nombres_cols.index("afro_montubio"),
        ],
        "Segregación por rama económica (CIIU)": [
            i for i, c in enumerate(nombres_cols) if c.startswith("rama_")
        ],
        "Constante (brecha base inobservada)": [nombres_cols.index("constante")],
    }

    desglose_componentes: list[dict[str, Any]] = []
    for nombre_comp, idxs in grupos_componentes.items():
        val_exp = float(np.sum(res_puntual["contrib_explicada"][idxs]))
        val_no_exp = float(np.sum(res_puntual["contrib_no_explicada"][idxs]))
        desglose_componentes.append(
            {
                "componente": nombre_comp,
                "dotaciones_log": round(val_exp, 5),
                "dotaciones_pct_aprox": round(val_exp * 100.0, 2),
                "retornos_log": round(val_no_exp, 5),
                "retornos_pct_aprox": round(val_no_exp * 100.0, 2),
            }
        )

    # Comparación directa de promedios Hombre vs Mujer (mensual, por hora, horas y escolaridad)
    sub_h = sub.loc[es_hombre]
    sub_m = sub.loc[es_mujer]
    ing_mes_h = float(np.average(sub_h["ingrl_positivo"], weights=sub_h["fexp"]))
    ing_mes_m = float(np.average(sub_m["ingrl_positivo"], weights=sub_m["fexp"]))
    sal_hr_h = float(np.average(sub_h["salario_hora"], weights=sub_h["fexp"]))
    sal_hr_m = float(np.average(sub_m["salario_hora"], weights=sub_m["fexp"]))
    horas_h = float(np.average(sub_h["horas_semana"], weights=sub_h["fexp"]))
    horas_m = float(np.average(sub_m["horas_semana"], weights=sub_m["fexp"]))
    esc_h = float(np.average(sub_h["escolaridad"], weights=sub_h["fexp"]))
    esc_m = float(np.average(sub_m["escolaridad"], weights=sub_m["fexp"]))

    return {
        "variable_objetivo": variable_objetivo,
        "n_hombres": int(np.sum(es_hombre)),
        "n_mujeres": int(np.sum(es_mujer)),
        "descriptivos_ocupados": {
            "ingreso_mensual_hombre_usd": round(ing_mes_h, 2),
            "ingreso_mensual_mujer_usd": round(ing_mes_m, 2),
            "brecha_mensual_bruta_pct": round(((ing_mes_h - ing_mes_m) / ing_mes_h) * 100.0, 2),
            "salario_hora_hombre_usd": round(sal_hr_h, 2),
            "salario_hora_mujer_usd": round(sal_hr_m, 2),
            "brecha_hora_bruta_pct": round(((sal_hr_h - sal_hr_m) / sal_hr_h) * 100.0, 2),
            "horas_semana_hombre": round(horas_h, 1),
            "horas_semana_mujer": round(horas_m, 1),
            "escolaridad_media_hombre": round(esc_h, 2),
            "escolaridad_media_mujer": round(esc_m, 2),
        },
        "resumen_oaxaca": {
            "media_log_hombre": round(res_puntual["media_log_h"], 4),
            "media_log_mujer": round(res_puntual["media_log_m"], 4),
            "brecha_log_total": round(res_puntual["brecha_log_total"], 4),
            "brecha_pct": round((np.exp(res_puntual["brecha_log_total"]) - 1.0) * 100.0, 2),
            "ee_brecha_log": round(float(np.std(boot_brecha, ddof=1)), 4),
            "dotaciones_explicada_log": round(res_puntual["explicada_log"], 4),
            "dotaciones_explicada_pct": round(
                (np.exp(res_puntual["explicada_log"]) - 1.0) * 100.0, 2
            ),
            "ee_dotaciones_log": round(float(np.std(boot_exp, ddof=1)), 4),
            "ic95_dotaciones_log": [
                round(float(np.percentile(boot_exp, 2.5)), 4),
                round(float(np.percentile(boot_exp, 97.5)), 4),
            ],
            "retornos_no_explicada_log": round(res_puntual["no_explicada_log"], 4),
            "retornos_no_explicada_pct": round(
                (np.exp(res_puntual["no_explicada_log"]) - 1.0) * 100.0, 2
            ),
            "ee_retornos_log": round(float(np.std(boot_no_exp, ddof=1)), 4),
            "ic95_retornos_log": [
                round(float(np.percentile(boot_no_exp, 2.5)), 4),
                round(float(np.percentile(boot_no_exp, 97.5)), 4),
            ],
            "dotaciones_ref_hombre_log": round(res_puntual["explicada_ref_h_log"], 4),
            "retornos_ref_hombre_log": round(res_puntual["no_explicada_ref_h_log"], 4),
        },
        "componentes": desglose_componentes,
    }


def brecha_cuantilica_genero(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula la brecha salarial Hombre vs Mujer por cuantiles (piso pegajoso vs techo de cristal)."""
    sub = preparar_muestra_mincer(df)
    cuantiles = [0.10, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.75, 0.80, 0.90]

    sectores = [
        ("Total ocupados", np.ones(len(sub), dtype=bool)),
        ("Sector formal", sub["formal"].eq(1).to_numpy()),
        ("Sector informal", sub["informal"].eq(1).to_numpy()),
    ]

    filas: list[dict[str, Any]] = []
    for nombre_sec, masc_sec in sectores:
        s_h = sub.loc[masc_sec & (sub["p02"] == 1)]
        s_m = sub.loc[masc_sec & (sub["p02"] == 2)]

        qh_mes = cuantil_ponderado(s_h["ingrl_positivo"], s_h["fexp"], cuantiles)
        qm_mes = cuantil_ponderado(s_m["ingrl_positivo"], s_m["fexp"], cuantiles)
        qh_hr = cuantil_ponderado(s_h["salario_hora"], s_h["fexp"], cuantiles)
        qm_hr = cuantil_ponderado(s_m["salario_hora"], s_m["fexp"], cuantiles)

        for q, vh_m, vm_m, vh_h, vm_h in zip(cuantiles, qh_mes, qm_mes, qh_hr, qm_hr):
            filas.append(
                {
                    "sector": nombre_sec,
                    "percentil": int(round(q * 100)),
                    "ingreso_mes_hombre_usd": round(float(vh_m), 2),
                    "ingreso_mes_mujer_usd": round(float(vm_m), 2),
                    "brecha_mensual_pct": round(float(((vh_m - vm_m) / vh_m) * 100.0), 2),
                    "salario_hora_hombre_usd": round(float(vh_h), 2),
                    "salario_hora_mujer_usd": round(float(vm_h), 2),
                    "brecha_hora_pct": round(float(((vh_h - vm_h) / vh_h) * 100.0), 2),
                    "diferencia_log_hora": round(float(np.log(vh_h) - np.log(vm_h)), 4),
                }
            )
    return pd.DataFrame(filas)
