"""Análisis de efectividad policial, arrestos y tipologías delictivas.

Calcula tasas de arresto con intervalos de confianza de Wilson al 95%,
evolución temporal de efectividad por tipo de delito, patrones de violencia
doméstica y contrastes estadísticos entre los distritos policiales de Chicago.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from delitos_chicago.config import FIGURAS, REPORTES


def intervalo_confianza_proporcion(
    exitos: int,
    total: int,
    confianza: float = 0.95,
) -> tuple[float, float]:
    """Calcula el intervalo de confianza de Wilson para una proporción."""
    if total == 0:
        return (0.0, 0.0)
    z = stats.norm.ppf(1 - (1 - confianza) / 2)
    p = exitos / total
    denominador = 1 + (z**2) / total
    centro = (p + (z**2) / (2 * total)) / denominador
    margen = (z * np.sqrt((p * (1 - p) + (z**2) / (4 * total)) / total)) / denominador
    return (max(0.0, centro - margen), min(1.0, centro + margen))


def tasa_arresto_por_tipo(df: pd.DataFrame, min_casos: int = 500) -> pd.DataFrame:
    """Calcula la tasa de arresto global por tipo de delito con intervalos de confianza."""
    resumen = (
        df.groupby("tipo_primario", observed=True)
        .agg(
            delitos=("id_delito", "count"),
            arrestos=("arresto", lambda x: int(x.sum())),
        )
        .reset_index()
    )
    resumen = resumen[resumen["delitos"] >= min_casos].copy()
    resumen["tasa_arresto"] = (resumen["arrestos"] / resumen["delitos"]).round(4)
    resumen["tasa_arresto_pct"] = (resumen["tasa_arresto"] * 100).round(2)

    # Calcular IC 95% para cada tipo
    ics = [
        intervalo_confianza_proporcion(int(row["arrestos"]), int(row["delitos"]))
        for _, row in resumen.iterrows()
    ]
    resumen["ic_inf_pct"] = [round(ic[0] * 100, 2) for ic in ics]
    resumen["ic_sup_pct"] = [round(ic[1] * 100, 2) for ic in ics]
    resumen["margen_error_pct"] = (
        (resumen["ic_sup_pct"] - resumen["ic_inf_pct"]) / 2
    ).round(2)

    return resumen.sort_values("tasa_arresto", ascending=False)


def evolucion_arresto_anual(df: pd.DataFrame, tipos_top: list[str] | None = None) -> pd.DataFrame:
    """Evolución anual de la tasa de arresto para los delitos principales."""
    if tipos_top is None:
        tipos_top = ["NARCOTICS", "WEAPONS VIOLATION", "BATTERY", "ASSAULT", "ROBBERY", "THEFT", "BURGLARY", "MOTOR VEHICLE THEFT"]

    sub = df[df["tipo_primario"].isin(tipos_top)].copy()
    anual = (
        sub.groupby(["anio", "tipo_primario"], observed=True)
        .agg(delitos=("id_delito", "count"), arrestos=("arresto", "sum"))
        .reset_index()
    )
    anual["tasa_arresto_pct"] = ((anual["arrestos"] / anual["delitos"]) * 100).round(2)
    return anual


def analisis_distritos_policiales(df: pd.DataFrame) -> pd.DataFrame:
    """Métricas operativas agregadas por distrito policial con IC al 95%."""
    distritos = (
        df[df["distrito"].notna()]
        .groupby("distrito")
        .agg(
            total_delitos=("id_delito", "count"),
            arrestos=("arresto", "sum"),
            domesticos=("domestico", "sum"),
        )
        .reset_index()
    )
    distritos["distrito"] = distritos["distrito"].astype(int)
    distritos["tasa_arresto_pct"] = (
        (distritos["arrestos"] / distritos["total_delitos"]) * 100
    ).round(2)
    distritos["pct_domestico"] = (
        (distritos["domesticos"] / distritos["total_delitos"]) * 100
    ).round(2)

    ics = [
        intervalo_confianza_proporcion(int(r["arrestos"]), int(r["total_delitos"]))
        for _, r in distritos.iterrows()
    ]
    distritos["ic_inf_arresto"] = [round(ic[0] * 100, 2) for ic in ics]
    distritos["ic_sup_arresto"] = [round(ic[1] * 100, 2) for ic in ics]

    return distritos.sort_values("total_delitos", ascending=False)


def analisis_violencia_domestica(df: pd.DataFrame) -> dict[str, Any]:
    """Estudia patrones específicos de violencia doméstica."""
    total = len(df)
    domesticos = int(df["domestico"].sum())
    pct_domestico = round((domesticos / total) * 100, 2) if total else 0.0

    tipos_domesticos = (
        df[df["domestico"] == True]["tipo_primario"]
        .value_counts()
        .head(8)
        .to_dict()
    )

    tasa_arresto_dom = round(
        (df[df["domestico"] == True]["arresto"].sum() / domesticos * 100), 2
    ) if domesticos else 0.0

    no_domesticos = total - domesticos
    tasa_arresto_no_dom = round(
        (df[df["domestico"] == False]["arresto"].sum() / no_domesticos * 100), 2
    ) if no_domesticos else 0.0

    return {
        "delitos_domesticos": domesticos,
        "delitos_no_domesticos": no_domesticos,
        "proporcion_domestica_pct": pct_domestico,
        "tasa_arresto_domestico_pct": tasa_arresto_dom,
        "tasa_arresto_no_domestico_pct": tasa_arresto_no_dom,
        "tipos_frecuentes_domestico": tipos_domesticos,
    }


# ── Figuras ─────────────────────────────────────────────────────────────────

def graficar_tasa_arresto_por_tipo(
    df_tasas: pd.DataFrame,
    ruta: Path = FIGURAS / "08_tasa_arresto_por_tipo.png",
) -> Path:
    """Gráfico de barras horizontales con barra de error IC 95% por tipo de delito."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df_plot = df_tasas.head(15).iloc[::-1]

    fig, ax = plt.subplots(figsize=(12, 7))
    errores = [
        df_plot["tasa_arresto_pct"] - df_plot["ic_inf_pct"],
        df_plot["ic_sup_pct"] - df_plot["tasa_arresto_pct"],
    ]

    ax.barh(
        df_plot["tipo_primario"],
        df_plot["tasa_arresto_pct"],
        xerr=errores,
        capsize=4,
        color="#2E7D32",
        alpha=0.85,
        edgecolor="#1B5E20",
    )
    ax.set_xlabel("Tasa de Arresto Efectiva (%) con Intervalo de Confianza al 95%")
    ax.set_title("Efectividad Policial por Tipo de Delito — Chicago (Top 15 Tipos)")
    ax.grid(axis="x", linestyle="--", alpha=0.5)

    fig.tight_layout()
    fig.savefig(ruta, dpi=180)
    plt.close(fig)
    return ruta


