"""
Gráficos estáticos (PNG) para el README y los notebooks.

Reglas de estilo (las mismas del proyecto de importaciones): paleta categórica validada para
daltonismo, el color sigue a la entidad (Ecuador siempre azul, la región siempre naranja, cada
categoría de desacople siempre el mismo color), líneas de 2 px, grilla discreta, un solo eje Y,
leyenda cuando hay 2 o más series y etiquetas directas selectivas.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mtick  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from . import config, kaya  # noqa: E402

ECU, REG = config.COLOR_ECUADOR, config.COLOR_REGION


def num(v: float, dec: int = 1) -> str:
    """Formato español: miles con punto, decimales con coma."""
    return f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def estilo() -> None:
    plt.rcParams.update({
        "figure.facecolor": config.SUPERFICIE, "axes.facecolor": config.SUPERFICIE,
        "savefig.facecolor": config.SUPERFICIE, "figure.dpi": 110, "savefig.dpi": 150,
        "font.family": "DejaVu Sans", "font.size": 10,
        "text.color": config.TEXTO, "axes.labelcolor": config.TEXTO_SECUNDARIO,
        "xtick.color": config.TEXTO_SECUNDARIO, "ytick.color": config.TEXTO_SECUNDARIO,
        "axes.edgecolor": "#d8d7d2", "axes.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": "#e8e7e3", "grid.linewidth": 0.7,
        "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.titlepad": 30, "axes.axisbelow": True, "lines.linewidth": 2, "legend.frameon": False,
    })


def _titulo(ax, titulo: str, subtitulo: str | None = None) -> None:
    ax.set_title(titulo, color=config.TEXTO)
    if subtitulo:
        ax.annotate(subtitulo, xy=(0, 1), xycoords="axes fraction", xytext=(0, 8),
                    textcoords="offset points", fontsize=9.5, color=config.TEXTO_SECUNDARIO, va="bottom")


def _guardar(fig, nombre: str | None, carpeta: Path = config.FIGURAS):
    fig.tight_layout()
    if nombre:
        carpeta.mkdir(parents=True, exist_ok=True)
        fig.savefig(carpeta / nombre, bbox_inches="tight")
    return fig


def _fuente(fig, texto: str = "Fuente: Banco Mundial (WDI) y Our World in Data / Global Carbon Project.") -> None:
    fig.text(0.01, -0.01, texto, fontsize=8, color=config.GRIS, ha="left", va="top")


def _usd_k(ax, eje: str = "x") -> None:
    f = mtick.FuncFormatter(lambda v, _: f"{num(v / 1000, 0)} mil")
    (ax.xaxis if eje == "x" else ax.yaxis).set_major_formatter(f)
    (ax.xaxis if eje == "x" else ax.yaxis).set_minor_formatter(mtick.NullFormatter())


# ---------------------------------------------------------------------------
# 01 · Cobertura de datos
# ---------------------------------------------------------------------------
def cobertura(cob: pd.DataFrame, variables: list[str], nombre="01_cobertura.png"):
    estilo()
    t = (cob[cob["variable"].isin(variables)]
         .pivot(index="variable", columns="iso3", values="pct_completo").reindex(variables))
    fig, ax = plt.subplots(figsize=(11, 0.42 * len(variables) + 1.8))
    cmap = LinearSegmentedColormap.from_list("azul", ["#f3f2ef", "#cfe0f6", "#2a78d6", "#0d3f80"])
    ax.imshow(t.to_numpy(dtype=float), aspect="auto", cmap=cmap, vmin=0, vmax=100)
    ax.set_xticks(range(t.shape[1]), t.columns, rotation=0, fontsize=8.5)
    ax.set_yticks(range(t.shape[0]), t.index, fontsize=9)
    ax.grid(False)
    for (i, j), v in np.ndenumerate(t.to_numpy(dtype=float)):
        if v < 100:
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7.5,
                    color="white" if v > 60 else config.TEXTO)
    for s in ax.spines.values():
        s.set_visible(False)
    _titulo(ax, "Cobertura de datos por variable y país, 1990–2024",
            "% de años con dato; las celdas sin número están 100 % completas. No se imputa ningún valor.")
    _fuente(fig)
    return _guardar(fig, nombre)


# ---------------------------------------------------------------------------
# 02 · Emisiones per cápita vs ingreso
# ---------------------------------------------------------------------------
def emisiones_vs_ingreso(panel: pd.DataFrame, anio: int, nombre="02_co2_vs_ingreso.png"):
    estilo()
    d = panel[(panel["anio"] == anio)].dropna(subset=["pib_pc_ppa", "co2_pc_t"])
    fig, ax = plt.subplots(figsize=(10, 6))
    otros = d[~d["iso3"].isin(["ECU", config.REGION])]
    ax.scatter(otros["pib_pc_ppa"], otros["co2_pc_t"], s=60, color=config.GRIS, edgecolor=config.SUPERFICIE,
               linewidth=2, zorder=3)
    for iso, color in [("ECU", ECU), (config.REGION, REG)]:
        f = d[d["iso3"] == iso]
        ax.scatter(f["pib_pc_ppa"], f["co2_pc_t"], s=110, color=color, edgecolor=config.SUPERFICIE,
                   linewidth=2, zorder=4, marker="D" if iso == config.REGION else "o")
    for _, f in d.iterrows():
        destacado = f["iso3"] in ("ECU", config.REGION)
        ax.annotate(f["pais"], (f["pib_pc_ppa"], f["co2_pc_t"]), xytext=(6, 4), textcoords="offset points",
                    fontsize=9 if destacado else 8, fontweight="bold" if destacado else "normal",
                    color=config.TEXTO if destacado else config.TEXTO_SECUNDARIO)
    ax.set_xscale("log")
    _usd_k(ax)
    ax.set_xticks([3000, 5000, 10000, 20000, 30000])
    ax.set_xlabel("PIB per cápita (USD PPA constantes de 2021, escala log)")
    ax.set_ylabel("t de CO2 por persona")
    _titulo(ax, f"Más ingreso, más emisiones… pero con mucha dispersión ({anio})",
            "CO2 fósil e industrial por persona vs PIB per cápita. Cuba y Venezuela no tienen PIB en el Banco Mundial.")
    _fuente(fig)
    return _guardar(fig, nombre)


# ---------------------------------------------------------------------------
# 03 · Índices de la región
# ---------------------------------------------------------------------------
SERIES_INDICE = {
    "pib_ppa": ("PIB real", config.COLORES[0]),
    "poblacion_bm": ("Población", config.GRIS),
    "co2_mt": ("CO2", config.COLORES[1]),
    "intensidad_co2_kg_usd": ("CO2 por USD de PIB", config.COLORES[2]),
}


def indices(ind: pd.DataFrame, titulo: str, subtitulo: str, nombre: str | None, ax=None):
    estilo()
    propio = ax is None
    if propio:
        fig, ax = plt.subplots(figsize=(10, 5.5))
    for col, (etiqueta, color) in SERIES_INDICE.items():
        if col not in ind:
            continue
        s = ind[col].dropna()
        ax.plot(s.index, s.values, color=color, label=etiqueta,
                linestyle="--" if col == "poblacion_bm" else "-")
        ax.annotate(f"{etiqueta}  {num(s.iloc[-1], 0)}", (s.index[-1], s.iloc[-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=9, color=config.TEXTO)
    ax.axhline(100, color=config.GRIS, linewidth=0.8)
    ax.set_xlim(right=ind.index.max() + 9)
    ax.set_ylabel("Índice (año base = 100)")
    ax.legend(loc="upper left", ncols=4, bbox_to_anchor=(0, 1.0))
    _titulo(ax, titulo, subtitulo)
    if propio:
        _fuente(fig)
        return _guardar(fig, nombre)
    return ax


# ---------------------------------------------------------------------------
# 04 · Dispersión de desacople
# ---------------------------------------------------------------------------
# etiquetas que chocan en la dispersión 2000–2024: (dx, dy, alineación)
DESPLAZAMIENTOS = {"ECU": (-8, 4, "right"), "GTM": (7, -6, "left"), config.REGION: (6, -13, "left"),
                   "NIC": (6, -12, "left"), "BRA": (-8, 0, "right"), "ARG": (-8, -2, "right")}


def desacople_dispersion(tabla: pd.DataFrame, periodo: tuple[int, int], nombre="04_desacople_paises.png"):
    estilo()
    d = tabla[tabla["categoria"] != "Sin datos"]
    fig, ax = plt.subplots(figsize=(10, 6.5))
    lim = max(d["crec_pib_anual"].max(), d["crec_co2_anual"].max()) + 0.6
    bajo = min(d["crec_co2_anual"].min(), 0) - 0.6
    ax.fill_between([0, lim], [0, lim], [bajo, bajo], color=config.COLORES[0], alpha=0.05, linewidth=0)
    ax.fill_between([0, lim], [0, 0], [bajo, bajo], color=config.COLORES[2], alpha=0.07, linewidth=0)
    ax.plot([0, lim], [0, lim], color=config.GRIS, linewidth=1, linestyle="--")
    ax.axhline(0, color=config.GRIS, linewidth=0.8)
    ax.text(lim - 0.1, lim - 0.15, "diagonal: el CO2 crece igual que el PIB", ha="right", va="top",
            fontsize=8.5, color=config.GRIS)
    ax.text(lim - 0.1, bajo + 0.15, "desacople absoluto: el CO2 baja", ha="right", fontsize=8.5,
            color=config.TEXTO_SECUNDARIO)
    for cat in config.CATEGORIAS_DESACOPLE:
        g = d[d["categoria"] == cat]
        if g.empty:
            continue
        ax.scatter(g["crec_pib_anual"], g["crec_co2_anual"], s=[150 if i == config.REGION else 70 for i in g["iso3"]],
                   marker="o", color=config.COLOR_DESACOPLE[cat], edgecolor=config.SUPERFICIE, linewidth=2,
                   label=f"{cat} ({(g['iso3'] != config.REGION).sum()})", zorder=3)
    for _, f in d.iterrows():
        destacado = f["iso3"] in ("ECU", config.REGION)
        dx, dy, ha = DESPLAZAMIENTOS.get(f["iso3"], (6, -3, "left"))
        ax.annotate(f["pais"], (f["crec_pib_anual"], f["crec_co2_anual"]), xytext=(dx, dy), textcoords="offset points",
                    ha=ha, fontsize=9 if destacado else 8, fontweight="bold" if destacado else "normal",
                    color=config.TEXTO if destacado else config.TEXTO_SECUNDARIO)
    ax.set_xlim(min(0, d["crec_pib_anual"].min() - 0.4), lim)   # deja ver los países en recesión
    ax.set_ylim(bajo, lim)
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.set_xlabel("Crecimiento anual del PIB real")
    ax.set_ylabel("Crecimiento anual del CO2")
    ax.legend(loc="upper left")
    n_abs = int(((d["categoria"] == "Absoluto") & (d["iso3"] != config.REGION)).sum())
    titulo = (f"Nadie desacopló en términos absolutos entre {periodo[0]} y {periodo[1]}" if n_abs == 0 else
              f"{n_abs} {'país' if n_abs == 1 else 'países'} con desacople absoluto entre {periodo[0]} y {periodo[1]}")
    _titulo(ax, titulo,
            "Tasas anuales entre promedios trienales (inicio y fin). Bajo la diagonal: el CO2 crece menos que el PIB.")
    _fuente(fig)
    return _guardar(fig, nombre)


# ---------------------------------------------------------------------------
# 05 · Elasticidad por subperiodo
# ---------------------------------------------------------------------------
def elasticidad_subperiodos(t1: pd.DataFrame, t2: pd.DataFrame, etiquetas: tuple[str, str],
                            nombre="05_desacople_subperiodos.png"):
    # un país en recesión tiene elasticidad sin sentido (dividir por un crecimiento ~0): se excluye
    excluir = set(t1.loc[t1["categoria"] == "Recesión", "pais"]) | set(t2.loc[t2["categoria"] == "Recesión", "pais"])
    estilo()
    d = (t1.set_index("pais")["elasticidad"].rename("e1").to_frame()
         .join(t2.set_index("pais")["elasticidad"].rename("e2")).dropna().sort_values("e2"))
    d = d.clip(-3, 3)
    d = d[~d.index.isin(excluir)]
    fig, ax = plt.subplots(figsize=(10, 7))
    y = np.arange(len(d))
    ax.hlines(y, d["e1"], d["e2"], color=config.GRIS_CLARO, linewidth=2)
    ax.scatter(d["e1"], y, color=config.COLORES[6], s=60, zorder=3, label=etiquetas[0],
               edgecolor=config.SUPERFICIE, linewidth=2)
    ax.scatter(d["e2"], y, color=config.COLORES[0], s=60, zorder=3, label=etiquetas[1],
               edgecolor=config.SUPERFICIE, linewidth=2)
    ax.axvline(0, color=config.GRIS, linewidth=0.8)
    ax.axvspan(0.8, 1.2, color=config.COLORES[1], alpha=0.08, linewidth=0)
    ax.text(1.0, -0.9, "acoplado (0,8–1,2)", ha="center", va="center", fontsize=8, color=config.TEXTO_SECUNDARIO)
    ax.set_ylim(-1.4, len(d) - 0.5)
    ax.set_yticks(y, d.index, fontsize=9)
    for lbl in ax.get_yticklabels():
        if lbl.get_text() in ("Ecuador", config.NOMBRE_REGION):
            lbl.set_fontweight("bold")
    nota = f" · excluido por recesión: {', '.join(sorted(excluir))}" if excluir else ""
    ax.set_xlabel(f"Elasticidad de Tapio = % cambio CO2 / % cambio PIB  (recortada a ±3){nota}")
    ax.legend(loc="upper left")
    _titulo(ax, "Tras el fin del auge de materias primas, la región se separó más… y otros se acoplaron",
            "Elasticidad < 0: desacople absoluto · 0 a 0,8: relativo · > 1,2: el CO2 crece más rápido que el PIB.")
    _fuente(fig)
    return _guardar(fig, nombre)


# ---------------------------------------------------------------------------
# 06 · Desacople móvil
# ---------------------------------------------------------------------------
def desacople_movil(movil: pd.DataFrame, ventana: int, nombre="06_desacople_movil.png"):
    estilo()
    cats = [c for c in config.CATEGORIAS_DESACOPLE if c != "Sin datos"]
    t = (movil[movil["categoria"].isin(cats)].groupby(["fin", "categoria"], observed=True).size()
         .unstack(fill_value=0).reindex(columns=cats, fill_value=0))
    fig, ax = plt.subplots(figsize=(10, 5.5))
    base = np.zeros(len(t))
    for c in cats:
        ax.bar(t.index, t[c], bottom=base, color=config.COLOR_DESACOPLE[c], label=c, width=0.8,
               edgecolor=config.SUPERFICIE, linewidth=1)
        base += t[c].to_numpy()
    ax.set_ylabel("Número de países (de 18 con PIB)")
    ax.set_xlabel(f"Último año de la ventana de {ventana} años")
    ax.legend(loc="upper left", ncols=4, bbox_to_anchor=(0, 1.0))
    ax.set_ylim(0, 21)
    ax.yaxis.set_major_locator(mtick.MultipleLocator(3))
    maximo = t["Absoluto"].max()
    _titulo(ax, f"Clasificación en ventanas móviles de {ventana} años",
            f"El desacople absoluto nunca pasa de {maximo} de 18 países en una misma ventana "
            f"(máximo en {t['Absoluto'].idxmax() - ventana}–{t['Absoluto'].idxmax()}).")
    _fuente(fig)
    return _guardar(fig, nombre)


# ---------------------------------------------------------------------------
# 07 · Ecuador frente a la región
# ---------------------------------------------------------------------------
PANELES_ECUADOR = [
    ("co2_pc_t", "CO2 por persona (t)", 1),
    ("intensidad_co2_kg_usd", "CO2 por USD de PIB (kg)", 3),
    ("energia_pc_mwh", "Energía primaria por persona (MWh)", 1),
    ("carbono_energia_kg_kwh", "CO2 por kWh de energía primaria (kg)", 3),
]


def ecuador_vs_region(panel: pd.DataFrame, nombre="07_ecuador_vs_region.png"):
    estilo()
    fig, ejes = plt.subplots(2, 2, figsize=(12, 8))
    for ax, (col, etiqueta, dec) in zip(ejes.flat, PANELES_ECUADOR):
        for iso, g in panel[~panel["iso3"].isin(["ECU", config.REGION])].groupby("iso3"):
            ax.plot(g["anio"], g[col], color=config.GRIS_CLARO, linewidth=0.9)
        for iso, color, etq in [(config.REGION, REG, "América Latina"), ("ECU", ECU, "Ecuador")]:
            g = panel[panel["iso3"] == iso].dropna(subset=[col])
            ax.plot(g["anio"], g[col], color=color, label=etq, linewidth=2.4)
            ax.annotate(num(g[col].iloc[-1], dec), (g["anio"].iloc[-1], g[col].iloc[-1]), xytext=(5, 0),
                        textcoords="offset points", va="center", fontsize=8.5, color=config.TEXTO)
        ax.set_title(etiqueta, fontsize=11, pad=8)
        alto = panel.loc[panel["iso3"].isin(["ECU", config.REGION]), col].max()
        ax.set_ylim(0, alto * 1.9)
        ax.set_xlim(1990, 2027)
    ejes[0, 0].legend(loc="upper left")
    fig.suptitle("Ecuador emite como la región por persona, pero con más CO2 por dólar producido",
                 x=0.01, ha="left", fontsize=13, fontweight="bold")
    fig.text(0.01, 0.935, "En gris, los otros 19 países (recortados para no aplanar la escala). 1990–2024.",
             fontsize=9.5, color=config.TEXTO_SECUNDARIO)
    _fuente(fig)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    if nombre:
        config.FIGURAS.mkdir(parents=True, exist_ok=True)
        fig.savefig(config.FIGURAS / nombre, bbox_inches="tight")
    return fig


# ---------------------------------------------------------------------------
# 08 · Kaya
# ---------------------------------------------------------------------------
def kaya_comparacion(tablas: dict[str, pd.DataFrame], periodo: tuple[int, int], nombre="08_kaya_lmdi.png"):
    estilo()
    factores = list(kaya.FACTORES.values()) + ["Cambio total"]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    alto = 0.38
    y = np.arange(len(factores))
    for i, (etq, t) in enumerate(tablas.items()):
        v = t.set_index("factor").reindex(factores)["pct_co2_inicial"]
        color = ECU if etq == "Ecuador" else REG
        barras = ax.barh(y + (i - 0.5) * alto, v, height=alto - 0.04, color=color, label=etq)
        for b, val in zip(barras, v):
            ax.annotate(f"{'+' if val > 0 else ''}{num(val, 0)} %", (val, b.get_y() + b.get_height() / 2),
                        xytext=(4 if val >= 0 else -4, 0), textcoords="offset points", va="center",
                        ha="left" if val >= 0 else "right", fontsize=8.5, color=config.TEXTO)
    ax.axvline(0, color=config.GRIS, linewidth=0.8)
    ax.set_yticks(y, factores)
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(mtick.PercentFormatter(decimals=0))
    ax.set_xlabel("Aporte al cambio del CO2, % del nivel inicial")
    ax.legend(loc="upper right")
    lo, hi = ax.get_xlim()
    ax.set_xlim(lo - 8, hi + 12)
    _titulo(ax, f"¿Por qué subió el CO2? Descomposición de Kaya, {periodo[0]}–{periodo[1]}",
            "LMDI aditivo sobre promedios trienales; los cuatro efectos suman exactamente el cambio total.")
    _fuente(fig)
    return _guardar(fig, nombre)


# ---------------------------------------------------------------------------
# 09 · Fuentes del CO2 de Ecuador
# ---------------------------------------------------------------------------
FUENTES_CO2 = {
    "co2_petroleo_mt": "Petróleo", "co2_gas_mt": "Gas", "co2_quema_mt": "Quema de gas (antorchas)",
    "co2_cemento_mt": "Cemento", "co2_carbon_mt": "Carbón",
}


def fuentes_co2(panel: pd.DataFrame, iso3: str = "ECU", nombre="09_ecuador_fuentes_co2.png"):
    estilo()
    g = panel[panel["iso3"] == iso3].set_index("anio")[list(FUENTES_CO2)].fillna(0)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    colores = [config.COLORES[0], config.COLORES[2], config.COLORES[1], config.COLORES[6], config.GRIS]
    ax.stackplot(g.index, g.T.values, labels=FUENTES_CO2.values(), colors=colores,
                 edgecolor=config.SUPERFICIE, linewidth=0.8)
    ult = g.iloc[-1]
    ax.annotate(f"{num(ult.sum(), 1)} Mt en {g.index[-1]}\n{num(100 * ult['co2_petroleo_mt'] / ult.sum(), 0)} % petróleo",
                (g.index[-1], ult.sum()), xytext=(-10, 12), textcoords="offset points", ha="right", fontsize=9)
    ax.set_ylabel("Mt de CO2")
    ax.legend(loc="upper left", ncols=3)
    ax.set_ylim(0, g.sum(axis=1).max() * 1.3)
    pais = config.PAISES.get(iso3, iso3)
    _titulo(ax, f"{pais}: el CO2 es casi todo petróleo",
            "Emisiones territoriales por combustible. 2020: pandemia; 2016–2019: entra la hidroelectricidad. El hueco de 1994 viene así en la fuente.")
    _fuente(fig)
    return _guardar(fig, nombre)


# ---------------------------------------------------------------------------
# 10–11 · Curva de Kuznets
# ---------------------------------------------------------------------------
def kuznets(d: pd.DataFrame, curvas: dict[str, pd.DataFrame], nombre="10_kuznets.png"):
    estilo()
    fig, ax = plt.subplots(figsize=(10, 6))
    for iso, g in d.groupby("iso3"):
        es_ecu = iso == "ECU"
        ax.plot(g["pib_pc_ppa"], g["co2_pc_t"], color=ECU if es_ecu else config.GRIS_CLARO,
                linewidth=2.2 if es_ecu else 0.9, zorder=3 if es_ecu else 1, label="Ecuador (trayectoria)" if es_ecu else None)
        if es_ecu or iso in ("PAN", "URY", "CRI", "CHL", "MEX", "HTI"):
            ax.annotate(g["pais"].iloc[0], (g["pib_pc_ppa"].iloc[-1], g["co2_pc_t"].iloc[-1]), xytext=(4, 0),
                        textcoords="offset points", fontsize=8, va="center",
                        color=config.TEXTO if es_ecu else config.TEXTO_SECUNDARIO)
    colores = [config.COLORES[1], config.COLORES[6]]
    for (etq, c), color in zip(curvas.items(), colores):
        ax.plot(c["pib_pc_ppa"], c["co2_pc_t"], color=color, linewidth=2.4, label=etq, zorder=4)
    ax.set_xscale("log")
    ax.set_yscale("log")
    _usd_k(ax)
    ax.set_xticks([2000, 5000, 10000, 20000, 40000])
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: num(v, 1 if v < 1 else 0)))
    ax.set_xlabel("PIB per cápita (USD PPA de 2021, escala log)")
    ax.set_ylabel("t de CO2 por persona (escala log)")
    ax.legend(loc="lower right")
    _titulo(ax, "La curva de Kuznets no se dobla dentro de América Latina",
            "Trayectoria de 18 países (1990–2024) y parábolas ajustadas en logaritmos. Ningún punto de giro cae en la muestra.")
    _fuente(fig)
    return _guardar(fig, nombre)


def pendientes(pend: pd.DataFrame, nombre="11_kuznets_pendientes.png"):
    estilo()
    d = pend.sort_values("elasticidad")
    fig, ax = plt.subplots(figsize=(10, 6.5))
    y = np.arange(len(d))
    colores = [ECU if i == "ECU" else config.GRIS for i in d["iso3"]]
    ax.hlines(y, d["ic_bajo"].clip(-1, 2.5), d["ic_alto"].clip(-1, 2.5), color=colores, linewidth=2, alpha=0.6)
    ax.scatter(d["elasticidad"], y, color=colores, s=55, zorder=3, edgecolor=config.SUPERFICIE, linewidth=2)
    ax.axvline(0, color=config.GRIS, linewidth=0.8)
    ax.axvline(1, color=config.GRIS, linewidth=0.8, linestyle="--")
    ax.set_yticks(y, d["pais"])
    for lbl in ax.get_yticklabels():
        if lbl.get_text() == "Ecuador":
            lbl.set_fontweight("bold")
    ax.set_xlim(-1, 2.5)
    ax.set_xlabel("Elasticidad ingreso–emisiones (IC 95 %, errores HAC; recortado a −1…2,5)")
    _titulo(ax, "Cada país tiene su propia relación ingreso–emisiones",
            "Pendiente de ln(CO2 pc) sobre ln(PIB pc) por país, 1990–2024. Una sola curva regional las promedia.")
    _fuente(fig)
    return _guardar(fig, nombre)
