"""Pronóstico mensual de delitos por distrito policial con backtesting de origen móvil.

- Series mensuales completas por distrito (meses sin registros = 0), solo hasta el último mes completo.
- Variables sin fuga: rezagos 1, 2, 3 y 12, medias móviles del pasado y calendario.
- Backtesting de origen móvil: en cada corte se reentrena con lo anterior al corte y se pronostican
  los meses siguientes un paso adelante (el mes previo ya se conoce al pronosticar el siguiente).
- Intervalos de predicción al 90 % calibrados fuera de muestra: en cada corte, el modelo se ajusta
  también con datos hasta 12 meses antes y los cocientes real/predicho de esos 12 meses dan los cuantiles.
- Modelos: línea base estacional (t−12), media móvil de 3 meses, Ridge y Random Forest.
"""
from __future__ import annotations

from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error

from delitos_chicago.config import FIGURAS

VARIABLES = ["distrito", "mes", "tendencia", "lag_1", "lag_2", "lag_3", "lag_12", "media_movil_3", "media_movil_6"]
MODELOS = {
    "Linea_Base_Estacional_t12": "Línea base estacional (t−12)",
    "Linea_Base_Promedio_Movil3": "Media móvil 3 meses",
    "Modelo_Ridge": "Ridge",
    "Modelo_Random_Forest": "Random Forest",
}


def ultimo_mes_completo(fecha_maxima: pd.Timestamp) -> pd.Timestamp:
    """Inicio del último mes cubierto entero por los datos (si el último día no es fin de mes, se descarta ese mes)."""
    fecha_maxima = pd.Timestamp(fecha_maxima)
    inicio_mes = fecha_maxima.to_period("M").to_timestamp()
    if fecha_maxima.normalize() == (inicio_mes + pd.offsets.MonthEnd(0)).normalize():
        return inicio_mes
    return inicio_mes - pd.DateOffset(months=1)


def preparar_series_mensuales_distrito(
    df: pd.DataFrame, hasta: pd.Timestamp | None = None, min_media_mensual: float = 50.0
) -> pd.DataFrame:
    """Conteos por mes y distrito en una grilla completa (meses vacíos = 0).

    Se excluyen distritos con media inferior a `min_media_mensual` en los últimos 12 meses
    (distritos con muy pocos incidentes), cuyo error relativo no es informativo.
    """
    sub = df[df["distrito"].notna()]
    periodo = pd.to_datetime(sub["fecha"]).dt.to_period("M").dt.to_timestamp()
    tabla = pd.crosstab(periodo, sub["distrito"].astype(int))
    tabla = tabla.asfreq("MS", fill_value=0)
    if hasta is not None:
        tabla = tabla[tabla.index <= pd.Timestamp(hasta)]
    activos = tabla.tail(12).mean() >= min_media_mensual
    tabla = tabla.loc[:, activos]
    serie = tabla.stack().rename("delitos").reset_index()
    serie.columns = ["fecha", "distrito", "delitos"]
    return serie.sort_values(["distrito", "fecha"]).reset_index(drop=True)


def construir_caracteristicas_tiempo(df_serie: pd.DataFrame) -> pd.DataFrame:
    """Rezagos y medias móviles calculados solo con meses anteriores (sin fuga de información)."""
    partes = []
    for _, grupo in df_serie.groupby("distrito"):
        g = grupo.sort_values("fecha").copy()
        g["mes"] = g["fecha"].dt.month
        g["tendencia"] = (g["fecha"].dt.year - 2001) * 12 + g["fecha"].dt.month - 1
        pasado = g["delitos"].shift(1)
        for k in (1, 2, 3, 12):
            g[f"lag_{k}"] = g["delitos"].shift(k)
        g["media_movil_3"] = pasado.rolling(3).mean()
        g["media_movil_6"] = pasado.rolling(6).mean()
        g["linea_base_estacional"] = g["lag_12"]
        g["linea_base_promedio"] = g["media_movil_3"]
        partes.append(g)
    return pd.concat(partes, ignore_index=True).dropna().reset_index(drop=True)


def evaluar_metricas(reales: np.ndarray, predichos: np.ndarray) -> dict[str, float]:
    """MAE, RMSE, WAPE y sesgo porcentual."""
    reales, predichos = np.asarray(reales, dtype=float), np.asarray(predichos, dtype=float)
    return {
        "MAE": round(float(mean_absolute_error(reales, predichos)), 2),
        "RMSE": round(float(np.sqrt(mean_squared_error(reales, predichos))), 2),
        "WAPE_pct": round(float(np.sum(np.abs(reales - predichos)) / np.sum(reales) * 100), 2),
        "Sesgo_pct": round(float(np.sum(predichos - reales) / np.sum(reales) * 100), 2),
    }


