"""
Curva de Kuznets ambiental (CKA): ¿las emisiones per cápita suben con el ingreso y luego bajan?

    ln(CO2 pc)_it = a_i + d_t + b1·ln(PIB pc)_it + b2·ln(PIB pc)²_it + e_it

Si b2 < 0 hay "U invertida" y el punto de giro es exp(−b1 / (2·b2)) USD.
Errores estándar agrupados por país (las observaciones de un mismo país no son independientes) e
intervalo del punto de giro con bootstrap por países (remuestrea países completos).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from . import config


def preparar(panel: pd.DataFrame, col_co2_pc: str = "co2_pc_t", anio_fin: int | None = None) -> pd.DataFrame:
    """Solo países (sin la región) con PIB y CO2 per cápita; variables en logaritmo."""
    d = panel[(panel["iso3"] != config.REGION)].dropna(subset=["pib_pc_ppa", col_co2_pc]).copy()
    if anio_fin:
        d = d[d["anio"] <= anio_fin]
    d = d[d[col_co2_pc] > 0]
    d["y"] = np.log(d[col_co2_pc])
    d["x"] = np.log(d["pib_pc_ppa"])
    d["x2"] = d["x"] ** 2
    d["x3"] = d["x"] ** 3
    return d[["iso3", "pais", "anio", "y", "x", "x2", "x3", "pib_pc_ppa", col_co2_pc]].reset_index(drop=True)


def punto_giro(b1: float, b2: float) -> float:
    """Ingreso (USD PPA) donde la parábola en logaritmos alcanza su máximo; NaN si no es U invertida."""
    if not (np.isfinite(b1) and np.isfinite(b2)) or b2 >= 0:
        return np.nan
    exponente = -b1 / (2 * b2)
    return float(np.exp(exponente)) if exponente < 700 else np.inf  # evita desbordar el float


FORMULAS = {
    "pooled": "y ~ x + x2",
    "fe_pais": "y ~ x + x2 + C(iso3)",
    "fe_pais_anio": "y ~ x + x2 + C(iso3) + C(anio)",
    "fe_cubico": "y ~ x + x2 + x3 + C(iso3) + C(anio)",
}


def ajustar(d: pd.DataFrame, especificacion: str = "fe_pais_anio"):
    formula = FORMULAS[especificacion]
    return smf.ols(formula, data=d).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["iso3"])[0]})


def resumen_modelo(modelo, nombre: str, d: pd.DataFrame) -> dict:
    b, se, p = modelo.params, modelo.bse, modelo.pvalues
    tp = punto_giro(b["x"], b["x2"]) if "x3" not in b else np.nan
    fila = {
        "modelo": nombre, "n": int(modelo.nobs), "paises": d["iso3"].nunique(),
        "b1": b["x"], "b1_p": p["x"], "b2": b["x2"], "b2_se": se["x2"], "b2_p": p["x2"],
        "r2": modelo.rsquared, "punto_giro_usd": tp,
        "pib_pc_max_muestra": d["pib_pc_ppa"].max(),
        "pct_obs_sobre_giro": 100 * (d["pib_pc_ppa"] > tp).mean() if np.isfinite(tp) else np.nan,
    }
    if "x3" in b:
        fila.update({"b3": b["x3"], "b3_p": p["x3"]})
    return fila


def _dentro(v: np.ndarray, grupo: np.ndarray, anio: np.ndarray, efecto_anio: bool) -> np.ndarray:
    """Transformación "within": resta medias por país (y por año, si el panel es balanceado)."""
    s = pd.Series(v)
    r = v - s.groupby(grupo).transform("mean").to_numpy()
    if efecto_anio:
        r = r - pd.Series(r).groupby(anio).transform("mean").to_numpy()
    return r


def bootstrap_punto_giro(d: pd.DataFrame, repeticiones: int = 999, efecto_anio: bool = True,
                         semilla: int = 42) -> dict:
    """Bootstrap por países del punto de giro del modelo con efectos fijos (cuadrático)."""
    rng = np.random.default_rng(semilla)
    paises = d["iso3"].unique()
    bloques = {p: d[d["iso3"] == p] for p in paises}
    giros, b2s = [], []
    for _ in range(repeticiones):
        muestra = rng.choice(paises, size=len(paises), replace=True)
        partes = [bloques[p].assign(grupo=i) for i, p in enumerate(muestra)]
        m = pd.concat(partes, ignore_index=True)
        g, a = m["grupo"].to_numpy(), m["anio"].to_numpy()
        y = _dentro(m["y"].to_numpy(), g, a, efecto_anio)
        X = np.column_stack([_dentro(m[c].to_numpy(), g, a, efecto_anio) for c in ("x", "x2")])
        b = np.linalg.lstsq(X, y, rcond=None)[0]
        b2s.append(b[1])
        giros.append(punto_giro(b[0], b[1]))
    giros = np.array(giros)
    validos = giros[~np.isnan(giros)]  # solo las réplicas con U invertida (puede haber infinitos)
    cuantil = (lambda q: float(np.quantile(validos, q, method="nearest"))) if len(validos) else (lambda q: np.nan)
    return {
        "repeticiones": repeticiones,
        "pct_u_invertida": 100 * np.mean(np.array(b2s) < 0),
        "giro_mediana": cuantil(0.5),
        "giro_p05": cuantil(0.05),
        "giro_p95": cuantil(0.95),
        "pct_giro_dentro_muestra": 100 * np.mean(giros <= d["pib_pc_ppa"].max()),
        "giros": giros,
    }


def tabla_modelos(panel: pd.DataFrame) -> pd.DataFrame:
    """Las especificaciones principales lado a lado, más la versión con CO2 de consumo."""
    filas = []
    d = preparar(panel)
    for esp, nombre in [("pooled", "MCO agrupado"), ("fe_pais", "EF país"),
                        ("fe_pais_anio", "EF país + año"), ("fe_cubico", "EF país + año, cúbico")]:
        filas.append(resumen_modelo(ajustar(d, esp), nombre, d))
    dc = preparar(panel, "co2_consumo_pc_t")
    filas.append(resumen_modelo(ajustar(dc, "fe_pais_anio"), "EF país + año, CO2 consumo", dc))
    return pd.DataFrame(filas)


def pendientes_por_pais(panel: pd.DataFrame, col_co2_pc: str = "co2_pc_t") -> pd.DataFrame:
    """Elasticidad ingreso–emisiones de cada país (regresión lineal en logs, errores HAC).

    Si la CKA fuera una ley común, los países más ricos deberían tener pendientes menores."""
    d = preparar(panel, col_co2_pc)
    filas = []
    for (iso3, pais), g in d.groupby(["iso3", "pais"]):
        m = smf.ols("y ~ x", data=g).fit(cov_type="HAC", cov_kwds={"maxlags": 2})
        ci = m.conf_int().loc["x"]
        filas.append({"iso3": iso3, "pais": pais, "elasticidad": m.params["x"], "ic_bajo": ci[0],
                      "ic_alto": ci[1], "r2": m.rsquared, "pib_pc_medio": g["pib_pc_ppa"].mean()})
    return pd.DataFrame(filas).sort_values("elasticidad").reset_index(drop=True)


def curva(modelo, d: pd.DataFrame, puntos: int = 200) -> pd.DataFrame:
    """Curva ajustada (efecto de x y x² sobre la media de la muestra) para graficar."""
    b = modelo.params
    xs = np.linspace(d["x"].min(), d["x"].max(), puntos)
    nivel = d["y"].mean() - (b["x"] * d["x"].mean() + b["x2"] * d["x2"].mean())
    ys = nivel + b["x"] * xs + b["x2"] * xs ** 2
    return pd.DataFrame({"pib_pc_ppa": np.exp(xs), "co2_pc_t": np.exp(ys)})
