"""Figuras del proyecto (reports/figures/*.png), dibujadas solo a partir de reports/.

Paleta categórica validada (orden fijo, nunca cíclica), texto en tinta neutra y rejilla recesiva.
Las curvas de supervivencia se muestran como «% de solicitudes aún abiertas» en eje de tiempo
logarítmico (de minutos a un año), con su banda de confianza al 95 %.
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

from nyc311.config import ARCHIVO_RESULTADOS, DIR_FIGURAS, DIR_TABLAS
from nyc311.etiquetas import BOROUGHS_ES, tipo_es

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
GRIS = "#8f8d87"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
REJILLA_COLOR = "#e6e5e0"
FONDO = "#fcfcfb"

TICKS_T = [1 / 1440, 1 / 24, 1, 7, 30, 365]
ETIQ_T = ["1 min", "1 h", "1 día", "7 días", "30 días", "1 año"]

plt.rcParams.update(
    {
        "figure.facecolor": FONDO,
        "axes.facecolor": FONDO,
        "savefig.facecolor": FONDO,
        "axes.edgecolor": REJILLA_COLOR,
        "axes.labelcolor": TINTA_2,
        "axes.titlecolor": TINTA,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.grid": True,
        "grid.color": REJILLA_COLOR,
        "grid.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": TINTA_2,
        "ytick.color": TINTA_2,
        "font.size": 10,
        "legend.frameon": False,
        "lines.linewidth": 2,
        "figure.dpi": 110,
        "figure.constrained_layout.use": True,
    }
)


def _res() -> dict:
    return json.loads(ARCHIVO_RESULTADOS.read_text(encoding="utf-8"))


def _curvas() -> pd.DataFrame:
    return pd.read_parquet(DIR_TABLAS / "curvas_km.parquet")


def n_es(x: float, dec: int = 0) -> str:
    texto = f"{x:,.{dec}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def eje_tiempo(ax: plt.Axes, xmin: float = 1 / 1440, xmax: float = 400) -> None:
    ax.set_xscale("log")
    ax.set_xlim(xmin, xmax)
    ax.xaxis.set_major_locator(FixedLocator(TICKS_T))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: ETIQ_T[TICKS_T.index(v)] if v in TICKS_T else ""))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_ylim(0, 101)
    ax.set_ylabel("% de solicitudes aún abiertas")


def dibujar_curva(ax: plt.Axes, c: pd.DataFrame, color: str, etiqueta: str, banda: bool = True, **kw) -> None:
    t = c["tiempo"].clip(lower=1 / 1440)
    ax.step(t, 100 * c["supervivencia"], where="post", color=color, label=etiqueta, **kw)
    if banda:
        ax.fill_between(t, 100 * c["ic_inferior"], 100 * c["ic_superior"], step="post", color=color, alpha=0.18, lw=0)


def _guardar(fig: plt.Figure, nombre: str, fuente: str = "Fuente: NYC Open Data, 311 Service Requests (oct-2024 a sep-2026). Cálculo propio.") -> None:
    fig.get_layout_engine().set(rect=(0, 0.035, 1, 0.965))
    fig.text(0.01, 0.005, fuente, fontsize=8, color=TINTA_2)
    fig.savefig(DIR_FIGURAS / nombre, dpi=130, bbox_inches="tight")
    plt.close(fig)


def fig01_calidad_y_censura() -> None:
    res = _res()
    cal = res["calidad"]
    mensual = pd.read_csv(DIR_TABLAS / "evolucion_mensual.csv")
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={"width_ratios": [1, 1.25]})
    items = [
        ("Estado «Closed» sin fecha de cierre (descartadas)", cal["cerradas_sin_fecha_cierre"]),
        ("Cierre antes de la apertura (descartadas)", cal["cierre_antes_de_apertura"]),
        ("Fecha de cierre pero estado abierto (censura)", cal["fecha_cierre_con_estado_abierto"]),
        ("Cierre posterior al corte (censura)", cal["cierre_posterior_al_corte"]),
        ("Cierre instantáneo, duración 0 (se conservan)", cal["cierres_instantaneos"]),
        ("ZIP nulo o fuera de NYC (se conservan)", cal["zip_invalido_o_nulo"]),
        ("Borough sin dato (se conservan)", cal["borough_sin_dato"]),
        ("unique_key duplicado", cal["duplicados_unique_key"]),
    ]
    etiquetas, valores = zip(*items)
    y = np.arange(len(items))[::-1]
    a.barh(y, valores, color=SERIES[0], height=0.6)
    a.set_xscale("symlog", linthresh=10)
    a.set_yticks(y, etiquetas)
    for yi, v in zip(y, valores):
        a.text(max(v, 1) * 1.15, yi, n_es(v), va="center", fontsize=9, color=TINTA)
    a.set_xlim(0, max(valores) * 8)
    a.set_xlabel("solicitudes (escala logarítmica)")
    a.set_title(f"Calidad: {n_es(cal['filas_crudas'])} → {n_es(cal['filas_limpias'])} filas")
    a.grid(axis="y", visible=False)

    x = np.arange(len(mensual))
    cerradas = mensual["n"] * (1 - mensual["pct_censuradas"] / 100)
    abiertas = mensual["n"] * mensual["pct_censuradas"] / 100
    b.bar(x, cerradas / 1e3, color=SERIES[0], width=0.8, label="Cerradas al corte (evento)")
    b.bar(x, abiertas / 1e3, bottom=cerradas / 1e3, color=SERIES[1], width=0.8, label="Abiertas al corte (censuradas)")
    for xi, (tot, pct) in enumerate(zip(mensual["n"], mensual["pct_censuradas"])):
        if xi % 3 == 2 or xi == len(mensual) - 1:
            b.text(xi, tot / 1e3 + 4, f"{n_es(pct, 1)} %", ha="center", fontsize=8, color=TINTA_2)
    b.set_xticks(x[::3], mensual["mes"].iloc[::3], rotation=0, fontsize=8)
    b.set_ylabel("miles de solicitudes creadas")
    b.set_title(f"Censura por mes (corte {res['fuente']['fecha_corte'][:10]})")
    b.set_ylim(0, 430)
    b.legend(loc="upper left", ncols=2)
    b.grid(axis="x", visible=False)
    _guardar(fig, "01_calidad_y_censura.png")


def fig02_sesgo_promedio_vs_km() -> None:
    res = _res()
    exp = pd.DataFrame(res["sesgo"]["tabla"])
    curvas = _curvas()
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 5), gridspec_kw={"width_ratios": [1.1, 1]})
    sel = exp.loc[exp["grupo"].isin(["Todas", "NYPD", "HPD", "DSNY", "DOHMH", "DOB", "DPR", "TLC"])].copy()
    sel = sel.sort_values("mediana_verdad")
    y = np.arange(len(sel))
    a.scatter(sel["mediana_ingenua_ficticio"], y, s=60, color=SERIES[1], label="Mediana ingenua (solo cerradas)", zorder=3)
    a.scatter(sel["mediana_km_ficticio"], y, s=60, color=SERIES[0], label="Mediana Kaplan-Meier", zorder=4)
    a.scatter(sel["mediana_verdad"], y, s=150, facecolors="none", edgecolors=TINTA, lw=1.5, label="Verdad (≈ 2 años después)", zorder=5)
    for yi, (_, r) in zip(y, sel.iterrows()):
        a.plot([r["mediana_ingenua_ficticio"], r["mediana_km_ficticio"]], [yi, yi], color=GRIS, lw=1, zorder=2)
    etiquetas = [f"{'Todas' if g == 'Todas' else g} ({n_es(p, 0)} % abiertas)"
                 for g, p in zip(sel["grupo"], sel["pct_abiertas_corte_ficticio"])]
    a.set_yticks(y, etiquetas)
    eje_tiempo(a, 1 / 24, 400)
    a.set_ylim(-0.6, len(sel) - 0.4)
    a.set_ylabel("")
    a.set_xlabel("mediana del tiempo de resolución")
    a.set_title(f"Corte ficticio {res['sesgo']['corte_ficticio']}: cohorte oct–dic 2024")
    a.legend(loc="upper left", fontsize=8.5)
    a.grid(axis="y", visible=False)

    estilos = {
        "Verdad (seguimiento completo)": (TINTA, "-"),
        "Kaplan-Meier al corte ficticio": (SERIES[0], "--"),
        "Ingenuo: solo cerradas al corte ficticio": (SERIES[1], "-"),
    }
    sub = curvas.loc[curvas["dimension"].eq("sesgo_DPR")]
    for nombre, (color, ls) in estilos.items():
        c = sub.loc[sub["grupo"].eq(nombre)]
        if nombre.startswith("Kaplan"):
            c = c.loc[c["tiempo"] <= 106]  # más allá no hay seguimiento al corte ficticio
        dibujar_curva(b, c, color, nombre, banda=False, ls=ls)
    eje_tiempo(b, 1 / 24, 400)
    b.axhline(50, color=GRIS, lw=0.8, ls=":")
    fila = exp.loc[exp["grupo"].eq("DPR")].iloc[0]
    b.set_title(
        f"Parques (DPR): mediana ingenua {n_es(fila['mediana_ingenua_ficticio'], 1)} d · "
        f"KM {n_es(fila['mediana_km_ficticio'], 1)} d · verdad {n_es(fila['mediana_verdad'], 1)} d",
        fontsize=10.5,
    )
    b.legend(loc="lower left", fontsize=8.5)
    _guardar(fig, "02_sesgo_promedio_vs_kaplan_meier.png")


def fig03_km_agencias() -> None:
    curvas = _curvas()
    km = pd.read_csv(DIR_TABLAS / "km_agencias.csv")
    sub = curvas.loc[curvas["dimension"].eq("agencia")]
    orden = sub.groupby("grupo")["n"].first().sort_values(ascending=False).index
    orden = [g for g in orden if g != "Otras"][:8]
    fig, ax = plt.subplots(figsize=(11, 5.6))
    for i, ag in enumerate(orden):
        med = km.loc[km["agencia"].eq(ag), "mediana_km_dias"].iat[0]
        txt = f"{n_es(med * 24, 1)} h" if med < 1 else f"{n_es(med, 1)} d"
        dibujar_curva(ax, sub.loc[sub["grupo"].eq(ag)], SERIES[i], f"{ag} · mediana {txt}")
    eje_tiempo(ax)
    ax.axhline(50, color=GRIS, lw=0.8, ls=":")
    ax.set_title("Kaplan-Meier por agencia: NYPD cierra en horas; Parques y Edificios, en semanas\n"
                 "El escalón inicial son cierres instantáneos (duración 0); la caída vertical de DOHMH, un cierre por plazo (60 días)")
    ax.legend(loc="upper right", fontsize=9)
    _guardar(fig, "03_kaplan_meier_agencias.png")


def fig04_km_borough_canal() -> None:
    curvas = _curvas()
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
    sub = curvas.loc[curvas["dimension"].eq("borough") & curvas["grupo"].ne("SIN DATO")]
    km_b = pd.read_csv(DIR_TABLAS / "km_boroughs.csv")
    for i, bo in enumerate(["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"]):
        med = km_b.loc[km_b["borough"].eq(bo), "mediana_km_dias"].iat[0]
        dibujar_curva(a, sub.loc[sub["grupo"].eq(bo)], SERIES[i], f"{BOROUGHS_ES[bo]} · {n_es(med * 24, 1)} h")
    eje_tiempo(a)
    a.axhline(50, color=GRIS, lw=0.8, ls=":")
    a.set_title("Por borough (sin ajustar por tipo de queja)")
    a.legend(loc="upper right", fontsize=9, title="mediana", title_fontsize=9)
    sub = curvas.loc[curvas["dimension"].eq("canal")]
    km_c = pd.read_csv(DIR_TABLAS / "km_canales.csv")
    for i, ca in enumerate(["Teléfono", "Web", "App móvil", "Otro/desconocido"]):
        med = km_c.loc[km_c["canal"].eq(ca), "mediana_km_dias"].iat[0]
        dibujar_curva(b, sub.loc[sub["grupo"].eq(ca)], SERIES[i], f"{ca} · {n_es(med * 24, 1)} h")
    eje_tiempo(b)
    b.set_ylabel("")
    b.axhline(50, color=GRIS, lw=0.8, ls=":")
    b.set_title("Por canal de entrada")
    b.legend(loc="upper right", fontsize=9, title="mediana", title_fontsize=9)
    _guardar(fig, "04_kaplan_meier_borough_y_canal.png")


def fig05_medianas_tipos() -> None:
    km = pd.read_csv(DIR_TABLAS / "km_tipos_queja.csv").head(20).copy()
    km = km.sort_values("mediana_km_dias")
    km["etiqueta"] = km["tipo_queja"].map(tipo_es)
    fig, ax = plt.subplots(figsize=(10.5, 7.2))
    y = np.arange(len(km))
    sup = km["mediana_ic_sup"].replace(np.inf, 400)
    ax.hlines(y, km["mediana_ic_inf"].clip(lower=1 / 1440), sup, color=SERIES[0], lw=3, alpha=0.35)
    ax.scatter(km["mediana_km_dias"].clip(lower=1 / 1440), y, s=36, color=SERIES[0], zorder=3, label="Mediana KM (IC 95 %)")
    ax.scatter(km["promedio_ingenuo_cerradas_dias"], y, s=36, marker="D", facecolors="none", edgecolors=SERIES[1],
               zorder=3, label="Promedio ingenuo de las cerradas")
    ax.set_yticks(y, [f"{e}  (n={n_es(n / 1e3, 0)} mil)" for e, n in zip(km["etiqueta"], km["n"])], fontsize=9)
    eje_tiempo(ax, 1 / 60, 400)
    ax.set_ylim(-0.6, len(km) - 0.4)
    ax.set_ylabel("")
    ax.set_xlabel("tiempo de resolución")
    ax.set_title("20 tipos de queja más frecuentes: mediana KM frente al promedio")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(axis="y", visible=False)
    _guardar(fig, "05_medianas_por_tipo_de_queja.png")


def _forest(ax: plt.Axes, hr: pd.DataFrame, titulo: str) -> None:
    hr = hr.iloc[::-1].reset_index(drop=True)
    y = np.arange(len(hr))
    colores = [SERIES[0] if v >= 1 else SERIES[1] for v in hr["hr"]]
    ax.hlines(y, hr["ic_inf"], hr["ic_sup"], color=colores, lw=3, alpha=0.5)
    ax.scatter(hr["hr"], y, color=colores, s=36, zorder=3)
    ax.axvline(1, color=TINTA_2, lw=1)
    ax.set_xscale("log")
    lo, hi = hr["ic_inf"].min() * 0.92, hr["ic_sup"].max() * 1.08
    ax.set_xlim(min(lo, 0.95), max(hi, 1.05))
    ancho = ax.get_xlim()[1] / ax.get_xlim()[0]
    candidatos = [0.1, 0.2, 0.3, 0.5, 1, 1.5, 2] if ancho > 3 else [0.7, 0.8, 0.9, 1, 1.1, 1.2, 1.3]
    ax.xaxis.set_major_locator(FixedLocator([v for v in candidatos if ax.get_xlim()[0] <= v <= ax.get_xlim()[1]]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: n_es(v, 2).rstrip("0").rstrip(",")))
    ax.xaxis.set_minor_locator(NullLocator())
    etiquetas = (
        hr["covariable"]
        .str.replace("agencia=", "Agencia: ")
        .str.replace("borough=", "Borough: ")
        .str.replace("canal=", "Canal: ")
        .replace({"fin_de_semana": "Creada en fin de semana", "nocturna": "Creada de 22 h a 6 h"})
    )
    for k, v in BOROUGHS_ES.items():
        etiquetas = etiquetas.str.replace(k, v)
    ax.set_yticks(y, etiquetas, fontsize=9)
    ax.set_ylim(-0.6, len(hr) - 0.4)
    ax.set_title(titulo, fontsize=10.5)
    ax.set_xlabel("hazard ratio de cierre (> 1 = más rápido; < 1 = más lento)")
    ax.grid(axis="y", visible=False)


def fig06_cox() -> None:
    a_ = pd.read_csv(DIR_TABLAS / "cox_modelo_A.csv")
    b_ = pd.read_csv(DIR_TABLAS / "cox_modelo_B.csv")
    res = _res()["cox"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 5.6), gridspec_kw={"width_ratios": [1.15, 1]})
    _forest(a, a_, f"Modelo A: agencia + borough + canal + horario (C = {n_es(res['modelo_A']['concordancia'], 3)})\n"
                   "Referencias: NYPD, Manhattan, teléfono")
    _forest(b, b_, f"Modelo B: estratificado por tipo de queja (C = {n_es(res['modelo_B']['concordancia'], 3)})\n"
                   "Compara boroughs dentro del mismo tipo de queja")
    _guardar(fig, "06_cox_hazard_ratios.png", f"Cox en muestra aleatoria de {n_es(res['n_muestra'])} solicitudes. "
             "Fuente: NYC Open Data 311. Cálculo propio.")


def fig07_supuesto_ph() -> None:
    curvas = _curvas()
    ven = pd.read_csv(DIR_TABLAS / "cox_hr_por_ventana.csv")
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 4.8))
    sub = curvas.loc[curvas["dimension"].eq("borough") & curvas["grupo"].ne("SIN DATO")]
    for i, bo in enumerate(["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"]):
        c = sub.loc[sub["grupo"].eq(bo) & sub["supervivencia"].between(1e-4, 0.9999) & sub["tiempo"].gt(0)]
        a.plot(c["tiempo"], np.log(-np.log(c["supervivencia"])), color=SERIES[i], label=BOROUGHS_ES[bo])
    a.set_xscale("log")
    a.xaxis.set_major_locator(FixedLocator(TICKS_T))
    a.xaxis.set_major_formatter(FuncFormatter(lambda v, _: ETIQ_T[TICKS_T.index(v)] if v in TICKS_T else ""))
    a.xaxis.set_minor_locator(NullLocator())
    a.set_xlim(1 / 1440, 400)
    a.set_ylabel("log(−log S(t))")
    a.set_title("Diagnóstico gráfico: con PH las curvas serían paralelas")
    a.legend(fontsize=9)
    vb = ven.loc[ven["covariable"].str.startswith("borough=")].copy()
    orden_v = list(dict.fromkeys(ven["ventana"]))
    x = np.arange(len(orden_v))
    for i, bo in enumerate(["BRONX", "BROOKLYN", "QUEENS", "STATEN ISLAND"]):
        s = vb.loc[vb["covariable"].eq(f"borough={bo}")].set_index("ventana").reindex(orden_v)
        color = SERIES[[0, 1, 3, 4][i]]
        b.errorbar(x + (i - 1.5) * 0.08, s["hr"], yerr=[s["hr"] - s["ic_inf"], s["ic_sup"] - s["hr"]], color=color,
                   marker="o", ms=6, capsize=0, lw=2, label=BOROUGHS_ES[bo])
    b.axhline(1, color=TINTA_2, lw=1)
    b.set_xticks(x, [f"{v}\n(en riesgo: {n_es(n)})" for v, n in zip(orden_v, ven.groupby("ventana", sort=False)["n_en_riesgo"].first())], fontsize=8.5)
    b.set_yscale("log")
    b.yaxis.set_major_locator(FixedLocator([0.5, 0.75, 1, 1.5, 2]))
    b.yaxis.set_major_formatter(FuncFormatter(lambda v, _: n_es(v, 2).rstrip("0").rstrip(",")))
    b.yaxis.set_minor_locator(NullLocator())
    b.set_ylabel("HR de cierre frente a Manhattan")
    b.set_title("HR del modelo B por ventana de tiempo: el efecto se invierte")
    b.legend(fontsize=9, ncols=2)
    _guardar(fig, "07_supuesto_riesgos_proporcionales.png")


def fig08_equidad() -> None:
    eq_z = pd.read_csv(DIR_TABLAS / "equidad_zip.csv", dtype={"zip": "string"})
    res = _res()["equidad"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 5), gridspec_kw={"width_ratios": [1, 1.3]})
    eq_h = pd.read_csv(DIR_TABLAS / "equidad_boroughs_horizontes.csv")
    etiquetas_h = list(dict.fromkeys(eq_h["horizonte"]))
    x = np.arange(len(etiquetas_h))
    for i, bo in enumerate(["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"]):
        s_ = eq_h.loc[eq_h["borough"].eq(bo)].set_index("horizonte").reindex(etiquetas_h)
        a.plot(x, s_["o_entre_e"], color=SERIES[i], marker="o", ms=6, label=BOROUGHS_ES[bo])
    a.axhline(1, color=TINTA_2, lw=1)
    a.set_xticks(x, [f"≤ {e}" for e in etiquetas_h])
    a.set_xlim(-0.3, len(x) - 0.7)
    a.set_xlabel("horizonte: cerradas dentro de…")
    a.set_ylabel("O/E (observado / esperado por su mezcla)")
    a.set_title("Borough, ajustado por tipo × descriptor:\nla brecha del Bronx está en las primeras horas", fontsize=10.5)
    a.legend(loc="lower right", fontsize=8.5)
    a.grid(axis="x", visible=False)

    orden = ["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"]
    for i, bo in enumerate(orden):
        s = eq_z.loc[eq_z["borough"].eq(bo)]
        b.scatter(s["n"], s["o_entre_e"], s=22, color=SERIES[i], label=BOROUGHS_ES[bo], alpha=0.85,
                  edgecolors=FONDO, linewidths=0.6)
    n = np.geomspace(eq_z["n"].min(), eq_z["n"].max(), 200)
    p = 0.8
    lim = 1.96 * np.sqrt(p * (1 - p) / n) / p
    b.plot(n, 1 + lim, color=GRIS, lw=1, ls="--")
    b.plot(n, 1 - lim, color=GRIS, lw=1, ls="--", label="Límite 95 % por azar")
    b.axhline(1, color=TINTA_2, lw=1)
    for _, r in eq_z.head(3).iterrows():
        b.annotate(r["zip"], (r["n"], r["o_entre_e"]), xytext=(6, -2), textcoords="offset points", fontsize=8.5)
    b.set_xscale("log")
    b.set_xlabel("solicitudes en el código postal (escala log)")
    b.set_ylabel("O/E de cierre en ≤ 7 días")
    b.set_title(f"Embudo por ZIP (≤ 7 días): {res['n_zip_lentos']} más lentos y\n{res['n_zip_rapidos']} más rápidos de lo esperado (FDR 5 %)",
                fontsize=10.5)
    b.legend(fontsize=8, ncols=3, loc="lower right")
    _guardar(fig, "08_equidad_territorial.png")


def fig09_evolucion() -> None:
    m = pd.read_csv(DIR_TABLAS / "evolucion_mensual.csv")
    fig, (a, b) = plt.subplots(1, 2, figsize=(13, 4.6))
    x = np.arange(len(m))
    a.fill_between(x, 24 * m["mediana_ic_inf"], 24 * m["mediana_ic_sup"], color=SERIES[0], alpha=0.2, lw=0)
    a.plot(x, 24 * m["mediana_km_dias"], color=SERIES[0], marker="o", ms=4)
    a.set_xticks(x[::3], m["mes"].iloc[::3], fontsize=8)
    a.set_ylabel("horas")
    a.set_ylim(0, None)
    a.set_title("Mediana KM por mes de creación: pico cada invierno")
    a.grid(axis="x", visible=False)
    b.plot(x, m["o_entre_e"], color=SERIES[0], marker="o", ms=4, label="O/E ajustado por tipo × descriptor")
    b.fill_between(x, m["ic_inf"], m["ic_sup"], color=SERIES[0], alpha=0.2, lw=0)
    b.axhline(1, color=TINTA_2, lw=1)
    b.axvline(11.5, color=GRIS, lw=1, ls=":")
    b.text(11.7, 0.95, "oct-2025 →", fontsize=8.5, color=TINTA_2, transform=b.get_xaxis_transform())
    b.set_xticks(x[::3], m["mes"].iloc[::3], fontsize=8)
    b.set_ylabel("O/E de cierre en ≤ 7 días")
    b.set_title("Rapidez ajustada por la mezcla de quejas (> 1 = mejor)")
    b.legend(fontsize=9, loc="lower left")
    b.grid(axis="x", visible=False)
    _guardar(fig, "09_evolucion_mensual.png")


def generar_todas() -> None:
    DIR_FIGURAS.mkdir(parents=True, exist_ok=True)
    for f in [fig01_calidad_y_censura, fig02_sesgo_promedio_vs_km, fig03_km_agencias, fig04_km_borough_canal,
              fig05_medianas_tipos, fig06_cox, fig07_supuesto_ph, fig08_equidad, fig09_evolucion]:
        f()


if __name__ == "__main__":
    generar_todas()
