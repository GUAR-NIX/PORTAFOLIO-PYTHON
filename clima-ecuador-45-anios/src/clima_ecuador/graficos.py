"""Figuras del proyecto (matplotlib, estilo consistente). ``todas`` las genera en reports/figures."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

from . import config  # noqa: E402
from .extremos import NOMBRES  # noqa: E402

MESES = ["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
DIVERGENTE = LinearSegmentedColormap.from_list("frio_calido", ["#1d5fae", "#8fb6e8", "#f0efec", "#f0a08f", "#b8322a"])
DIVERGENTE_LLUVIA = LinearSegmentedColormap.from_list("seco_humedo", ["#a8611d", "#e3b77a", "#f0efec", "#8fb6e8", "#1d5fae"])


def estilo() -> None:
    plt.rcParams.update({
        "figure.facecolor": config.SUPERFICIE, "axes.facecolor": config.SUPERFICIE, "savefig.facecolor": config.SUPERFICIE,
        "axes.edgecolor": config.GRIS_CLARO, "axes.labelcolor": config.TEXTO_SECUNDARIO, "axes.titlesize": 11,
        "axes.titleweight": "bold", "axes.titlecolor": config.TEXTO, "axes.titlelocation": "left",
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#e8e7e3",
        "grid.linewidth": 0.6, "xtick.color": config.TEXTO_SECUNDARIO, "ytick.color": config.TEXTO_SECUNDARIO,
        "font.size": 9, "legend.frameon": False, "lines.linewidth": 2, "figure.dpi": 110, "savefig.dpi": 140,
        "savefig.bbox": "tight",
    })


def guardar(fig, nombre: str, carpeta: Path = config.FIGURAS) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / nombre
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def nota(fig, texto: str) -> None:
    fig.text(0.01, -0.02, texto, fontsize=7.5, color=config.TEXTO_SECUNDARIO, ha="left", va="top")


# ---------------------------------------------------------------------------
# Mapa base
# ---------------------------------------------------------------------------
def leer_provincias(ruta: Path = config.GEOJSON_PROVINCIAS) -> list[np.ndarray]:
    """Anillos exteriores de las provincias (lista de arreglos lon/lat)."""
    if not ruta.exists():
        return []
    g = json.loads(ruta.read_text(encoding="utf-8"))
    anillos = []
    for f in g["features"]:
        geom = f["geometry"]
        poligonos = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for pol in poligonos:
            anillos.append(np.asarray(pol[0]))
    return anillos


def mapa_base(ax, anillos, extension) -> None:
    for a in anillos:
        ax.add_patch(Polygon(a, closed=True, facecolor="#f1f0ec", edgecolor="#b9b8b3", linewidth=0.5, zorder=0))
    ax.set_xlim(extension[0], extension[1])
    ax.set_ylim(extension[2], extension[3])
    ax.set_aspect("equal")
    ax.grid(False)
    ax.tick_params(labelsize=7)
    for lado in ["top", "right"]:
        ax.spines[lado].set_visible(True)


EXT_CONTINENTE = (-81.3, -75.1, -5.1, 1.6)
# Etiquetas que se pisan con su vecina: (dx, dy en puntos, alineación)
DESPLAZAMIENTO_ETIQUETA = {"Santo Domingo": (-6, -10, "right"), "Quito": (6, 4, "left"),
                           "Portoviejo": (6, -10, "left"), "Puerto Baquerizo": (-4, -12, "right"),
                           "Zamora": (6, -8, "left"), "Loja": (-6, 3, "right")}
EXT_GALAPAGOS = (-91.8, -89.1, -1.5, 0.7)


def mapa_puntos(valores: pd.Series | None, titulo: str, etiqueta: str, nombre: str, cmap=DIVERGENTE,
                significativo: pd.Series | None = None, simetrico: bool = True, formato: str = "{:+.2f}",
                anillos=None) -> Path:
    """Mapa de las ciudades coloreadas por ``valores`` (índice = ciudad). Sin valores: por región."""
    anillos = leer_provincias() if anillos is None else anillos
    fig = plt.figure(figsize=(8.6, 6.4))
    ax = fig.add_axes([0.05, 0.08, 0.68, 0.84])
    ax_g = fig.add_axes([0.74, 0.62, 0.24, 0.28])
    mapa_base(ax, anillos, EXT_CONTINENTE)
    mapa_base(ax_g, anillos, EXT_GALAPAGOS)
    ax_g.set_title("Galápagos", fontsize=8, loc="left")
    lat = {c: v[0] for c, v in config.CIUDADES.items()}
    lon = {c: v[1] for c, v in config.CIUDADES.items()}
    if valores is not None:
        v = valores.dropna()
        limite = float(np.nanmax(np.abs(v))) if simetrico else None
        norma = TwoSlopeNorm(0, -limite, limite) if simetrico and limite > 0 else None
    for c in config.CIUDADES:
        destino = ax_g if config.CIUDADES[c][3] == "Galápagos" else ax
        if valores is None:
            color = config.COLOR_REGION[config.CIUDADES[c][3]]
            destino.scatter(lon[c], lat[c], s=60, color=color, edgecolor="white", linewidth=1.2, zorder=3)
        else:
            if c not in v.index:
                continue
            sig = True if significativo is None else bool(significativo.get(c, False))
            sc = destino.scatter(lon[c], lat[c], s=140, c=[v[c]], cmap=cmap, norm=norma, zorder=3,
                                 edgecolor=config.TEXTO if sig else config.GRIS, linewidth=1.6 if sig else 0.8,
                                 marker="o" if sig else "D")
        texto = c if valores is None else f"{c}\n{formato.format(v[c])}"
        dx, dy, ha = DESPLAZAMIENTO_ETIQUETA.get(c, (6, 3, "left"))
        destino.annotate(texto, (lon[c], lat[c]), xytext=(dx, dy), textcoords="offset points", fontsize=7,
                         color=config.TEXTO, zorder=4, linespacing=0.95, ha=ha)
    ax.set_title(titulo)
    if valores is None:
        manejadores = [Line2D([], [], marker="o", ls="", color=col, markersize=8, label=r)
                       for r, col in config.COLOR_REGION.items()]
        est = [(v[2], v[1]) for v in config.ESTACIONES.values()]
        ax.scatter([e[0] for e in est if e[0] > -85], [e[1] for e in est if e[0] > -85], marker="^", s=40,
                   facecolor="none", edgecolor=config.TEXTO_SECUNDARIO, zorder=2)
        ax_g.scatter([e[0] for e in est if e[0] < -85], [e[1] for e in est if e[0] < -85], marker="^", s=40,
                     facecolor="none", edgecolor=config.TEXTO_SECUNDARIO, zorder=2)
        manejadores.append(Line2D([], [], marker="^", ls="", markerfacecolor="none",
                                  markeredgecolor=config.TEXTO_SECUNDARIO, label="Estación GHCN (validación)"))
        fig.legend(handles=manejadores, loc="lower right", bbox_to_anchor=(0.98, 0.12), fontsize=8)
    else:
        cax = fig.add_axes([0.77, 0.2, 0.18, 0.025])
        cb = fig.colorbar(sc, cax=cax, orientation="horizontal")
        cb.set_label(etiqueta, fontsize=8)
        cb.ax.tick_params(labelsize=7)
        if significativo is not None:
            fig.legend(handles=[Line2D([], [], marker="o", ls="", markerfacecolor="white", markeredgecolor=config.TEXTO,
                                       markersize=8, label="Significativa (Hamed-Rao, p < 0,05)"),
                                Line2D([], [], marker="D", ls="", markerfacecolor="white", markeredgecolor=config.GRIS,
                                       markersize=7, label="No significativa")],
                       loc="lower right", bbox_to_anchor=(0.98, 0.3), fontsize=7.5)
    return guardar(fig, nombre)


# ---------------------------------------------------------------------------
# Figuras del análisis
# ---------------------------------------------------------------------------
def fig_calidad(s: dict) -> Path:
    api = s["controles"]["api"]
    ciclo = s["ciclo"]
    fig, ejes = plt.subplots(1, 2, figsize=(10, 3.6), gridspec_kw={"width_ratios": [1.1, 1]})
    ax = ejes[0]
    nombres = {"tmed_celda": "Tmed", "tmax_celda": "Tmáx", "tmin_celda": "Tmín", "precip": "Lluvia", "humedad": "Humedad",
               "viento_max": "Viento máx", "radiacion": "Radiación"}
    y = np.arange(len(api))
    ax.barh(y, api["correlacion"], color=config.COLORES[0], height=0.55, zorder=2)
    ax.grid(False)
    for i, f in api.reset_index(drop=True).iterrows():
        ax.text(0.902, i, f"r = {f['correlacion']:.4f} · |dif| media {f['dif_abs_media']:.3f}",
                va="center", ha="left", fontsize=7.5, color="white", fontweight="bold", zorder=3)
    ax.set_yticks(y, [nombres.get(v, v) for v in api["variable"]])
    ax.set_xlim(0.9, 1.0)
    ax.invert_yaxis()
    ax.set_title("Agregación propia vs API diaria de Open-Meteo")
    ax.set_xlabel("Correlación diaria (2015 y 2023, 22 ciudades)")
    ax = ejes[1]
    for region, d in ciclo.groupby("region"):
        ax.plot(d["hora"], d["radiacion"], color=config.COLOR_REGION[region], label=region)
    ax.set_xticks(range(0, 24, 3))
    ax.set_xlabel("Hora local")
    ax.set_ylabel("W/m²")
    ax.set_title("Control de hora local: radiación solar media")
    ax.legend(fontsize=7.5)
    nota(fig, "Si la conversión UTC → hora local fallara, el pico de radiación se movería del mediodía solar.")
    return guardar(fig, "02_calidad.png")


def fig_climatologia(a: dict) -> Path:
    c = a["clim_region"]
    fig, ejes = plt.subplots(2, 4, figsize=(12, 5.2), sharex=True)
    for j, region in enumerate(config.REGIONES):
        d = c[c["region"] == region]
        ax = ejes[0, j]
        ax.bar(d["m"], d["precip"], color=config.COLOR_REGION[region], width=0.7)
        ax.set_title(f"{region} · {d['precip'].sum():,.0f} mm/año".replace(",", "."))
        if j == 0:
            ax.set_ylabel("Lluvia mensual (mm)")
        ax = ejes[1, j]
        ax.fill_between(d["m"], d["tmin"], d["tmax"], color=config.COLOR_REGION[region], alpha=0.18, linewidth=0)
        ax.plot(d["m"], d["tmax"], color=config.COLOR_REGION[region])
        ax.plot(d["m"], d["tmin"], color=config.COLOR_REGION[region], ls="--")
        ax.set_xticks(range(1, 13), MESES)
        if j == 0:
            ax.set_ylabel("Tmáx (—) y Tmín (--) °C")
    fig.suptitle("Clima normal 1981–2010 por región (media de las ciudades de cada región)", x=0.01, ha="left",
                 fontweight="bold")
    fig.tight_layout()
    return guardar(fig, "03_climatologia_regiones.png")


def fig_ciclo_diurno(s: dict) -> Path:
    c = s["ciclo"]
    fig, ejes = plt.subplots(1, 2, figsize=(10, 3.6))
    for region, d in c.groupby("region"):
        col = config.COLOR_REGION[region]
        ejes[0].plot(d["hora"], d["precip"], color=col, label=region)
        ejes[1].plot(d["hora"], d["temp"] - d["temp"].mean(), color=col, label=region)
    ejes[0].set_title("¿A qué hora llueve? Lluvia media por hora")
    ejes[0].set_ylabel("mm/h")
    ejes[1].set_title("Ciclo diario de temperatura (respecto a su media)")
    ejes[1].set_ylabel("°C")
    for ax in ejes:
        ax.set_xticks(range(0, 24, 3))
        ax.set_xlabel("Hora local")
    ejes[0].legend(fontsize=7.5)
    nota(fig, "ERA5 horario 1991–2020. La lluvia de cada hora es la acumulada en la hora que termina.")
    return guardar(fig, "04_ciclo_diurno.png")


def fig_franjas(a: dict) -> Path:
    """Franjas de calentamiento: anomalía de la temperatura media anual de cada ciudad."""
    an = a["anom_a"].copy()
    orden = [c for r in config.REGIONES for c, v in config.CIUDADES.items() if v[3] == r]
    tabla = an.pivot(index="punto", columns="anio", values="tmed").reindex(orden)
    fig, ax = plt.subplots(figsize=(11, 5.6))
    lim = np.nanmax(np.abs(tabla.to_numpy()))
    im = ax.imshow(tabla.to_numpy(), aspect="auto", cmap=DIVERGENTE, norm=TwoSlopeNorm(0, -lim, lim),
                   interpolation="nearest")
    ax.set_yticks(range(len(orden)), orden, fontsize=7.5)
    anios = tabla.columns.to_numpy()
    ax.set_xticks(range(0, len(anios), 5), anios[::5])
    ax.grid(False)
    for i, c in enumerate(orden):
        ax.text(-0.7, i, "", ha="right")
    bordes = np.cumsum([sum(v[3] == r for v in config.CIUDADES.values()) for r in config.REGIONES])[:-1]
    for b in bordes:
        ax.axhline(b - 0.5, color="white", linewidth=2)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    cb.set_label("Anomalía de temperatura media (°C, vs 1981–2010)")
    ax.set_title("Franjas de calentamiento: 22 ciudades, 1980–2024 (de arriba abajo: Costa, Sierra, Amazonía, Galápagos)")
    return guardar(fig, "05_franjas_calentamiento.png")


def fig_anomalias_regiones(a: dict) -> Path:
    an = a["anom_reg_a"]
    fig, ejes = plt.subplots(1, 2, figsize=(11, 3.8))
    for region, d in an.groupby("region"):
        col = config.COLOR_REGION[region]
        ejes[0].plot(d["anio"], d["tmed"], color=col, label=region, linewidth=1.6)
        ejes[1].plot(d["anio"], d["precip_pct"], color=col, label=region, linewidth=1.4)
    nac = a["anom_nac"]
    tn = a["tend_nac"].set_index("variable")
    if "tmed" in tn.index:
        f = tn.loc["tmed"]
        x = nac["anio"].to_numpy()
        ejes[0].plot(x, f["pendiente_decada"] / 10 * (x - x[0]) + np.median(nac["tmed"])
                     - f["pendiente_decada"] / 10 * (np.median(x) - x[0]), color=config.TEXTO, ls=":",
                     linewidth=1.5, label=f"Sen nacional {f['pendiente_decada']:+.2f} °C/década")
    ejes[0].axhline(0, color=config.GRIS, linewidth=0.8)
    ejes[1].axhline(0, color=config.GRIS, linewidth=0.8)
    ejes[0].set_title("Anomalía de temperatura media anual (°C)")
    ejes[1].set_title("Anomalía de lluvia anual (% de la normal)")
    ejes[0].legend(fontsize=7.5, ncol=2)
    for anio, etiqueta in [(1983, "El Niño\n82-83"), (1998, "El Niño\n97-98")]:
        ejes[1].annotate(etiqueta, (anio, an[an["anio"] == anio]["precip_pct"].max()), xytext=(4, -2),
                         textcoords="offset points", fontsize=7, color=config.TEXTO_SECUNDARIO)
    return guardar(fig, "06_anomalias_regiones.png")


def fig_tendencias_ciudades(a: dict) -> Path:
    t = a["tend_ciudad"]
    fig, ejes = plt.subplots(1, 3, figsize=(12, 6), sharey=True)
    orden = [c for r in config.REGIONES for c, v in config.CIUDADES.items() if v[3] == r][::-1]
    y = np.arange(len(orden))
    for ax, var, titulo, campo in [(ejes[0], "tmax", "Tmáx (°C/década)", "pendiente_decada"),
                                   (ejes[1], "tmin", "Tmín (°C/década)", "pendiente_decada"),
                                   (ejes[2], "precip", "Lluvia anual (%/década)", "pendiente_pct_decada")]:
        d = t[t["variable"] == var].set_index("punto").reindex(orden)
        escala = 100 / d["precip_media"] if var == "precip" else 1
        bajo = d["ic_bajo_decada"] * escala
        alto = d["ic_alto_decada"] * escala
        for i, c in enumerate(orden):
            col = config.COLOR_REGION[config.CIUDADES[c][3]]
            sig = bool(d.loc[c, "significativa"])
            ax.plot([bajo[c], alto[c]], [i, i], color=col, linewidth=1.5, alpha=0.6)
            ax.scatter(d.loc[c, campo], i, s=40, color=col if sig else "white", edgecolor=col, linewidth=1.5, zorder=3)
        ax.axvline(0, color=config.GRIS, linewidth=0.8)
        ax.set_title(titulo)
    ejes[0].set_yticks(y, orden)
    fig.legend(handles=[Line2D([], [], marker="o", ls="", color=c, label=r) for r, c in config.COLOR_REGION.items()]
               + [Line2D([], [], marker="o", ls="", markerfacecolor="white", markeredgecolor=config.TEXTO,
                         label="Hueco: no significativa (Hamed-Rao)")],
               loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.04), fontsize=8)
    fig.suptitle("Tendencia 1980–2024 por ciudad: pendiente de Sen e intervalo del 95 %", x=0.01, ha="left",
                 fontweight="bold")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return guardar(fig, "07_tendencias_ciudades.png")


def fig_correccion_autocorrelacion(a: dict) -> Path:
    t = a["tend_ciudad"]
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    for var, col, etiqueta in [("tmed", config.CALIDO, "Tmed"), ("precip", config.FRIO, "Lluvia"),
                               ("humedad", config.COLORES[2], "Humedad")]:
        d = t[t["variable"] == var]
        ax.scatter(-np.log10(d["p_original"].clip(1e-12)), -np.log10(d["p_hamed_rao"].clip(1e-12)), s=30,
                   color=col, label=etiqueta, alpha=0.85, edgecolor="white", linewidth=0.6)
    lim = ax.get_xlim()[1]
    ax.plot([0, lim], [0, lim], color=config.GRIS, linewidth=0.8, ls="--")
    ax.axhline(-np.log10(0.05), color=config.TEXTO_SECUNDARIO, linewidth=0.8)
    ax.axvline(-np.log10(0.05), color=config.TEXTO_SECUNDARIO, linewidth=0.8)
    ax.set_xlabel("−log10 p sin corregir (Mann-Kendall original)")
    ax.set_ylabel("−log10 p con corrección de Hamed-Rao")
    ax.set_title("La autocorrelación infla la significancia")
    ax.legend(fontsize=8)
    nota(fig, "Cada punto es una ciudad. Bajo la diagonal: la corrección reduce la evidencia. Líneas: p = 0,05.")
    return guardar(fig, "08_correccion_autocorrelacion.png")


def fig_extremos(a: dict) -> Path:
    ir = a["ind_region"]
    paneles = [("dias_ola_calor", "Días en olas de calor por año"), ("tx90p", "Días cálidos (% con Tmáx > p90)"),
               ("r20mm", "Días con lluvia ≥ 20 mm"), ("cdd", "Racha seca más larga (días)")]
    fig, ejes = plt.subplots(2, 2, figsize=(11, 6.4), sharex=True)
    for ax, (var, titulo) in zip(ejes.ravel(), paneles):
        for region, d in ir.groupby("region"):
            col = config.COLOR_REGION[region]
            suave = d.set_index("anio")[var].rolling(5, center=True, min_periods=3).mean()
            ax.plot(d["anio"], d[var], color=col, linewidth=0.8, alpha=0.35)
            ax.plot(suave.index, suave.to_numpy(), color=col, linewidth=2, label=region)
        ax.set_title(titulo)
    ejes[0, 0].legend(fontsize=7.5, ncol=2)
    nota(fig, "Media de las ciudades de cada región. Línea fina: valor anual; gruesa: media móvil de 5 años. "
              "Umbrales: percentiles de 1981–2010 de cada ciudad.")
    fig.tight_layout()
    return guardar(fig, "09_extremos_regiones.png")


def fig_tabla_extremos(a: dict) -> Path:
    """Mapa de calor: tendencia de cada índice en cada región, con marca de significancia."""
    t = a["tend_ext_reg"].copy()
    indices = ["tx90p", "tn90p", "dias_ola_calor", "olas_calor", "wsdi", "prcptot", "dias_lluvia", "r20mm",
               "rx1day", "rx5day", "r95ptot", "sdii", "cdd", "rachas_secas_10"]
    media = t.set_index(["region", "variable"])["media"]
    t["rel"] = 100 * t["pendiente_decada"] / t.set_index(["region", "variable"]).index.map(media).to_numpy().clip(1e-9)
    tabla = t.pivot(index="variable", columns="region", values="rel").reindex(indices)[config.REGIONES]
    sig = t.pivot(index="variable", columns="region", values="significativa").reindex(indices)[config.REGIONES]
    pend = t.pivot(index="variable", columns="region", values="pendiente_decada").reindex(indices)[config.REGIONES]
    fig, ax = plt.subplots(figsize=(8.6, 6.4))
    lim = np.nanpercentile(np.abs(tabla.to_numpy()), 95)
    im = ax.imshow(tabla.to_numpy(), cmap=DIVERGENTE, norm=TwoSlopeNorm(0, -lim, lim), aspect="auto")
    for i in range(len(indices)):
        for j in range(4):
            v = pend.iloc[i, j]
            if np.isnan(v):
                continue
            ax.text(j, i, f"{v:+.2f}{' *' if sig.iloc[i, j] else ''}", ha="center", va="center", fontsize=7.5,
                    color=config.TEXTO, fontweight="bold" if sig.iloc[i, j] else "normal")
    ax.set_xticks(range(4), config.REGIONES)
    ax.set_yticks(range(len(indices)), [NOMBRES[i] for i in indices], fontsize=8)
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.03)
    cb.set_label("Tendencia (% de la media por década)")
    ax.set_title("Tendencia de los índices de extremos (unidades del índice por década)")
    nota(fig, "* = significativa con Mann-Kendall corregido por autocorrelación (Hamed-Rao, p < 0,05).")
    return guardar(fig, "10_extremos_tendencias.png")


def fig_enso_rezagos(a: dict) -> Path:
    c = a["corr_region"]
    fig, ejes = plt.subplots(1, 2, figsize=(10.5, 3.8), sharey=True)
    for ax, var, titulo in [(ejes[0], "precip_pct", "lluvia mensual"),
                            (ejes[1], "tmed", "temperatura media mensual")]:
        for region, d in c[c["variable"] == var].groupby("region"):
            col = config.COLOR_REGION[region]
            ax.plot(d["rezago"], d["r"], color=col, label=region, marker="o", markersize=4)
            no = d[~d["significativa"]]
            ax.scatter(no["rezago"], no["r"], s=40, color="white", edgecolor=col, zorder=3)
        ax.axhline(0, color=config.GRIS, linewidth=0.8)
        ax.set_title(f"ONI vs {titulo}")
        ax.set_xlabel("Rezago (meses que el ONI se adelanta)")
    ejes[0].set_ylabel("r de Pearson")
    ejes[0].legend(fontsize=7.5)
    nota(fig, "Anomalías mensuales 1980–2024. Punto hueco: no significativa con el tamaño de muestra efectivo "
              "(Bretherton et al. 1999).")
    return guardar(fig, "11_enso_rezagos.png")


def fig_enso_costa(a: dict) -> Path:
    oni = a["oni"]
    m = a["anom_reg_m"]
    costa = m[m["region"] == "Costa"].set_index("mes")["precip"]
    fig, ejes = plt.subplots(2, 1, figsize=(11, 5), sharex=True, gridspec_kw={"height_ratios": [1, 1.4]})
    ax = ejes[0]
    ax.fill_between(oni["fecha"], oni["oni"], 0, where=oni["oni"] >= 0, color=config.CALIDO, linewidth=0)
    ax.fill_between(oni["fecha"], oni["oni"], 0, where=oni["oni"] < 0, color=config.FRIO, linewidth=0)
    ax.axhline(0.5, color=config.GRIS, linewidth=0.6, ls="--")
    ax.axhline(-0.5, color=config.GRIS, linewidth=0.6, ls="--")
    ax.set_title("Índice ONI (Niño 3.4, °C): rojo = El Niño, azul = La Niña")
    ax = ejes[1]
    suave = costa.rolling(3, center=True).mean()
    ax.bar(costa.index, costa.to_numpy(), width=31, color=np.where(costa >= 0, config.FRIO, "#a8611d"),
           linewidth=0, edgecolor="none")
    ax.plot(suave.index, suave.to_numpy(), color=config.TEXTO, linewidth=1)
    ax.set_title("Costa: anomalía de lluvia mensual (mm, vs 1981–2010) y media móvil de 3 meses")
    ax.set_ylabel("mm")
    return guardar(fig, "12_enso_costa.png")


def fig_compuestos(a: dict) -> Path:
    c = a["comp_enso"]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    fases = ["La Niña", "Neutral", "El Niño"]
    colores = {"La Niña": config.FRIO, "Neutral": config.GRIS, "El Niño": config.CALIDO}
    ancho = 0.26
    for k, fase in enumerate(fases):
        d = c[c["fase"] == fase].set_index("region").reindex(config.REGIONES)
        x = np.arange(4) + (k - 1) * ancho
        ax.bar(x, d["media"], width=ancho - 0.03, color=colores[fase], label=fase)
        for xi, v in zip(x, d["media"]):
            ax.text(xi, v + (2 if v >= 0 else -2), f"{v:+.0f} %", ha="center", va="bottom" if v >= 0 else "top",
                    fontsize=7, color=config.TEXTO)
    ax.set_xticks(range(4), config.REGIONES)
    ax.axhline(0, color=config.GRIS, linewidth=0.8)
    ax.set_ylabel("Anomalía media de lluvia (% de la normal)")
    ax.set_title("Lluvia de enero a abril según la fase de ENOS (meses 1980–2024)")
    ax.legend(fontsize=8)
    return guardar(fig, "13_enso_compuestos.png")


def fig_oni_vs_nino12(a: dict, region: str = "Costa") -> Path:
    t = a["temporada"]
    c = a["comp_indices"].set_index(["region", "indice"])
    fig, ejes = plt.subplots(1, 2, figsize=(10.5, 4.2), sharey=True)
    destacados = {1983: "1983", 1992: "1992", 1998: "1998", 2016: "2016", 2024: "2024"}
    for ax, ind, nombre in [(ejes[0], "oni", "ONI (Niño 3.4, Pacífico central)"),
                            (ejes[1], "nino12", "Niño 1+2 (frente a la costa)")]:
        d = t[["anio", region, ind]].dropna()
        ax.scatter(d[ind], d[region], s=30, color=config.COLOR_REGION[region], edgecolor="white", linewidth=0.6)
        for _, f in d[d["anio"].isin(destacados)].iterrows():
            ax.annotate(destacados[int(f["anio"])], (f[ind], f[region]), xytext=(5, 2), textcoords="offset points",
                        fontsize=8, color=config.TEXTO, fontweight="bold")
        ax.axhline(0, color=config.GRIS, linewidth=0.8)
        ax.axvline(0, color=config.GRIS, linewidth=0.8)
        rs = c.loc[(region, ind), "r_spearman"]
        ax.set_title(f"{nombre} · Spearman {rs:+.2f}")
        ax.set_xlabel("Índice medio de enero a abril (°C)")
    ejes[0].set_ylabel(f"{region}: lluvia ene–abr (% sobre la normal)")
    nota(fig, "Cada punto es un año 1980–2024. 2016 tuvo el ONI más alto pero el mar frente a la costa no se calentó "
              "tanto: la Costa tuvo lluvia normal.")
    fig.tight_layout()
    return guardar(fig, "18_enso_oni_vs_nino12.png")


def fig_validacion(a: dict) -> Path:
    v = a["validacion"].copy()
    v = v.sort_values(["region", "altitud"])
    etiquetas = [f"{n}\n{int(z)} m" for n, z in zip(v["nombre"], v["altitud"])]
    fig, ejes = plt.subplots(1, 3, figsize=(12.5, 4.4), sharey=True)
    y = np.arange(len(v))
    colores = [config.COLOR_REGION[r] for r in v["region"]]
    ancho = 0.36
    ejes[0].barh(y - ancho / 2, v["sesgo_tmax"], height=ancho, color=config.CALIDO, label="Tmáx")
    ejes[0].barh(y + ancho / 2, v["sesgo_tmin"], height=ancho, color=config.FRIO, label="Tmín")
    ejes[0].axvline(0, color=config.GRIS, linewidth=0.8)
    ejes[0].set_title("Sesgo ERA5 − estación (°C)")
    ejes[0].legend(fontsize=7.5)
    ejes[1].barh(y, v["ratio_lluvia"], color=colores, height=0.6)
    ejes[1].axvline(1, color=config.GRIS, linewidth=0.8)
    ejes[1].set_title("Lluvia ERA5 / estación (veces)")
    for i, r in enumerate(v["ratio_lluvia"]):
        if np.isfinite(r):
            ejes[1].text(r + 0.05, i, f"{r:.1f}×", va="center", fontsize=7.5)
    ejes[2].barh(y - ancho / 2, v["r_anom_tmax"], height=ancho, color=config.CALIDO, label="Anomalía diaria de Tmáx")
    ejes[2].barh(y + ancho / 2, v["r_lluvia_mensual"], height=ancho, color=config.FRIO, label="Lluvia mensual")
    ejes[2].set_xlim(0, 1)
    ejes[2].set_title("Correlación ERA5 vs estación")
    ejes[2].legend(fontsize=7.5, loc="upper right")
    ejes[0].set_yticks(y, etiquetas, fontsize=7.5)
    nota(fig, "Estaciones NOAA GHCN-Daily (solo valores sin marca de calidad). Temperatura de ERA5 corregida a la "
              "altitud de la estación con −6,5 °C/km. Color de la lluvia: región.")
    fig.tight_layout()
    return guardar(fig, "14_validacion_estaciones.png")


def lluvia_mensual_pareada(unidas: pd.DataFrame, estacion: str, min_dias: int = 20) -> pd.DataFrame:
    """Lluvia mensual de ERA5 y de la estación sumando solo los días en que ambas tienen dato."""
    d = unidas[unidas["estacion"] == estacion].dropna(subset=["precip_est", "precip_era5"]).set_index("fecha")
    g = d[["precip_era5", "precip_est"]].resample("MS")
    m = g.sum()
    m["dias"] = g.size()
    return m[m["dias"] >= min_dias]


def fig_validacion_series(a: dict, estaciones: tuple[str, ...] = ("ECM00084088", "ECM00084179", "ECM00084050")) -> Path:
    u = a["unidas"]
    fig, ejes = plt.subplots(1, len(estaciones), figsize=(12, 4.2))
    for ax, est in zip(np.atleast_1d(ejes), estaciones):
        m = lluvia_mensual_pareada(u, est)
        col = config.COLOR_REGION[config.ESTACIONES[est][4]]
        ax.scatter(m["precip_est"], m["precip_era5"], s=24, color=col, alpha=0.8, edgecolor="white", linewidth=0.5)
        lim = float(max(m["precip_est"].max(), m["precip_era5"].max()) * 1.05)
        ax.plot([0, lim], [0, lim], color=config.GRIS, ls="--", linewidth=0.8)
        ax.set_xlim(0, lim)
        ax.set_ylim(0, lim)
        ax.set_aspect("equal")
        r = m["precip_era5"].corr(m["precip_est"])
        cociente = m["precip_era5"].sum() / m["precip_est"].sum()
        ax.set_title(f"{config.ESTACIONES[est][0]} · {config.ESTACIONES[est][3]:,} m".replace(",", "."))
        ax.text(0.03, 0.97, f"{len(m)} meses · r = {r:.2f}\nERA5 / estación = {cociente:.2f}",
                transform=ax.transAxes, va="top", fontsize=8, color=config.TEXTO)
        ax.set_xlabel("Estación (mm/mes)")
    np.atleast_1d(ejes)[0].set_ylabel("ERA5 (mm/mes)")
    nota(fig, "Meses con al menos 20 días con dato en ambas fuentes (se suman solo esos días). Línea discontinua: 1 a 1.")
    fig.tight_layout()
    return guardar(fig, "15_validacion_lluvia_mensual.png")


def todas(s: dict, a: dict) -> list[Path]:
    estilo()
    t = a["tend_ciudad"]
    tmed = t[t["variable"] == "tmed"].set_index("punto")
    lluvia = t[t["variable"] == "precip"].set_index("punto")
    rutas = [
        mapa_puntos(None, "22 ciudades en las 4 regiones del Ecuador", "", "01_mapa_ciudades.png"),
        fig_calidad(s), fig_climatologia(a), fig_ciclo_diurno(s), fig_franjas(a), fig_anomalias_regiones(a),
        fig_tendencias_ciudades(a), fig_correccion_autocorrelacion(a), fig_extremos(a), fig_tabla_extremos(a),
        fig_enso_rezagos(a), fig_enso_costa(a), fig_compuestos(a), fig_validacion(a), fig_validacion_series(a),
        fig_oni_vs_nino12(a),
        mapa_puntos(tmed["pendiente_decada"], "Tendencia de la temperatura media 1980–2024", "°C por década",
                    "16_mapa_tendencia_temperatura.png", significativo=tmed["significativa"]),
        mapa_puntos(lluvia["pendiente_pct_decada"], "Tendencia de la lluvia anual 1980–2024", "% de la media por década",
                    "17_mapa_tendencia_lluvia.png", cmap=DIVERGENTE_LLUVIA, significativo=lluvia["significativa"],
                    formato="{:+.1f} %"),
    ]
    return rutas