def graficar_distritos_comparativa(
    df_distritos: pd.DataFrame,
    ruta: Path = FIGURAS / "09_distritos_policiales_efectividad.png",
) -> Path:
    """Comparación de volumen vs efectividad de arresto por distrito policial."""
    ruta.parent.mkdir(parents=True, exist_ok=True)

    fig, ax1 = plt.subplots(figsize=(14, 6))

    distritos = df_distritos.sort_values("distrito")
    x = np.arange(len(distritos))
    ancho = 0.4

    color1 = "#1565C0"
    ax1.bar(x - ancho / 2, distritos["total_delitos"], ancho, label="Volumen de Delitos", color=color1, alpha=0.8)
    ax1.set_xlabel("Distrito Policial")
    ax1.set_ylabel("Total Delitos", color=color1)
    ax1.tick_params(axis="y", labelcolor=color1)
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"D{int(d)}" for d in distritos["distrito"]], rotation=45)

    ax2 = ax1.twinx()
    color2 = "#D84315"
    ax2.plot(x + ancho / 2, distritos["tasa_arresto_pct"], color=color2, marker="o", linewidth=2, label="Tasa Arresto (%)")
    ax2.set_ylabel("Tasa de Arresto (%)", color=color2)
    ax2.tick_params(axis="y", labelcolor=color2)

    plt.title("Volumen Delictivo vs. Tasa de Arresto por Distrito Policial de Chicago")
    fig.tight_layout()
    fig.savefig(ruta, dpi=180)
    plt.close(fig)
    return ruta