def _ajustar_y_predecir(entreno: pd.DataFrame, prueba: pd.DataFrame) -> dict[str, np.ndarray]:
    """Ajusta Ridge y Random Forest con `entreno` y devuelve las predicciones de los cuatro modelos para `prueba`."""
    ridge = Ridge(alpha=10.0).fit(entreno[VARIABLES], entreno["delitos"])
    bosque = RandomForestRegressor(n_estimators=200, max_depth=8, min_samples_leaf=3, random_state=42, n_jobs=4)
    bosque.fit(entreno[VARIABLES], entreno["delitos"])
    return {
        "Linea_Base_Estacional_t12": prueba["linea_base_estacional"].to_numpy(),
        "Linea_Base_Promedio_Movil3": prueba["linea_base_promedio"].to_numpy(),
        "Modelo_Ridge": ridge.predict(prueba[VARIABLES]),
        "Modelo_Random_Forest": bosque.predict(prueba[VARIABLES]),
    }


def origenes_trimestrales(ultimo_mes: pd.Timestamp, n_cortes: int = 8, horizonte: int = 3) -> list[pd.Timestamp]:
    """Cortes cada `horizonte` meses de modo que el último bloque termine en `ultimo_mes`."""
    primero = pd.Timestamp(ultimo_mes) - pd.DateOffset(months=n_cortes * horizonte - 1)
    return [primero + pd.DateOffset(months=horizonte * k) for k in range(n_cortes)]


def backtesting_origen_movil(
    df_caracteristicas: pd.DataFrame,
    origenes: list[pd.Timestamp],
    horizonte: int = 3,
    meses_calibracion: int = 12,
    nivel: float = 0.90,
) -> dict[str, Any]:
    """Backtesting de origen móvil con intervalos de predicción calibrados fuera de muestra.

    Para cada corte O: entrena con fecha < O y predice [O, O + horizonte). Para el intervalo, ajusta
    otra vez con fecha < O − `meses_calibracion`, predice esos 12 meses de calibración (que el modelo
    no vio) y usa los cuantiles del cociente real/predicho; ningún dato ≥ O entra en el intervalo.
    """
    a = (1 - nivel) / 2
    filas = []
    for origen in origenes:
        origen = pd.Timestamp(origen)
        fin = origen + pd.DateOffset(months=horizonte)
        entreno = df_caracteristicas[df_caracteristicas["fecha"] < origen]
        prueba = df_caracteristicas[(df_caracteristicas["fecha"] >= origen) & (df_caracteristicas["fecha"] < fin)].copy()
        if entreno.empty or prueba.empty:
            continue
        inicio_cal = origen - pd.DateOffset(months=meses_calibracion)
        entreno_cal = df_caracteristicas[df_caracteristicas["fecha"] < inicio_cal]
        calibra = df_caracteristicas[(df_caracteristicas["fecha"] >= inicio_cal) & (df_caracteristicas["fecha"] < origen)]
        pred = _ajustar_y_predecir(entreno, prueba)
        pred_cal = _ajustar_y_predecir(entreno_cal, calibra)
        prueba["origen"] = origen
        for modelo, valores in pred.items():
            cociente = calibra["delitos"].to_numpy() / np.maximum(pred_cal[modelo], 1e-9)
            q_inf, q_sup = np.quantile(cociente, [a, 1 - a])
            prueba[f"pred_{modelo}"] = valores
            prueba[f"inf_{modelo}"] = valores * q_inf
            prueba[f"sup_{modelo}"] = valores * q_sup
        filas.append(prueba)
    resultados = pd.concat(filas, ignore_index=True)

    metricas, por_origen, intervalos = {}, [], {}
    for modelo in MODELOS:
        metricas[modelo] = evaluar_metricas(resultados["delitos"], resultados[f"pred_{modelo}"])
        dentro = resultados["delitos"].between(resultados[f"inf_{modelo}"], resultados[f"sup_{modelo}"])
        ancho = (resultados[f"sup_{modelo}"] - resultados[f"inf_{modelo}"]) / resultados[f"pred_{modelo}"]
        intervalos[modelo] = {
            "cobertura_pct": round(float(dentro.mean() * 100), 1),
            "ancho_relativo_mediano_pct": round(float(ancho.median() * 100), 1),
        }
        for origen, grupo in resultados.groupby("origen"):
            por_origen.append({"origen": origen.strftime("%Y-%m"), "modelo": modelo,
                               **evaluar_metricas(grupo["delitos"], grupo[f"pred_{modelo}"])})
    por_origen = pd.DataFrame(por_origen)
    resumen_origen = por_origen.groupby("modelo")["WAPE_pct"].agg(["mean", "std", "min", "max"]).round(2)
    victorias = por_origen.loc[por_origen.groupby("origen")["WAPE_pct"].idxmin(), "modelo"].value_counts()
    for modelo in MODELOS:
        metricas[modelo].update({
            "WAPE_medio_por_corte": float(resumen_origen.loc[modelo, "mean"]),
            "WAPE_desv_por_corte": float(resumen_origen.loc[modelo, "std"]),
            "cortes_ganados": int(victorias.get(modelo, 0)),
            **intervalos[modelo],
        })
    ganador = min(MODELOS, key=lambda m: metricas[m]["WAPE_pct"])
    base = metricas["Linea_Base_Estacional_t12"]["WAPE_pct"]
    return {
        "metricas": metricas,
        "por_origen": por_origen,
        "resultados": resultados,
        "ganador": ganador,
        "configuracion": {
            "cortes": len(origenes),
            "horizonte_meses": horizonte,
            "primer_mes_evaluado": resultados["fecha"].min().strftime("%Y-%m"),
            "ultimo_mes_evaluado": resultados["fecha"].max().strftime("%Y-%m"),
            "meses_evaluados": int(resultados["fecha"].nunique()),
            "distritos": int(resultados["distrito"].nunique()),
            "nivel_intervalo": nivel,
            "meses_calibracion_intervalo": meses_calibracion,
        },
        "mejora_ganador_vs_estacional_pct": round((base - metricas[ganador]["WAPE_pct"]) / base * 100, 1),
    }


