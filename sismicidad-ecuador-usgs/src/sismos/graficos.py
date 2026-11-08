"""Figuras del proyecto (matplotlib). Cada función guarda un PNG numerado en reports/figures/."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from . import config  # noqa: E402
from . import gutenberg_richter as gr  # noqa: E402
from . import omori  # noqa: E402
from .calidad import a_mw  # noqa: E402

# Paleta categórica (orden fijo) y rampa secuencial de un solo tono para la profundidad
AZUL, NARANJA, AGUA, AMARILLO, VIOLETA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#6250d6"
GRIS, TINTA, TINTA_2 = "#9a9993", "#0b0b0b", "#52514e"
RAMPA_PROFUNDIDAD = LinearSegmentedColormap.from_list("profundidad", ["#f2a65e", "#c2410c", "#7a1f6b", "#1f1147"])

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 130, "savefig.bbox": "tight", "font.size": 10,
    "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#b8b7b0",
    "axes.labelcolor": TINTA_2, "xtick.color": TINTA_2, "ytick.color": TINTA_2,
    "axes.grid": True, "grid.color": "#e6e5e0", "grid.linewidth": 0.6, "axes.titleweight": "bold",
    "axes.titlesize": 11, "legend.frameon": False, "axes.formatter.use_locale": False,
})


def miles(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _guardar(fig, nombre: str) -> Path:
    config.FIGURAS.mkdir(parents=True, exist_ok=True)
    ruta = config.FIGURAS / nombre
    fig.savefig(ruta, facecolor="white")
    plt.close(fig)
    return ruta


# ---- capas de mapa ---------------------------------------------------------------------------
def _lineas_geojson(nombre: str) -> list[np.ndarray]:
    ruta = config.CRUDOS / "capas" / nombre
    if not ruta.exists():
        return []
    lineas = []
    for f in json.loads(ruta.read_text(encoding="utf-8"))["features"]:
        g = f["geometry"]
        partes = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        lineas.extend(np.asarray(p, dtype=float) for p in partes)
    return lineas


def _dibujar_capas(ax, extension, pacifico: bool = False, placas: bool = True):
    lon0, lon1, lat0, lat1 = extension
    capas = [("costas_ne50m.geojson", dict(color="#8c8b85", lw=0.6)),
             ("fronteras_ne50m.geojson", dict(color="#b8b7b0", lw=0.5, ls=(0, (3, 2))))]
    if placas:
        capas.append(("placas_pb2002.json", dict(color=AZUL, lw=1.1, alpha=0.8)))
    for nombre, estilo in capas:
        for xy in _lineas_geojson(nombre):
            x, y = xy[:, 0].copy(), xy[:, 1]
            if pacifico:
                x = np.where(x < 0, x + 360, x)
                cortes = np.where(np.abs(np.diff(x)) > 180)[0] + 1
                for xs, ys in zip(np.split(x, cortes), np.split(y, cortes)):
                    ax.plot(xs, ys, zorder=1, **estilo)
            else:
                if x.max() < lon0 - 5 or x.min() > lon1 + 5 or y.max() < lat0 - 5 or y.min() > lat1 + 5:
                    continue
                ax.plot(x, y, zorder=1, **estilo)
    ax.set_xlim(lon0, lon1)
    ax.set_ylim(lat0, lat1)
    ax.set_aspect(1 / np.cos(np.radians((lat0 + lat1) / 2)))
    ax.grid(False)


def _tamano(m):
    return 2 + (np.asarray(m) - 2.5).clip(0) ** 2.6 * 2.2


# ---- 01 · calidad ----------------------------------------------------------------------------
def fig_calidad(df: pd.DataFrame) -> Path:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2))
    quinq = (df["anio"] // 5) * 5
    tabla = pd.crosstab(quinq, df["familia_mag"], normalize="index") * 100
    orden = [(c, col) for c, col in (("mb", NARANJA), ("Mw", AZUL), ("Local", AGUA), ("Ms", VIOLETA))
             if c in tabla]
    base = np.zeros(len(tabla))
    for familia, color in orden:
        a1.bar(tabla.index, tabla[familia], bottom=base, width=4.2, color=color, label=familia,
               edgecolor="white", linewidth=1)
        base += tabla[familia].to_numpy()
    a1.set_title("Escala de magnitud reportada (% por quinquenio)")
    a1.set_ylabel("% de eventos")
    a1.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.1))

    sin_dither, _ = a_mw(df["mag_original"], df["familia_mag"])
    clases = np.arange(3.0, 7.0, 0.1)
    h1 = pd.Series(gr.a_clases(sin_dither)).value_counts().reindex(np.round(clases, 6), fill_value=0)
    h2 = pd.Series(df["mw"].to_numpy()).value_counts().reindex(np.round(clases, 1), fill_value=0)
    a2.step(clases, h1.to_numpy(), where="mid", color=GRIS, lw=1.5, label="mb→Mw directo (picos falsos)")
    a2.step(clases, h2.to_numpy(), where="mid", color=NARANJA, lw=2, label="mb→Mw con reparto en la clase")
    a2.set_yscale("log")
    a2.set_xlim(3.5, 7)
    a2.set_title("mb→Mw sin repartir en la clase crea picos falsos")
    a2.set_xlabel("Mw (clases de 0,1)")
    a2.set_ylabel("eventos por clase")
    a2.legend()
    return _guardar(fig, "01_calidad_magnitudes.png")


# ---- 02–03 · exploratorio --------------------------------------------------------------------
def fig_eventos_por_anio(df: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(12, 4))
    bandas = pd.cut(df["mw"], [0, 5, 6, 10], right=False, labels=["M<5", "5≤M<6", "M≥6"])
    tabla = pd.crosstab(df["anio"], bandas).reindex(range(config.ANIO_INICIO_ECUADOR, config.ANIO_FIN + 1),
                                                   fill_value=0)
    base = np.zeros(len(tabla))
    for banda, color in zip(tabla.columns, (GRIS, AZUL, NARANJA)):
        ax.bar(tabla.index, tabla[banda], bottom=base, color=color, label=str(banda), width=0.8)
        base += tabla[banda].to_numpy()
    ax.annotate("Pedernales 2016 (M7,8)\ny sus réplicas", xy=(2016, base[tabla.index.get_loc(2016)]),
                xytext=(2003, base.max() * 0.95), color=TINTA_2,
                arrowprops=dict(arrowstyle="->", color=TINTA_2))
    ax.set_title("Sismos por año en el Ecuador ampliado (catálogo USGS, Mw homogénea)")
    ax.set_ylabel("eventos")
    ax.legend(ncol=3, loc="upper left")
    return _guardar(fig, "02_eventos_por_anio.png")


def fig_magnitud_profundidad(df: pd.DataFrame) -> Path:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4))
    a1.hist(df["mw"], bins=np.arange(2.95, 8.15, 0.1), color=AZUL, edgecolor="white", linewidth=0.6)
    a1.set_yscale("log")
    a1.set_title("Distribución de magnitudes (escala log)")
    a1.set_xlabel("Mw")
    a1.set_ylabel("eventos")
    libres = df[~df["profundidad_fija"]]
    fijas = df[df["profundidad_fija"]]
    bins = np.arange(0, 260, 5)
    a2.hist(libres["profundidad_km"], bins=bins, color=AZUL, label="profundidad calculada",
            edgecolor="white", linewidth=0.6)
    a2.hist(fijas["profundidad_km"], bins=bins, color=NARANJA, label="profundidad fija (10/33/35 km)",
            edgecolor="white", linewidth=0.6)
    a2.axvline(70, color=TINTA_2, lw=1, ls="--")
    a2.text(72, a2.get_ylim()[1] * 0.9, "70 km: superficial | intermedio", color=TINTA_2, fontsize=9)
    a2.set_title("Profundidad: dos grupos (interfaz somera y placa de Nazca a 100–200 km)")
    a2.set_xlabel("profundidad (km)")
    a2.legend()
    return _guardar(fig, "03_magnitud_y_profundidad.png")


def fig_mapa_ecuador(df: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(8.5, 9))
    d = df.sort_values("profundidad_km", ascending=False)
    sc = ax.scatter(d["longitud"], d["latitud"], s=_tamano(d["mw"]), c=d["profundidad_km"].clip(0, 250),
                    cmap=RAMPA_PROFUNDIDAD, alpha=0.75, edgecolors="white", linewidths=0.3, zorder=2)
    p = config.PEDERNALES
    ax.scatter(p["longitud"], p["latitud"], marker="*", s=420, color=AMARILLO, edgecolors=TINTA, zorder=3,
               label="Pedernales 2016 (M7,8)")
    _dibujar_capas(ax, (-82, -74, -6, 3))
    ax.text(-81.7, -5.6, "Placa de Nazca", color=AZUL, fontsize=10, style="italic")
    ax.text(-76.4, 2.5, "Placa Sudamericana", color=AZUL, fontsize=10, style="italic")
    cb = fig.colorbar(sc, ax=ax, shrink=0.6, pad=0.02)
    cb.set_label("profundidad (km)")
    cb.ax.invert_yaxis()
    for m in (4, 6, 8):
        ax.scatter([], [], s=_tamano(m), color=GRIS, label=f"M{m}")
    ax.legend(loc="lower right", fontsize=9, frameon=True, facecolor="white", framealpha=0.9)
    ax.set_title(f"Epicentros M≥2,5 1970–{config.ANIO_FIN} ({miles(len(df))} sismos): "
                 "la profundidad crece hacia el este", fontsize=11)
    ax.set_xlabel("longitud")
    ax.set_ylabel("latitud")
    return _guardar(fig, "04_mapa_epicentros_ecuador.png")


def fig_perfil(perfil: pd.DataFrame, pendiente: dict) -> Path:
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.scatter(perfil["longitud"], perfil["profundidad_km"], s=_tamano(perfil["mw"]),
               c=perfil["profundidad_km"].clip(0, 250), cmap=RAMPA_PROFUNDIDAD, alpha=0.7,
               edgecolors="white", linewidths=0.3)
    ax.invert_yaxis()
    ax.set_xlim(-82, -74)
    ax.set_ylim(260, -5)
    ax.axvline(-80.9, color=AZUL, lw=1, ls="--")
    ax.text(-80.85, 245, "≈ fosa", color=AZUL)
    ax.text(-75.5, 30, "corteza\nsudamericana", color=TINTA_2, ha="center")
    ax.set_title(f"Corte este–oeste (latitud 2,5°S a 1,5°N): la placa de Nazca se hunde bajo el continente "
                 f"(pendiente aparente ≈ {pendiente['angulo_grados']:.0f}°)".replace(".", ","))
    ax.set_xlabel("longitud")
    ax.set_ylabel("profundidad (km)")
    return _guardar(fig, "05_perfil_subduccion.png")


# ---- 06–07 · Gutenberg-Richter --------------------------------------------------------------
def fig_gutenberg_richter(m, ajuste: dict, titulo: str, nombre: str) -> Path:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    clases, acum = gr.distribucion_acumulada(m)
    c2, nc = gr.distribucion_no_acumulada(m)
    ax.semilogy(clases, acum, "o", ms=4.5, color=TINTA_2, label="N(≥M) acumulado")
    ax.semilogy(c2[nc > 0], nc[nc > 0], "s", ms=3.5, color=GRIS, label="eventos por clase")
    for clave, color, etiqueta in (("maxc", NARANJA, "Mc por máxima curvatura"),
                                   ("mbs", AZUL, "Mc por estabilidad de b (MBS)")):
        aj = ajuste.get(clave)
        if not aj:
            continue
        x = np.linspace(aj["mc"], clases.max(), 50)
        ax.semilogy(x, aj["n"] * 10 ** (-aj["b"] * (x - aj["mc"])), color=color, lw=2,
                    label=f"{etiqueta}: Mc={aj['mc']:.1f}, b={aj['b']:.2f} "
                          f"[{aj['ic95_bajo']:.2f}–{aj['ic95_alto']:.2f}]".replace(".", ","))
        ax.axvline(aj["mc"], color=color, lw=1, ls=":")
    ax.set_xlabel("Mw")
    ax.set_ylabel("número de sismos")
    ax.set_title(titulo)
    ax.legend(fontsize=9)
    return _guardar(fig, nombre)


def fig_estabilidad_b(tabla: pd.DataFrame, mc_maxc: float, mc_mbs: float) -> Path:
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.errorbar(tabla["mc"], tabla["b"], yerr=1.96 * tabla["sigma"], fmt="o-", color=AZUL, ms=4, lw=1.5,
                capsize=2, label="b de Aki ± IC 95 %")
    ax.axvline(mc_maxc, color=NARANJA, ls=":", label=f"Mc máxima curvatura = {mc_maxc:.1f}".replace(".", ","))
    ax.axvline(mc_mbs, color=AZUL, ls="--", label=f"Mc estabilidad de b = {mc_mbs:.1f}".replace(".", ","))
    ax.axhline(1, color=GRIS, lw=1)
    ax.set_xlabel("umbral de magnitud Mc")
    ax.set_ylabel("valor b")
    ax.set_title("El valor b depende del umbral: debajo de ~M5,5 dominan las mb convertidas")
    ax.legend(fontsize=9)
    return _guardar(fig, "07_estabilidad_valor_b.png")


# ---- 08–10 · Cinturón de Fuego ----------------------------------------------------------------
def fig_mapa_cinturon(mundo: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(14, 7))
    d = mundo.sort_values("profundidad_km", ascending=False)
    lon = np.where(d["longitud"] < 0, d["longitud"] + 360, d["longitud"])
    sc = ax.scatter(lon, d["latitud"], s=_tamano(d["mw"]) * 0.25, c=d["profundidad_km"].clip(0, 700),
                    cmap=RAMPA_PROFUNDIDAD, alpha=0.5, linewidths=0, zorder=2)
    _dibujar_capas(ax, (95, 300, -60, 65), pacifico=True)
    ax.set_aspect(1)
    for zona, (la0, la1, lo0, lo1) in config.ZONAS_CINTURON.items():
        x0, x1 = (lo0 + 360 if lo0 < 0 else lo0), (lo1 + 360 if lo1 <= 0 else lo1)
        es_ec = zona == "Ecuador"
        ax.add_patch(plt.Rectangle((x0, la0), x1 - x0, la1 - la0, fill=False, lw=2 if es_ec else 1,
                                   ec=AMARILLO if es_ec else TINTA_2, zorder=3))
        ax.text(x0 + 0.5, la1 + 0.8, zona, fontsize=8, color=TINTA, weight="bold" if es_ec else None, zorder=4)
    cb = fig.colorbar(sc, ax=ax, shrink=0.6, pad=0.01)
    cb.set_label("profundidad (km)")
    cb.ax.invert_yaxis()
    ticks = np.arange(100, 301, 40)
    ax.set_xticks(ticks, [f"{t}°E" if t <= 180 else f"{360 - t}°O" for t in ticks])
    ax.set_title(f"Cinturón de Fuego del Pacífico: sismos M≥5, {config.ANIO_INICIO_GLOBAL}–{config.ANIO_FIN}, "
                 "y las 13 zonas comparadas")
    return _guardar(fig, "08_mapa_cinturon_de_fuego.png")


def fig_b_por_zona(tabla: pd.DataFrame, mc_comun: float) -> Path:
    t = tabla.sort_values("b_mc_comun")
    fig, ax = plt.subplots(figsize=(9, 6))
    y = np.arange(len(t))
    colores = [AMARILLO if z == "Ecuador" else AZUL for z in t["zona"]]
    ax.hlines(y, t["b_mc_comun_ic95_bajo"], t["b_mc_comun_ic95_alto"], color=colores, lw=2.5)
    ax.scatter(t["b_mc_comun"], y, color=colores, s=55, zorder=3, edgecolors="white")
    for yi, (_, f) in zip(y, t.iterrows()):
        ax.text(f["b_mc_comun_ic95_alto"] + 0.015, yi, f"{f['b_mc_comun']:.2f}  (n={f['n_mc_comun']})"
                .replace(".", ","), va="center", fontsize=8.5, color=TINTA_2)
    ax.set_yticks(y, t["zona"])
    ax.axvline(1, color=GRIS, lw=1)
    ax.set_xlabel(f"valor b (Aki, M≥{mc_comun:.1f}) con IC 95 % de Shi-Bolt".replace(".", ","))
    ax.set_title("Valor b por zona del Cinturón: Ecuador tiene de los más bajos")
    ax.set_xlim(t["b_mc_comun_ic95_bajo"].min() - 0.05, t["b_mc_comun_ic95_alto"].max() + 0.2)
    return _guardar(fig, "09_valor_b_por_zona.png")


def fig_gr_vs_empirico(tabla: pd.DataFrame) -> Path:
    t = tabla.sort_values("tasa_m7_empirica")
    fig, ax = plt.subplots(figsize=(9, 6))
    y = np.arange(len(t))
    ax.hlines(y, t["tasa_m7_gr"], t["tasa_m7_empirica"], color="#d6d5cf", lw=3)
    ax.scatter(t["tasa_m7_empirica"], y, color=NARANJA, s=50, zorder=3, label="conteo real M≥7 / años (línea base)")
    ax.scatter(t["tasa_m7_gr"], y, color=AZUL, s=50, zorder=3, label="Gutenberg-Richter extrapolado desde M5,5")
    ax.set_yticks(y, t["zona"])
    ax.set_xlabel("sismos M≥7 por año (1973–2025)")
    ax.set_title("Extrapolar la recta hasta M7: acierta en unas zonas y se queda corta en otras")
    ax.legend(loc="lower right", fontsize=9)
    return _guardar(fig, "10_m7_gr_vs_conteo.png")


# ---- 11 · periodos de retorno --------------------------------------------------------------
def fig_retorno(df_principal: pd.DataFrame, historico_principal: pd.DataFrame, aj: dict, anios: int,
                anios_hist: int) -> Path:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    mags = np.round(np.arange(5.0, 8.05, 0.1), 1)
    emp = [(df_principal["mw"] >= m).sum() / anios for m in mags]
    ax.semilogy(mags, emp, "o", color=NARANJA, ms=5, label="conteo 1970–2025 (desagrupado)")
    emp_h = [(historico_principal["mw"] >= m).sum() / anios_hist for m in mags if m >= 6]
    ax.semilogy([m for m in mags if m >= 6], emp_h, "^", color=VIOLETA, ms=5, label="conteo 1900–2025, M≥6")
    x = np.linspace(aj["mc"], 8.3, 60)
    rng = np.random.default_rng(config.SEMILLA)
    m = gr.a_clases(df_principal["mw"])
    m = m[m >= aj["mc"] - 1e-9]
    curvas = []
    for _ in range(500):
        mm = rng.choice(m, len(m))
        b = gr.LOG10_E / (mm.mean() - (aj["mc"] - 0.05))
        curvas.append(rng.poisson(len(m)) / anios * 10 ** (-b * (x - aj["mc"])))
    bajo, alto = np.percentile(curvas, [2.5, 97.5], axis=0)
    ax.fill_between(x, bajo, alto, color=AZUL, alpha=0.18, lw=0, label="IC 95 % (bootstrap)")
    ax.semilogy(x, aj["n"] / anios * 10 ** (-aj["b"] * (x - aj["mc"])), color=AZUL, lw=2,
                label=f"Gutenberg-Richter (Mc={aj['mc']:.1f}, b={aj['b']:.2f})".replace(".", ","))
    for m_obj in (6, 7):
        tasa = aj["n"] / anios * 10 ** (-aj["b"] * (m_obj - aj["mc"]))
        ax.annotate(f"M≥{m_obj}: cada {1 / tasa:.1f} años en promedio".replace(".", ","),
                    xy=(m_obj, tasa), xytext=(m_obj + 0.15, tasa * 2.2), color=TINTA,
                    arrowprops=dict(arrowstyle="->", color=TINTA_2))
    ax.set_xlabel("magnitud mínima M")
    ax.set_ylabel("sismos con magnitud ≥ M por año")
    ax.set_title("Frecuencia anual de sismos en el Ecuador ampliado (frecuencia media, no predicción)")
    ax.legend(fontsize=9, loc="lower left")
    return _guardar(fig, "11_periodos_de_retorno.png")


# ---- 12–13 · Pedernales ---------------------------------------------------------------------
def fig_mapa_replicas(rep: pd.DataFrame, mc: float) -> Path:
    fig, ax = plt.subplots(figsize=(7.5, 7.5))
    sc = ax.scatter(rep["longitud"], rep["latitud"], s=_tamano(rep["mw"]), c=rep["dias"], cmap="Blues_r",
                    norm=matplotlib.colors.LogNorm(0.01, 365), edgecolors=TINTA_2, linewidths=0.4, zorder=2)
    p = config.PEDERNALES
    ax.scatter(p["longitud"], p["latitud"], marker="*", s=500, color=AMARILLO, edgecolors=TINTA, zorder=3)
    angulo = np.linspace(0, 2 * np.pi, 200)
    radio = config.RADIO_REPLICAS_KM / 111.32
    ax.plot(p["longitud"] + radio * np.cos(angulo) / np.cos(np.radians(p["latitud"])),
            p["latitud"] + radio * np.sin(angulo), color=GRIS, ls="--", lw=1)
    _dibujar_capas(ax, (-81.8, -78.2, -1.6, 2.0))
    cb = fig.colorbar(sc, ax=ax, shrink=0.7, pad=0.02)
    cb.set_label("días después del sismo principal")
    ax.set_title(f"Réplicas de Pedernales 2016 (año siguiente, ≤150 km): {len(rep)} sismos M≥2,5 en el USGS")
    return _guardar(fig, "12_mapa_replicas_pedernales.png")


def fig_omori(t: np.ndarray, res: dict) -> Path:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.8))
    u, e, p1 = res["omori_utsu"], res["exponencial"], res["omori_p1"]
    bordes = np.logspace(np.log10(0.005), np.log10(365), 16)
    conteo, _ = np.histogram(t, bordes)
    centro = np.sqrt(bordes[1:] * bordes[:-1])
    ancho = np.diff(bordes)
    ok = conteo > 0
    a1.loglog(centro[ok], conteo[ok] / ancho[ok], "o", color=TINTA_2, ms=6, label="observado (réplicas/día)")
    x = np.logspace(np.log10(0.005), np.log10(365), 200)
    a1.loglog(x, omori.tasa_omori(x, u["K"], u["c"], u["p"]), color=AZUL, lw=2,
              label=f"Omori-Utsu: p={u['p']:.2f}±{u['se_p']:.2f}, c={u['c']:.2f} d".replace(".", ","))
    a1.loglog(x, e["A"] * np.exp(-x / e["tau_dias"]), color=NARANJA, lw=1.5, ls="--",
              label=f"exponencial (línea base): τ={e['tau_dias']:.1f} d".replace(".", ","))
    a1.set_ylim(conteo[ok].min() / ancho[ok].max() / 5, None)
    a1.set_xlabel("días desde el sismo principal")
    a1.set_ylabel("réplicas por día")
    a1.set_title(f"Tasa de réplicas M≥{res['mc']:.1f}: decae como una potencia de t".replace(".", ","))
    a1.legend(fontsize=9)

    a2.step(np.r_[0, t], np.arange(len(t) + 1), where="post", color=TINTA_2, lw=1.8, label="observado")
    x2 = np.linspace(0, 365, 400)
    a2.plot(x2, omori.acumulado_omori(x2, u["K"], u["c"], u["p"]), color=AZUL, lw=2, label="Omori-Utsu")
    a2.plot(x2, omori.acumulado_omori(x2, p1["K"], p1["c"], 1.0), color=VIOLETA, lw=1.2, ls=":",
            label="Omori p=1")
    a2.plot(x2, e["A"] * e["tau_dias"] * (1 - np.exp(-x2 / e["tau_dias"])), color=NARANJA, lw=1.5, ls="--",
            label="exponencial")
    a2.set_xscale("symlog", linthresh=1)
    a2.set_xlabel("días desde el sismo principal (escala log después de 1 día)")
    a2.set_ylabel("réplicas acumuladas")
    a2.set_title(f"ΔAIC exponencial − Omori-Utsu = {res['delta_aic_exponencial_vs_utsu']:.0f}".replace(".", ","))
    a2.legend(fontsize=9)
    return _guardar(fig, "13_omori_pedernales.png")
