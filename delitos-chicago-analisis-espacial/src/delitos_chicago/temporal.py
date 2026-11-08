"""Análisis temporal de delitos de Chicago.

Tendencia anual, patrón hora × día, descomposición STL, serie temporal interrumpida
para el efecto del COVID-19 y cambio de composición por tipo.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import numpy as np
import pandas as pd
import seaborn as sns
from statsmodels.tsa.seasonal import STL

from delitos_chicago.config import FIGURAS

DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def delitos_por_anio_tipo(df: pd.DataFrame) -> pd.DataFrame:
    """Cuenta delitos por año y tipo primario."""
    return (
        df.groupby(["anio", "tipo_primario"], observed=True)
        .size()
        .reset_index(name="conteo")
        .sort_values(["anio", "conteo"], ascending=[True, False])
    )


def mapa_calor_hora_dia(df: pd.DataFrame) -> pd.DataFrame:
    """Tabla hora × día de la semana con el total de delitos."""
    if "fecha" not in df.columns:
        raise ValueError("La columna 'fecha' no existe")
    fechas = pd.to_datetime(df["fecha"])
    tabla = pd.crosstab(fechas.dt.dayofweek, fechas.dt.hour)
    tabla = tabla.reindex(index=range(7), columns=range(24), fill_value=0)
    tabla.index = DIAS
    return tabla


def patron_horario(df: pd.DataFrame, ventana: int = 4) -> dict:
    """Resume la distribución por hora: franja de `ventana` horas con más delitos y hora mínima.

    La medianoche se excluye de la búsqueda de la franja pico porque concentra registros sin hora exacta
    (se guardan como 00:00); su peso se informa aparte.
    """
    por_hora = pd.to_datetime(df["fecha"]).dt.hour.value_counts().reindex(range(24), fill_value=0)
    sin_medianoche = por_hora.copy()
    sin_medianoche[0] = 0
    sumas = {h: int(sum(sin_medianoche[h + k] for k in range(ventana))) for h in range(1, 25 - ventana)}
    inicio = max(sumas, key=sumas.get)
    total = int(por_hora.sum())
    por_dia = pd.to_datetime(df["fecha"]).dt.dayofweek.value_counts().reindex(range(7), fill_value=0)
    return {
        "franja_pico_inicio": int(inicio),
        "franja_pico_fin": int(inicio + ventana),
        "franja_pico_pct": round(sumas[inicio] / total * 100, 1),
        "hora_pico_sin_medianoche": int(sin_medianoche.idxmax()),
        "hora_minima": int(por_hora.idxmin()),
        "pct_medianoche": round(float(por_hora[0] / total * 100), 1),
        "dia_maximo": DIAS[int(por_dia.idxmax())],
        "dia_minimo": DIAS[int(por_dia.idxmin())],
        "dif_dia_max_min_pct": round(float((por_dia.max() / por_dia.min() - 1) * 100), 1) if por_dia.min() else None,
        "por_hora": {int(h): int(v) for h, v in por_hora.items()},
    }


def serie_mensual(df: pd.DataFrame, filtro: pd.Series | None = None) -> pd.Series:
    """Conteo mensual (inicio de mes) de los registros seleccionados, con ceros en meses vacíos."""
    sub = df if filtro is None else df[filtro]
    serie = sub.groupby(pd.to_datetime(sub["fecha"]).dt.to_period("M")).size()
    serie.index = serie.index.to_timestamp()
    return serie.asfreq("MS", fill_value=0).astype(float)


def descomposicion_stl(df: pd.DataFrame, tipo: str = "THEFT", hasta: str | None = None) -> dict:
    """Descomposición STL (periodo 12, robusta) de la serie mensual de un tipo de delito.

    `hasta` recorta la serie al último mes completo para no tomar un mes parcial como caída.
    Devuelve la serie y sus componentes; tendencia + estacional + residuo = serie.
    """
    serie = serie_mensual(df, df["tipo_primario"] == tipo)
    if hasta is not None:
        serie = serie[serie.index <= pd.Timestamp(hasta)]
    resultado = STL(serie, period=12, robust=True).fit()
    return {
        "serie": serie,
        "tendencia": resultado.trend,
        "estacional": resultado.seasonal,
        "residuo": resultado.resid,
    }


def resumen_estacionalidad(stl_dict: dict) -> dict:
    """Mes con el componente estacional más alto y más bajo (promedio de todos los años)."""
    est = stl_dict["estacional"]
    por_mes = est.groupby(est.index.month).mean()
    nombres = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
               "septiembre", "octubre", "noviembre", "diciembre"]
    return {
        "mes_alto": nombres[int(por_mes.idxmax()) - 1],
        "mes_bajo": nombres[int(por_mes.idxmin()) - 1],
        "amplitud_pct_media": round(float((por_mes.max() - por_mes.min()) / stl_dict["serie"].mean() * 100), 1),
    }


# ── Serie temporal interrumpida (COVID-19) ─────────────────────────────────

def _diseno_its(fechas: pd.DatetimeIndex, origen: pd.Timestamp) -> np.ndarray:
    """Matriz de diseño: constante, tendencia lineal en meses y 11 indicadores de mes."""
    t = ((fechas.year - origen.year) * 12 + (fechas.month - origen.month)).to_numpy(dtype=float)
    meses = np.zeros((len(fechas), 11))
    for i, m in enumerate(fechas.month):
        if m > 1:
            meses[i, m - 2] = 1.0
    return np.column_stack([np.ones(len(fechas)), t, meses])


def serie_interrumpida(
    serie: pd.Series,
    inicio_pre: str = "2015-01-01",
    intervencion: str = "2020-03-01",
    fin_eval: str = "2021-12-01",
    nivel: float = 0.95,
    n_sim: int = 5000,
    semilla: int = 42,
) -> dict:
    """Serie temporal interrumpida con contrafactual ajustado solo con datos previos a la intervención.

    Modelo OLS sobre el logaritmo de la media diaria de cada mes, ajustado entre `inicio_pre` y el
    mes anterior a `intervencion`: log(y/días) = a + b·t + estacionalidad mensual + e.
    El contrafactual se proyecta a los meses de evaluación. Los intervalos salen de simular
    coeficientes (incertidumbre del modelo) y ruido residual (variación mes a mes), así que son
    intervalos de predicción, no solo de la media.
    """
    serie = serie.asfreq("MS")
    inicio_pre, intervencion, fin_eval = map(pd.Timestamp, (inicio_pre, intervencion, fin_eval))
    pre = serie[(serie.index >= inicio_pre) & (serie.index < intervencion)]
    post = serie[(serie.index >= intervencion) & (serie.index <= fin_eval)]
    if len(pre) < 24 or post.empty:
        raise ValueError("Se necesitan al menos 24 meses previos y un mes posterior a la intervención")

    dias_pre = pre.index.days_in_month.to_numpy(dtype=float)
    dias_post = post.index.days_in_month.to_numpy(dtype=float)
    X_pre = _diseno_its(pre.index, inicio_pre)
    X_post = _diseno_its(post.index, inicio_pre)
    y_pre = np.log(pre.to_numpy() / dias_pre)

    beta, *_ = np.linalg.lstsq(X_pre, y_pre, rcond=None)
    resid = y_pre - X_pre @ beta
    sigma2 = float(resid @ resid / (len(y_pre) - X_pre.shape[1]))
    cov = sigma2 * np.linalg.inv(X_pre.T @ X_pre)

    rng = np.random.default_rng(semilla)
    betas = rng.multivariate_normal(beta, cov, size=n_sim)
    ruido = rng.normal(0.0, np.sqrt(sigma2), size=(n_sim, len(post)))
    sim = np.exp(betas @ X_post.T + ruido) * dias_post  # n_sim × meses

    a = (1 - nivel) / 2
    observado = post.to_numpy()
    contrafactual = np.exp(X_post @ beta) * dias_post
    tabla = pd.DataFrame({
        "mes": post.index,
        "observado": observado,
        "contrafactual": contrafactual.round(1),
        "pi_inf": np.quantile(sim, a, axis=0).round(1),
        "pi_sup": np.quantile(sim, 1 - a, axis=0).round(1),
        "desviacion_pct": ((observado / contrafactual - 1) * 100).round(1),
    })
    tabla["fuera_intervalo"] = (observado < tabla["pi_inf"]) | (observado > tabla["pi_sup"])

    total_sim = sim.sum(axis=1)
    cambio_sim = (observado.sum() / total_sim - 1) * 100
    ajuste_pre = np.exp(X_pre @ beta) * dias_pre
    return {
        "tabla": tabla,
        "resumen": {
            "inicio_pre": str(inicio_pre.date()),
            "fin_pre": str(pre.index.max().date()),
            "intervencion": str(intervencion.date()),
            "fin_evaluacion": str(fin_eval.date()),
            "meses_pre": int(len(pre)),
            "nivel_intervalo": nivel,
            "tendencia_pre_pct_anual": round(float((np.exp(beta[1] * 12) - 1) * 100), 1),
            "mape_ajuste_pre_pct": round(float(np.mean(np.abs(pre.to_numpy() / ajuste_pre - 1)) * 100), 1),
            "observado_total": int(observado.sum()),
            "contrafactual_total": int(round(float(contrafactual.sum()))),
            "diferencia_total": int(round(float(observado.sum() - contrafactual.sum()))),
            "diferencia_inf": int(round(float(np.quantile(observado.sum() - total_sim, a)))),
            "diferencia_sup": int(round(float(np.quantile(observado.sum() - total_sim, 1 - a)))),
            "cambio_pct": round(float((observado.sum() / contrafactual.sum() - 1) * 100), 1),
            "cambio_inf_pct": round(float(np.quantile(cambio_sim, a)), 1),
            "cambio_sup_pct": round(float(np.quantile(cambio_sim, 1 - a)), 1),
            "meses_fuera_intervalo": int(tabla["fuera_intervalo"].sum()),
            "meses_evaluados": int(len(tabla)),
        },
    }


def efecto_covid_por_serie(
    series: dict[str, pd.Series],
    meses_choque: tuple[str, str] = ("2020-04-01", "2020-05-01"),
    **kwargs,
) -> pd.DataFrame:
    """Aplica la serie interrumpida a varias series y resume el choque (abril–mayo 2020) y el acumulado."""
    filas = []
    for nombre, serie in series.items():
        res = serie_interrumpida(serie, **kwargs)
        tabla = res["tabla"].set_index("mes")
        choque = tabla.loc[pd.Timestamp(meses_choque[0]):pd.Timestamp(meses_choque[1])]
        cf = choque["contrafactual"].sum()
        filas.append({
            "serie": nombre,
            "choque_abr_may_2020_pct": round(float((choque["observado"].sum() / cf - 1) * 100), 1),
            **{k: res["resumen"][k] for k in (
                "cambio_pct", "cambio_inf_pct", "cambio_sup_pct",
                "meses_fuera_intervalo", "meses_evaluados", "mape_ajuste_pre_pct",
            )},
        })
    return pd.DataFrame(filas)


def cambio_porcentual_por_tipo(df: pd.DataFrame, anio_ini: int = 2019, anio_fin: int = 2024) -> pd.DataFrame:
    """Cambio porcentual de delitos por tipo entre dos años (usar con tipos ya armonizados).

    Si un tipo no existe en el año inicial, el cambio queda vacío en vez de dividir por cero.
    """
    anios = set(pd.Series(df["anio"]).dropna().astype(int))
    if anio_ini not in anios or anio_fin not in anios:
        raise ValueError(f"Faltan datos de {anio_ini} o {anio_fin}")
    sub = df[df["anio"].isin([anio_ini, anio_fin])]
    grupo = pd.crosstab(sub["tipo_primario"].astype(str), sub["anio"].astype(int))
    grupo = grupo.reindex(columns=[anio_ini, anio_fin], fill_value=0)
    grupo.columns = [f"conteo_{anio_ini}", f"conteo_{anio_fin}"]
    cambio = grupo.reset_index().rename(columns={"index": "tipo_primario"})
    ini = cambio[f"conteo_{anio_ini}"]
    cambio["cambio_pct"] = ((cambio[f"conteo_{anio_fin}"] - ini) / ini.where(ini > 0) * 100).round(1)
    return cambio.sort_values("cambio_pct", ascending=False).reset_index(drop=True)


# ── Figuras ─────────────────────────────────────────────────────────────────

def graficar_tendencia_anual(
    anual: pd.Series, anio_parcial: int | None, etiqueta_parcial: str = "", ruta: Path | None = None
) -> Path:
    """Delitos por año; el año parcial se dibuja aparte y rotulado para no leerlo como caída."""
    ruta = ruta or FIGURAS / "01_tendencia_anual.png"
    fig, ax = plt.subplots(figsize=(12, 5))
    colores = ["#BDBDBD" if a == anio_parcial else "#1565C0" for a in anual.index]
    ax.bar(anual.index.astype(int), anual.values, color=colores)
    if anio_parcial in anual.index:
        ax.annotate(f"{anio_parcial}: año parcial\n{etiqueta_parcial}", (anio_parcial, anual[anio_parcial]),
                    xytext=(0, 8), textcoords="offset points", ha="center", fontsize=8)
    ax.set_xlabel("Año")
    ax.set_ylabel("Delitos registrados")
    ax.set_title("Delitos registrados por año — Chicago")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1000:,.0f} mil"))
    ax.set_xticks(anual.index.astype(int))
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
    return ruta


def graficar_mapa_calor_hora_dia(tabla: pd.DataFrame, ruta: Path | None = None) -> Path:
    """Mapa de calor hora × día de la semana."""
    ruta = ruta or FIGURAS / "02_mapa_calor_hora_dia.png"
    fig, ax = plt.subplots(figsize=(14, 5))
    sns.heatmap(tabla, cmap="YlOrRd", linewidths=0.3, ax=ax, cbar_kws={"label": "Delitos"})
    ax.set_xlabel("Hora del día (00:00 incluye registros sin hora exacta)")
    ax.set_ylabel("")
    ax.set_title("Delitos por hora y día de la semana")
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
    return ruta


def graficar_stl(stl_dict: dict, tipo: str, ruta: Path | None = None) -> Path:
    """Descomposición STL en 4 paneles."""
    ruta = ruta or FIGURAS / "03_descomposicion_stl.png"
    nombres = {"serie": "Serie", "tendencia": "Tendencia", "estacional": "Estacional", "residuo": "Residuo"}
    fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True)
    for ax, (nombre, datos) in zip(axes, stl_dict.items()):
        ax.plot(datos, color="#1565C0", linewidth=0.8)
        ax.set_ylabel(nombres.get(nombre, nombre))
    axes[0].set_title(f"Descomposición STL — {tipo} mensual")
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
    return ruta


def graficar_efecto_covid(serie: pd.Series, resultado: dict, ruta: Path | None = None) -> Path:
    """Serie observada frente al contrafactual pre-2020 con su intervalo de predicción."""
    ruta = ruta or FIGURAS / "04_efecto_covid.png"
    r = resultado["resumen"]
    tabla = resultado["tabla"]
    ventana = serie[(serie.index >= pd.Timestamp(r["inicio_pre"])) & (serie.index <= pd.Timestamp(r["fin_evaluacion"]))]
    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(ventana.index, ventana.values, color="#212121", linewidth=1.4, label="Observado")
    ax.plot(tabla["mes"], tabla["contrafactual"], color="#1565C0", linestyle="--", label="Contrafactual (ajustado antes de 2020-03)")
    ax.fill_between(tabla["mes"], tabla["pi_inf"], tabla["pi_sup"], color="#1565C0", alpha=0.18,
                    label=f"Intervalo de predicción {int(r['nivel_intervalo'] * 100)} %")
    ax.axvline(pd.Timestamp(r["intervencion"]), color="#C62828", linewidth=1)
    ax.set_ylabel("Delitos por mes")
    ax.set_title(
        f"Serie interrumpida: {r['cambio_pct']:+.1f} % frente al contrafactual entre "
        f"{r['intervencion'][:7]} y {r['fin_evaluacion'][:7]} (IC 95 %: {r['cambio_inf_pct']:+.1f} a {r['cambio_sup_pct']:+.1f} %)"
    )
    ax.legend(loc="lower left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
    return ruta


def graficar_top_tipos(conteo: pd.Series, titulo: str, ruta: Path | None = None) -> Path:
    """Barras horizontales de los tipos de delito más frecuentes."""
    ruta = ruta or FIGURAS / "05_top_tipos.png"
    fig, ax = plt.subplots(figsize=(10, 6))
    conteo.plot.barh(ax=ax, color="#EF6C00")
    ax.set_xlabel("Número de delitos")
    ax.set_title(titulo)
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v / 1e6:.1f} M"))
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
    return ruta