# ── Figuras ─────────────────────────────────────────────────────────────────

def graficar_pronostico_vs_real(resultados: pd.DataFrame, ganador: str, ruta=FIGURAS / "10_pronostico_vs_real.png"):
    """Ciudad (suma de distritos) y el distrito con más delitos, con el intervalo de predicción del ganador."""
    nombre = MODELOS[ganador]
    ciudad = resultados.groupby("fecha")[["delitos", f"pred_{ganador}", "pred_Linea_Base_Estacional_t12"]].sum()
    top = resultados.groupby("distrito")["delitos"].sum().idxmax()
    dist = resultados[resultados["distrito"] == top].set_index("fecha")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5))
    ax1.plot(ciudad.index, ciudad["delitos"], "o-", color="#212121", label="Real")
    ax1.plot(ciudad.index, ciudad[f"pred_{ganador}"], "s--", color="#2E7D32", label=nombre)
    ax1.plot(ciudad.index, ciudad["pred_Linea_Base_Estacional_t12"], "^:", color="#C62828", label="Base estacional (t−12)")
    ax1.set_title("Ciudad: suma de los pronósticos por distrito")
    ax1.set_ylabel("Delitos por mes")
    ax2.fill_between(dist.index, dist[f"inf_{ganador}"], dist[f"sup_{ganador}"], color="#2E7D32", alpha=0.2,
                     label="Intervalo de predicción 90 %")
    ax2.plot(dist.index, dist["delitos"], "o-", color="#212121", label="Real")
    ax2.plot(dist.index, dist[f"pred_{ganador}"], "s--", color="#2E7D32", label=nombre)
    ax2.set_title(f"Distrito {top} (el de más delitos en el periodo evaluado)")
    for ax in (ax1, ax2):
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        ax.tick_params(axis="x", rotation=30)
    fig.suptitle("Backtesting de origen móvil: pronóstico a un mes, reentrenando cada 3 meses")
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
    return ruta


def graficar_comparacion_modelos(por_origen: pd.DataFrame, ruta=FIGURAS / "11_comparativa_errores_modelos.png"):
    """WAPE de cada modelo en cada corte del backtesting."""
    tabla = por_origen.pivot(index="origen", columns="modelo", values="WAPE_pct")[list(MODELOS)]
    tabla.columns = [MODELOS[c] for c in tabla.columns]
    fig, ax = plt.subplots(figsize=(12, 5))
    tabla.plot(ax=ax, marker="o", color=["#9E9E9E", "#BDBDBD", "#2E7D32", "#1565C0"])
    ax.set_ylabel("WAPE (%) — menor es mejor")
    ax.set_xlabel("Corte (primer mes pronosticado)")
    ax.set_title("WAPE por corte del backtesting de origen móvil")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
    return ruta
