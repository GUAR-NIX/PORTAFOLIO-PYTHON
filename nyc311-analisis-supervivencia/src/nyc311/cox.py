"""Modelos de Cox de riesgos proporcionales con lifelines y verificación del supuesto PH.

Aquí el «riesgo» (hazard) es la tasa instantánea de **cierre**: un hazard ratio (HR) > 1 significa que la
solicitud se cierra **más rápido** que la categoría de referencia y HR < 1, **más lento**.

* Modelo A (descriptivo): agencia, borough, canal, fin de semana y franja nocturna.
* Modelo B (equidad): estratificado por tipo de queja (cada tipo tiene su propio riesgo base, sin
  imponerle forma), con borough, canal, fin de semana y franja nocturna. Compara barrios **dentro del
  mismo tipo de queja**.

lifelines con 7 M de filas y empates en segundos es lento y pesado, así que los modelos se ajustan en
una muestra aleatoria fija (`N_MUESTRA_COX`, semilla 311); con ese tamaño los IC de los HR ya son
estrechos (±1–3 %).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from lifelines import CoxPHFitter
from lifelines.statistics import proportional_hazard_test

from nyc311.config import SEMILLA
from nyc311.limpieza import agrupar_top

N_MUESTRA_COX = 200_000
N_MUESTRA_PH = 40_000
REFERENCIAS = {"agencia": "NYPD", "borough": "MANHATTAN", "canal": "Teléfono"}
VENTANAS_DIAS = [(0.0, 1.0), (1.0, 7.0), (7.0, 30.0), (30.0, np.inf)]


def muestra_modelo(df: pd.DataFrame, n: int = N_MUESTRA_COX, semilla: int = SEMILLA) -> pd.DataFrame:
    """Muestra aleatoria con borough conocido y las variables que usan los modelos."""
    base = df.loc[df["borough"].ne("SIN DATO")]
    sub = base.sample(n=min(n, len(base)), random_state=semilla).copy()
    sub["agencia_m"] = agrupar_top(sub["agencia"], 9, "Otras")
    sub["tipo_m"] = agrupar_top(sub["tipo_queja"], 25, "Otros")
    sub["fin_de_semana"] = sub["dia_semana"].ge(5).astype("int8")
    sub["nocturna"] = ((sub["hora"] >= 22) | (sub["hora"] < 6)).astype("int8")
    # Duración 0 (cierre instantáneo): lifelines la admite, pero un piso de 1 s evita avisos numéricos
    sub["duracion_dias"] = sub["duracion_dias"].clip(lower=1 / 86_400)
    return sub


def _dummies(sub: pd.DataFrame, columna: str, prefijo: str, referencia: str) -> pd.DataFrame:
    valores = sub[columna].astype("string")
    niveles = [v for v in valores.unique() if v != referencia]
    return pd.DataFrame({f"{prefijo}{v}": valores.eq(v).astype("int8") for v in sorted(niveles)}, index=sub.index)


def matriz_modelo(sub: pd.DataFrame, modelo: str) -> pd.DataFrame:
    """Matriz de diseño de los modelos A y B (dummies con referencia explícita)."""
    partes = [sub[["duracion_dias", "evento", "fin_de_semana", "nocturna"]]]
    if modelo == "A":
        partes.append(_dummies(sub, "agencia_m", "agencia=", REFERENCIAS["agencia"]))
    partes.append(_dummies(sub, "borough", "borough=", REFERENCIAS["borough"]))
    partes.append(_dummies(sub, "canal", "canal=", REFERENCIAS["canal"]))
    if modelo == "B":
        partes.append(sub[["tipo_m"]].astype("string"))
    return pd.concat(partes, axis=1)


def ajustar(matriz: pd.DataFrame, modelo: str, entry_col: str | None = None) -> CoxPHFitter:
    cph = CoxPHFitter()
    cph.fit(
        matriz,
        duration_col="duracion_dias",
        event_col="evento",
        strata=["tipo_m"] if modelo == "B" else None,
        entry_col=entry_col,
    )
    return cph


def tabla_hr(cph: CoxPHFitter) -> pd.DataFrame:
    """HR con IC 95 %, p-valor y su lectura en lenguaje de negocio."""
    s = cph.summary
    t = pd.DataFrame(
        {
            "covariable": s.index,
            "hr": s["exp(coef)"].to_numpy(),
            "ic_inf": s["exp(coef) lower 95%"].to_numpy(),
            "ic_sup": s["exp(coef) upper 95%"].to_numpy(),
            "p_valor": s["p"].to_numpy(),
        }
    )
    t["lectura"] = [leer_hr(hr, lo, hi) for hr, lo, hi in zip(t["hr"], t["ic_inf"], t["ic_sup"])]
    return t


def leer_hr(hr: float, ic_inf: float, ic_sup: float) -> str:
    """Traduce un HR de cierre a lenguaje de negocio."""
    if ic_inf <= 1 <= ic_sup:
        return "sin diferencia clara con la referencia"
    sentido = "más rápido" if hr > 1 else "más lento"
    return f"en cada momento, {abs(hr - 1) * 100:.0f} % {'más' if hr > 1 else 'menos'} probable cerrarse ({sentido})"


def prueba_supuesto_ph(cph: CoxPHFitter, matriz: pd.DataFrame) -> pd.DataFrame:
    """Prueba de Grambsch-Therneau sobre residuos de Schoenfeld escalados (transformación de rango del tiempo).

    Se reajusta en una submuestra (`N_MUESTRA_PH`): con cientos de miles de filas cualquier desviación
    mínima sale «significativa», así que lo importante es el tamaño del estadístico y la evidencia gráfica.
    """
    sub = matriz.sample(n=min(N_MUESTRA_PH, len(matriz)), random_state=SEMILLA)
    modelo = "B" if "tipo_m" in matriz.columns else "A"
    cph_sub = ajustar(sub, modelo)
    res = proportional_hazard_test(cph_sub, sub, time_transform="rank").summary
    return pd.DataFrame(
        {"covariable": res.index.astype(str), "estadistico": res["test_statistic"].to_numpy(), "p_valor": res["p"].to_numpy()}
    ).sort_values("estadistico", ascending=False)


def hr_por_ventana(matriz: pd.DataFrame, modelo: str, ventanas=VENTANAS_DIAS) -> pd.DataFrame:
    """HR del modelo reestimado en ventanas de tiempo (0–1, 1–7, 7–30, > 30 días).

    Cada ventana usa las solicitudes aún abiertas al inicio (truncamiento por la izquierda con
    `entry_col`) y censura al final. Si el supuesto PH se cumpliera, los HR serían parecidos en todas.
    """
    filas = []
    for desde, hasta in ventanas:
        en_riesgo = matriz.loc[matriz["duracion_dias"] > desde].copy()
        en_riesgo["entrada"] = desde
        if np.isfinite(hasta):
            pasa = en_riesgo["duracion_dias"] > hasta
            en_riesgo.loc[pasa, "evento"] = 0
            en_riesgo.loc[pasa, "duracion_dias"] = hasta
        # Covariables sin variación en la ventana harían singular la matriz
        constantes = [c for c in en_riesgo.columns if c not in ("duracion_dias", "evento", "entrada", "tipo_m")
                      and en_riesgo[c].nunique() < 2]
        cph = ajustar(en_riesgo.drop(columns=constantes), modelo, entry_col="entrada")
        t = tabla_hr(cph)
        t["ventana"] = f"{desde:g}–{hasta:g} d" if np.isfinite(hasta) else f"> {desde:g} d"
        t["n_en_riesgo"] = len(en_riesgo)
        filas.append(t)
    return pd.concat(filas, ignore_index=True)
