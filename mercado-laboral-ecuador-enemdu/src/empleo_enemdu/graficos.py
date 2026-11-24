"""Generación de las 10 figuras editoriales del estudio del mercado laboral (ENEMDU 2025)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from empleo_enemdu.config import DIR_FIGURAS, PALETA, SBU_USD_2025


def _num(valor: float, decimales: int = 1) -> str:
    """Formatea un número con coma decimal para los subtítulos (estilo es-EC)."""
    return f"{valor:.{decimales}f}".replace(".", ",")


def configurar_estilo() -> None:
    """Configura un estilo tipográfico y de ejes limpio para todas las figuras."""
    plt.rcParams.update(
        {
            "figure.facecolor": "#fbfbfd",
            "axes.facecolor": "#fbfbfd",
            "axes.edgecolor": "#cccccc",
            "axes.linewidth": 0.8,
            "axes.grid": True,
            "grid.color": "#e5e7eb",
            "grid.linewidth": 0.6,
            "font.family": "sans-serif",
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.labelsize": 10,
            "xtick.color": "#374151",
            "ytick.color": "#374151",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "savefig.dpi": 160,
            "savefig.bbox": "tight",
        }
    )


def fig_01_diseno_muestral_y_reconciliacion(
    df_reconciliacion: pd.DataFrame,
    dir_figuras: Path = DIR_FIGURAS,
) -> Path:
    """Compara estimaciones ponderadas vs sin ponderar y DEFT (EE complejo / EE MAS)."""
    configurar_estilo()
    sub = df_reconciliacion.loc[df_reconciliacion["dominio"] == "Total"].copy()
    orden_ind = [
        "Participación Global",
        "Empleo Bruto",
        "Sector informal",
        "Empleo Adecuado/Pleno",
        "Otro Empleo no pleno",
        "Subempleo",
        "Empleo no Remunerado",
        "Desempleo",
    ]
    sub = sub.set_index("indicador").loc[orden_ind].reset_index()
    dif_max = float(sub["dif_indicador_pp"].abs().max())
    sesgos = sub.set_index("indicador")["sesgo_sin_ponderar_pp"]
    sesgo_inf = ("+" if sesgos["Sector informal"] >= 0 else "") + _num(sesgos["Sector informal"])
    sesgo_nr = ("+" if sesgos["Empleo no Remunerado"] >= 0 else "") + _num(sesgos["Empleo no Remunerado"])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 5.8))
    y = np.arange(len(sub))
    h = 0.36

    b1 = ax1.barh(
        y + h / 2,
        sub["estimacion_pct"],
        height=h,
        color=PALETA["primario"],
        label="Ponderado (fexp) = Oficial INEC",
    )
    ax1.barh(
        y - h / 2,
        sub["sin_ponderar_pct"],
        height=h,
        color=PALETA["acento"],
        alpha=0.85,
        label="Muestra sin ponderar (sesgada)",
    )
    ax1.set_yticks(y)
    ax1.set_yticklabels(sub["indicador"])
    ax1.invert_yaxis()
    ax1.set_xlabel("Porcentaje (%)")
    ax1.set_xlim(0, 82)
    ax1.set_title("Efecto del factor de expansión (fexp) en las tasas", loc="left", pad=16)
    ax1.text(
        0,
        1.02,
        f"Coincide con el tabulado INEC al redondear a 1 decimal (dif. máx. {_num(dif_max)} pp) · "
        f"Sin ponderar: informalidad {sesgo_inf} pp, no remunerado {sesgo_nr} pp",
        transform=ax1.transAxes,
        fontsize=9,
        color="#4b5563",
    )
    ax1.legend(loc="upper left", bbox_to_anchor=(0.0, -0.1), ncol=2, frameon=True, fontsize=8.5)

    for rect, sesgo in zip(b1, sub["sesgo_sin_ponderar_pp"]):
        val = rect.get_width()
        signo = "+" if sesgo >= 0 else ""
        ax1.text(
            val + 0.8,
            rect.get_y() + rect.get_height() / 2,
            f"{val:.1f}% (sesgo: {signo}{sesgo:.1f} pp)",
            va="center",
            fontsize=8.2,
            color="#1f2937",
        )

    # Panel derecho: DEFT = EE complejo / EE MAS
    barras_deft = ax2.barh(
        y,
        sub["deft"],
        height=0.52,
        color=PALETA["secundario"],
    )
    ax2.axvline(1.0, color=PALETA["alerta"], linestyle="--", linewidth=1.2, label="MAS (DEFT = 1,0)")
    ax2.set_yticks(y)
    ax2.set_yticklabels(sub["indicador"])
    ax2.invert_yaxis()
    ax2.set_xlabel("Factor de inflación del error estándar (DEFT = √DEFF)")
    ax2.set_xlim(0, max(sub["deft"]) * 1.32)
    ax2.set_title("Subestimación del error estándar al ignorar UPM y estratos", loc="left", pad=16)
    ax2.text(
        0,
        1.02,
        f"Linealización de Taylor vs. Muestreo Aleatorio Simple (MAS): EE real es "
        f"{_num(sub['deft'].min())}x a {_num(sub['deft'].max())}x mayor",
        transform=ax2.transAxes,
        fontsize=9,
        color="#4b5563",
    )
    ax2.legend(loc="lower right", frameon=True, fontsize=8.5)

    for rect, ee_c, ee_m, deff_v in zip(
        barras_deft, sub["ee_complejo_pct"], sub["ee_mas_pct"], sub["deff"]
    ):
        w = rect.get_width()
        ax2.text(
            w + 0.12,
            rect.get_y() + rect.get_height() / 2,
            f"{w:.1f}x (EE {ee_c:.2f}% vs {ee_m:.2f}% · DEFF={deff_v:.0f})",
            va="center",
            fontsize=8.2,
            color="#1f2937",
        )

    plt.tight_layout()
    ruta = dir_figuras / "01_diseno_muestral_y_reconciliacion.png"
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def fig_02_evolucion_mercado_laboral_2018_2025(
    df_serie: pd.DataFrame,
    dir_figuras: Path = DIR_FIGURAS,
) -> Path:
    """Muestra la serie histórica nacional 2018-2025 y la brecha Urbano vs Rural."""
    configurar_estilo()
    nac = df_serie.loc[df_serie["dominio"] == "Total"].copy()
    piv_nac = nac.pivot_table(index="anio", columns="indicador", values="valor_pct")
    anio_fin = int(piv_nac.index.max())

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 5.6))

    series_cfg = [
        ("Sector informal", PALETA["informal"], "o-", 2.4),
        ("Empleo Adecuado/Pleno", PALETA["adecuado"], "s-", 2.4),
        ("Otro Empleo no pleno", PALETA["otro_no_pleno"], "^--", 1.8),
        ("Subempleo", PALETA["subempleo"], "d-", 2.0),
        ("Desempleo", PALETA["desempleo"], "v-", 2.0),
    ]
    for nombre, color, estilo, lw in series_cfg:
        if nombre in piv_nac.columns:
            s = piv_nac[nombre].dropna()
            ax1.plot(s.index, s.values, estilo, color=color, linewidth=lw, markersize=6, label=nombre)
            ax1.text(
                s.index[-1] + 0.12,
                s.values[-1],
                f"{s.values[-1]:.1f}%",
                va="center",
                fontsize=8.5,
                fontweight="bold",
                color=color,
            )

    ax1.axvspan(2019.6, 2021.3, color="#fee2e2", alpha=0.45, label="Choque pandemia")
    ax1.set_xlim(2017.8, 2025.9)
    ax1.set_ylim(0, 60)
    ax1.set_xlabel("Año (ENEMDU Anual)")
    ax1.set_ylabel("Porcentaje (%)")
    ax1.set_title("Evolución estructural del empleo en el Ecuador (2018–2025)", loc="left", pad=16)
    ax1.text(
        0,
        1.02,
        f"Serie publicada por el INEC · {anio_fin}: desempleo {_num(piv_nac.loc[anio_fin, 'Desempleo'])}% "
        f"e informalidad {_num(piv_nac.loc[anio_fin, 'Sector informal'])}% de los ocupados",
        transform=ax1.transAxes,
        fontsize=9,
        color="#4b5563",
    )
    ax1.legend(loc="upper left", ncol=2, fontsize=8.2, frameon=True)

    # Panel derecho: Urbano vs Rural en 2018-2025 para Empleo Adecuado e Informalidad
    urb_rur = df_serie.loc[
        df_serie["dominio"].isin(["Urbano", "Rural"])
        & df_serie["indicador"].isin(["Empleo Adecuado/Pleno", "Sector informal"])
    ]
    rural_fin = (
        urb_rur.loc[urb_rur["dominio"].eq("Rural") & urb_rur["anio"].eq(anio_fin)]
        .set_index("indicador")["valor_pct"]
    )
    for (ind, dom), g in urb_rur.groupby(["indicador", "dominio"]):
        g = g.sort_values("anio")
        color = PALETA["informal"] if ind == "Sector informal" else PALETA["adecuado"]
        ls = "-" if dom == "Rural" else "--"
        mk = "o" if dom == "Rural" else "s"
        etiqueta = f"{ind} ({dom})"
        ax2.plot(g["anio"], g["valor_pct"], linestyle=ls, marker=mk, color=color, linewidth=2.1, label=etiqueta)
        ax2.text(
            g["anio"].iloc[-1] + 0.12,
            g["valor_pct"].iloc[-1],
            f"{g['valor_pct'].iloc[-1]:.1f}%",
            va="center",
            fontsize=8.5,
            color=color,
        )

    ax2.set_xlim(2017.8, 2025.9)
    ax2.set_ylim(10, 86)
    ax2.set_xlabel("Año (ENEMDU Anual)")
    ax2.set_ylabel("Porcentaje (%)")
    ax2.set_title("Fractura territorial: Urbano vs. Rural (2018–2025)", loc="left", pad=16)
    ax2.text(
        0,
        1.02,
        f"Rural {anio_fin}: {_num(rural_fin['Sector informal'])}% en el sector informal y "
        f"{_num(rural_fin['Empleo Adecuado/Pleno'])}% con empleo adecuado",
        transform=ax2.transAxes,
        fontsize=9,
        color="#4b5563",
    )
    ax2.legend(loc="upper left", ncol=2, fontsize=8.0, frameon=True)

    plt.tight_layout()
    ruta = dir_figuras / "02_evolucion_mercado_laboral_2018_2025.png"
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def fig_03_radiografia_provincial_informalidad_adecuado(
    df_prov: pd.DataFrame,
    dir_figuras: Path = DIR_FIGURAS,
) -> Path:
    """Muestra las 24 provincias por empleo adecuado (IC 95%) y cruce con informalidad."""
    configurar_estilo()
    sub = df_prov.sort_values("empleo_adecuado_pct", ascending=True).reset_index(drop=True)
    alto1, alto2 = sub.iloc[-1], sub.iloc[-2]
    bajo1, bajo2 = sub.iloc[0], sub.iloc[1]

    colores_reg = {
        "Sierra": PALETA["primario"],
        "Costa": PALETA["acento"],
        "Amazonía": PALETA["exito"],
        "Insular": "#8e44ad",
    }

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15.0, 7.2))
    y = np.arange(len(sub))
    c_barras = [colores_reg.get(r, PALETA["gris"]) for r in sub["region_natural"]]

    ax1.barh(
        y,
        sub["empleo_adecuado_pct"],
        xerr=1.96 * sub["empleo_adecuado_ee_pct"],
        height=0.68,
        color=c_barras,
        alpha=0.88,
        error_kw={"ecolor": "#374151", "lw": 1.0, "capsize": 2.5},
    )
    ax1.set_yticks(y)
    ax1.set_yticklabels(sub["provincia"], fontsize=8.8)
    ax1.set_xlabel("Tasa de empleo adecuado / pleno (% de la PEA)")
    ax1.set_xlim(0, 72)
    ax1.set_title("Empleo adecuado en las 24 provincias (IC 95 % complejo)", loc="left", pad=16)
    ax1.text(
        0,
        1.015,
        f"{alto1['provincia']} ({_num(alto1['empleo_adecuado_pct'])}%) y {alto2['provincia']} "
        f"({_num(alto2['empleo_adecuado_pct'])}%) frente a {bajo2['provincia']} "
        f"({_num(bajo2['empleo_adecuado_pct'])}%) y {bajo1['provincia']} ({_num(bajo1['empleo_adecuado_pct'])}%)",
        transform=ax1.transAxes,
        fontsize=8.8,
        color="#4b5563",
    )

    for i, r in sub.iterrows():
        ax1.text(
            r["empleo_adecuado_pct"] + 1.96 * r["empleo_adecuado_ee_pct"] + 0.8,
            i,
            f"{r['empleo_adecuado_pct']:.1f}%",
            va="center",
            fontsize=7.8,
            color="#1f2937",
        )

    # Panel derecho: Informalidad (%) vs Pobreza por ingresos (%) por provincia
    for reg, grp in sub.groupby("region_natural"):
        tam = np.clip(np.sqrt(grp["pea_expandida"]) * 0.22, 45, 380)
        ax2.scatter(
            grp["informalidad_pct"],
            grp["pobreza_pct"],
            s=tam,
            color=colores_reg.get(reg, PALETA["gris"]),
            alpha=0.82,
            edgecolors="white",
            linewidth=1.0,
            label=reg,
        )

    # Recta de tendencia MCO entre provincias
    m_lin, b_lin = np.polyfit(sub["informalidad_pct"], sub["pobreza_pct"], 1)
    xs = np.linspace(sub["informalidad_pct"].min() - 2, sub["informalidad_pct"].max() + 2, 50)
    corr = np.corrcoef(sub["informalidad_pct"], sub["pobreza_pct"])[0, 1]
    ax2.plot(xs, m_lin * xs + b_lin, "--", color="#6b7280", linewidth=1.3, label=f"Tendencia (r = {corr:.2f})")

    destacar = {
        "Pichincha": (1.2, -1.8),
        "Guayas": (1.2, 1.0),
        "Azuay": (1.2, -1.5),
        "Galápagos": (1.5, 1.0),
        "Morona Santiago": (-14.0, 1.5),
        "Pastaza": (-10.0, -2.5),
        "Napo": (-8.0, 1.8),
        "Esmeraldas": (1.2, 1.2),
        "Chimborazo": (2.0, -4.0),
        "Manabí": (1.2, 1.0),
        "Bolívar": (-9.0, 1.4),
    }
    for _, fila in sub.iterrows():
        nom = fila["provincia"]
        if nom in destacar:
            dx, dy = destacar[nom]
            ax2.annotate(
                nom,
                (fila["informalidad_pct"], fila["pobreza_pct"]),
                xytext=(fila["informalidad_pct"] + dx, fila["pobreza_pct"] + dy),
                fontsize=8.2,
                color="#1f2937",
                # Línea guía para que cada etiqueta quede unida a su provincia
                arrowprops={"arrowstyle": "-", "color": "#9ca3af", "lw": 0.7},
            )

    ax2.set_ylim(bottom=-3)
    ax2.set_xlabel("Ocupados en el sector informal (%)")
    ax2.set_ylabel("Tasa de pobreza por ingresos (%)")
    ax2.set_title("Informalidad laboral vs. pobreza por ingresos provincial", loc="left", pad=16)
    ax2.text(
        0,
        1.015,
        f"Correlación entre provincias r = {_num(corr, 2)} · cada punto es una provincia (tamaño = PEA)",
        transform=ax2.transAxes,
        fontsize=8.8,
        color="#4b5563",
    )
    ax2.legend(loc="upper left", frameon=True, fontsize=8.5)

    plt.tight_layout()
    ruta = dir_figuras / "03_radiografia_provincial_informalidad_adecuado.png"
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def fig_04_brechas_demograficas_etnia_educacion(
    df_subgrupos: pd.DataFrame,
    dir_figuras: Path = DIR_FIGURAS,
) -> Path:
    """Gráfico de barras apiladas de composición de la PEA por etnia y por nivel educativo."""
    configurar_estilo()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.6, 5.6))

    componentes = [
        ("empleo_adecuado_pct", "Empleo adecuado", PALETA["adecuado"]),
        ("subempleo_pct", "Subempleo", PALETA["subempleo"]),
        ("otro_no_pleno_pct", "Otro no pleno", PALETA["otro_no_pleno"]),
        ("no_remunerado_pct", "No remunerado", PALETA["no_remunerado"]),
        ("desempleo_pct", "Desempleo", PALETA["desempleo"]),
    ]

    def _dibujar_apiladas(ax: Any, df_dim: pd.DataFrame, titulo: str, subtitulo: str) -> None:
        y = np.arange(len(df_dim))
        acum = np.zeros(len(df_dim))
        for col, etiq, color in componentes:
            vals = df_dim[col].to_numpy()
            ax.barh(y, vals, left=acum, height=0.56, color=color, label=etiq)
            for i, (v, izq) in enumerate(zip(vals, acum)):
                if v >= 7.5:
                    ax.text(
                        izq + v / 2,
                        i,
                        f"{v:.1f}%",
                        ha="center",
                        va="center",
                        color="white" if col in ("empleo_adecuado_pct", "no_remunerado_pct", "desempleo_pct") else "#1f2937",
                        fontsize=8.2,
                        fontweight="bold",
                    )
            acum += vals
        ax.set_yticks(y)
        ax.set_yticklabels(df_dim["categoria"], fontsize=9.2)
        ax.invert_yaxis()
        ax.set_xlim(0, 102)
        ax.set_xlabel("Composición de la PEA (%)")
        ax.set_title(titulo, loc="left", pad=16)
        ax.text(0, 1.02, subtitulo, transform=ax.transAxes, fontsize=8.8, color="#4b5563")

    etn = (
        df_subgrupos.loc[df_subgrupos["dimension"] == "Autoidentificación étnica"]
        .sort_values("empleo_adecuado_pct", ascending=False)
        .reset_index(drop=True)
    )
    indig = etn.set_index("categoria").loc["Indígena"]
    _dibujar_apiladas(
        ax1,
        etn,
        "Composición de la PEA por autoidentificación étnica",
        f"En la PEA indígena el empleo no remunerado es {_num(indig['no_remunerado_pct'])}% "
        f"y el adecuado {_num(indig['empleo_adecuado_pct'])}%",
    )

    orden_edu = [
        "Superior",
        "Educación Media / Bachillerato",
        "Educación Básica",
        "Centro de alfabetización",
        "Ninguno",
    ]
    edu = df_subgrupos.loc[df_subgrupos["dimension"] == "Nivel de instrucción"].copy()
    edu = edu.set_index("categoria").reindex([x for x in orden_edu if x in edu["categoria"].values]).reset_index()
    adec_sup = float(edu.set_index("categoria").loc["Superior", "empleo_adecuado_pct"])
    adec_bas = float(edu.set_index("categoria").loc["Educación Básica", "empleo_adecuado_pct"])
    _dibujar_apiladas(
        ax2,
        edu,
        "Composición de la PEA por nivel de instrucción",
        f"Empleo adecuado: {_num(adec_sup)}% con educación superior vs. {_num(adec_bas)}% con "
        f"educación básica ({_num(adec_sup / adec_bas)} veces)",
    )
    ax2.legend(loc="lower center", bbox_to_anchor=(-0.1, -0.24), ncol=5, frameon=True, fontsize=9)

    plt.tight_layout()
    ruta = dir_figuras / "04_brechas_demograficas_etnia_educacion.png"
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def fig_05_ramas_actividad_informalidad_ingresos(
    df_ramas: pd.DataFrame,
    dir_figuras: Path = DIR_FIGURAS,
) -> Path:
    """Compara las principales ramas de actividad CIIU por informalidad e ingreso mediano."""
    configurar_estilo()
    sub = df_ramas.head(10).sort_values("informalidad_pct", ascending=True).reset_index(drop=True)
    nombres_cortos = {
        "Agricultura, ganadería, caza y silvicultura y pesca": "Agricultura, ganadería y pesca",
        "Comercio al por mayor y al por menor; reparación de vehículos": "Comercio y reparación vehículos",
        "Industrias manufactureras": "Industria manufacturera",
        "Actividades de alojamiento y de servicio de comidas": "Alojamiento y comidas",
        "Transporte y almacenamiento": "Transporte y almacenamiento",
        "Construcción": "Construcción",
        "Enseñanza": "Enseñanza",
        "Administración pública y defensa; planes de seguridad social": "Administración pública y defensa",
        "Actividades de atención de la salud humana y asistencia social": "Salud humana y asistencia social",
        "Actividades profesionales, científicas y técnicas": "Servicios profesionales y técnicos",
        "Otras actividades de servicios": "Otras actividades de servicios",
        "Actividades de servicios administrativos y de apoyo": "Servicios administrativos y apoyo",
        "Actividades de los hogares como empleadores": "Hogares como empleadores (doméstico)",
    }
    sub["etiqueta"] = sub["rama_nombre"].map(lambda x: nombres_cortos.get(x, x[:34]))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.6, 5.6), sharey=True)
    y = np.arange(len(sub))

    b1 = ax1.barh(y, sub["informalidad_pct"], height=0.6, color=PALETA["informal"], alpha=0.88)
    ax1.set_yticks(y)
    ax1.set_yticklabels(sub["etiqueta"], fontsize=9.2)
    ax1.set_xlabel("Ocupados en el sector informal (%)")
    ax1.set_xlim(0, 95)
    ax1.set_title("Tasa de informalidad en las 10 mayores ramas CIIU", loc="left", pad=16)
    ax1.text(
        0,
        1.02,
        f"{sub['etiqueta'].iloc[-1]} ({_num(sub['informalidad_pct'].iloc[-1])}%) y "
        f"{sub['etiqueta'].iloc[-2]} ({_num(sub['informalidad_pct'].iloc[-2])}%) concentran la mayor informalidad",
        transform=ax1.transAxes,
        fontsize=8.8,
        color="#4b5563",
    )
    for rect, part in zip(b1, sub["participacion_ocupados_pct"]):
        w = rect.get_width()
        ax1.text(
            w + 1.0,
            rect.get_y() + rect.get_height() / 2,
            f"{w:.1f}% ({part:.1f}% del empleo)",
            va="center",
            fontsize=8.2,
            color="#1f2937",
        )

    b2 = ax2.barh(y, sub["ingreso_mediano_usd"], height=0.6, color=PALETA["primario"], alpha=0.88)
    ax2.axvline(
        SBU_USD_2025,
        color=PALETA["alerta"],
        linestyle="--",
        linewidth=1.3,
        label=f"SBU 2025 ({SBU_USD_2025:.0f} USD)",
    )
    ax2.set_xlabel("Ingreso laboral mensual mediano (USD)")
    ax2.set_xlim(0, max(sub["ingreso_mediano_usd"]) * 1.25)
    ax2.set_title("Ingreso mensual mediano por rama de actividad (USD)", loc="left", pad=16)
    ax2.text(
        0,
        1.02,
        "Las ramas de alta informalidad operan muy por debajo del Salario Básico Unificado",
        transform=ax2.transAxes,
        fontsize=8.8,
        color="#4b5563",
    )
    ax2.legend(loc="lower right", frameon=True, fontsize=8.5)
    for rect in b2:
        w = rect.get_width()
        ax2.text(
            w + 12,
            rect.get_y() + rect.get_height() / 2,
            f"{w:.0f} USD",
            va="center",
            fontsize=8.2,
            color="#1f2937",
        )

    plt.tight_layout()
    ruta = dir_figuras / "05_ramas_actividad_informalidad_ingresos.png"
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def fig_06_distribucion_ingresos_y_sbu(
    df: pd.DataFrame,
    res_ingresos_sector: dict[str, dict[str, float]],
    dir_figuras: Path = DIR_FIGURAS,
) -> Path:
    """Histograma ponderado del ingreso laboral mensual en sector formal vs informal y anclaje en el SBU."""
    configurar_estilo()
    ocup = df.loc[
        df["empleo_ind"].eq(1) & df["ingrl_positivo"].notna() & (df["ingrl_positivo"] <= 2000)
    ].copy()
    for_df = ocup.loc[ocup["formal"].eq(1)]
    inf_df = ocup.loc[ocup["informal"].eq(1)]
    for_res = res_ingresos_sector["sector_formal"]
    inf_res = res_ingresos_sector["sector_informal"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 5.4))
    bins = np.arange(0, 1650, 50)

    ax1.hist(
        inf_df["ingrl_positivo"],
        bins=bins,
        weights=inf_df["fexp"] / inf_df["fexp"].sum() * 100.0,
        color=PALETA["informal"],
        alpha=0.62,
        edgecolor="white",
        label="Sector informal",
    )
    ax1.hist(
        for_df["ingrl_positivo"],
        bins=bins,
        weights=for_df["fexp"] / for_df["fexp"].sum() * 100.0,
        color=PALETA["formal"],
        alpha=0.65,
        edgecolor="white",
        label="Sector formal",
    )
    ax1.axvline(
        SBU_USD_2025,
        color=PALETA["alerta"],
        linestyle="--",
        linewidth=1.6,
        label=f"SBU 2025 = {SBU_USD_2025:.0f} USD",
    )
    ax1.set_xlabel("Ingreso laboral mensual (USD, truncado a 1.600 USD para visualización)")
    ax1.set_ylabel("Porcentaje de ocupados dentro de cada sector (%)")
    ax1.set_title("Efecto faro / agrupamiento en el Salario Básico Unificado", loc="left", pad=16)
    ax1.text(
        0,
        1.02,
        f"Sector informal: el {_num(inf_res['bajo_sbu_pct'], 0)}% gana menos del SBU; en el formal "
        f"la distribución se ancla en {SBU_USD_2025:.0f} USD",
        transform=ax1.transAxes,
        fontsize=8.8,
        color="#4b5563",
    )
    ax1.legend(loc="upper right", frameon=True, fontsize=8.8)

    # Panel derecho: CDF ponderada (función de distribución acumulada)
    rejilla = np.linspace(0, 1600, 161)
    for sub_s, etiq, col in [
        (inf_df, "Sector informal", PALETA["informal"]),
        (for_df, "Sector formal", PALETA["formal"]),
    ]:
        vals = sub_s["ingrl_positivo"].to_numpy()
        w = sub_s["fexp"].to_numpy()
        orden = np.argsort(vals)
        vals = vals[orden]
        w = w[orden]
        cdf = np.interp(rejilla, vals, np.cumsum(w) / np.sum(w)) * 100.0
        ax2.plot(rejilla, cdf, color=col, linewidth=2.4, label=etiq)

    ax2.axvline(SBU_USD_2025, color=PALETA["alerta"], linestyle="--", linewidth=1.4, label="SBU (470 USD)")
    ax2.axhline(50.0, color="#9ca3af", linestyle=":", linewidth=1.0)
    ax2.set_xlabel("Ingreso laboral mensual (USD)")
    ax2.set_ylabel("Ocupados acumulados (%)")
    ax2.set_ylim(0, 102)
    ax2.set_title("Curva de distribución acumulada por sector (CDF ponderada)", loc="left", pad=16)
    ax2.text(
        0,
        1.02,
        f"Mediana ponderada: {_num(inf_res['ingreso_mediano_usd'], 0)} USD en el sector informal vs. "
        f"{_num(for_res['ingreso_mediano_usd'], 0)} USD en el formal",
        transform=ax2.transAxes,
        fontsize=8.8,
        color="#4b5563",
    )
    ax2.legend(loc="lower right", frameon=True, fontsize=8.8)

    plt.tight_layout()
    ruta = dir_figuras / "06_distribucion_ingresos_y_sbu.png"
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def fig_07_ecuacion_mincer_y_efecto_diploma(
    res_mincer: dict[str, Any],
    dir_figuras: Path = DIR_FIGURAS,
) -> Path:
    """Visualiza el retorno por año de escolaridad y el efecto diploma por nivel educativo."""
    configurar_estilo()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.6, 5.6))

    df_perf = pd.DataFrame(res_mincer["perfil_escolaridad_sector"])
    for sec, col, mk in [
        ("Formal", PALETA["formal"], "o-"),
        ("Informal", PALETA["informal"], "s--"),
    ]:
        g = df_perf.loc[df_perf["sector_bin"] == sec].sort_values("esc_redondeada")
        ax1.plot(
            g["esc_redondeada"],
            g["salario_hora_medio"],
            mk,
            color=col,
            linewidth=2.3,
            markersize=5.5,
            label=f"Sector {sec.lower()}",
        )

    b_m1 = res_mincer["modelos"]["m1_base"]["coeficientes"]["escolaridad"]["efecto_porcentual"]
    b_m2 = res_mincer["modelos"]["m2_formalidad"]["coeficientes"]["escolaridad"]["efecto_porcentual"]
    b_m3 = res_mincer["modelos"]["m3_completo"]["coeficientes"]["escolaridad"]["efecto_porcentual"]

    ax1.set_xlabel("Años de escolaridad aprobados")
    ax1.set_ylabel("Salario medio por hora trabajada (USD/hora)")
    ax1.set_title("Retorno salarial de la educación según formalidad (Mincer)", loc="left", pad=16)
    ax1.text(
        0,
        1.02,
        f"Retorno por año: +{_num(b_m1)}% bruto (M1) → +{_num(b_m2)}% controlando formalidad/IESS (M2) → +{_num(b_m3)}% con EF (M3)",
        transform=ax1.transAxes,
        fontsize=8.6,
        color="#4b5563",
    )
    ax1.legend(loc="upper left", frameon=True, fontsize=9)

    # Panel derecho: Efecto diploma
    df_dip = pd.DataFrame(res_mincer["efecto_diploma"]).iloc[1:].reset_index(drop=True)
    y = np.arange(len(df_dip))
    err_inf = df_dip["premio_salarial_pct"] - df_dip["ic95_inf_pct"]
    err_sup = df_dip["ic95_sup_pct"] - df_dip["premio_salarial_pct"]

    barras = ax2.barh(
        y,
        df_dip["premio_salarial_pct"],
        xerr=[err_inf, err_sup],
        height=0.55,
        color=PALETA["primario"],
        alpha=0.88,
        error_kw={"ecolor": "#374151", "lw": 1.1, "capsize": 3},
    )
    ax2.set_yticks(y)
    ax2.set_yticklabels(df_dip["nivel"], fontsize=9.2)
    ax2.set_xlabel("Premio salarial por hora frente a sin instrucción (%, neto de formalidad)")
    ax2.set_xlim(0, max(df_dip["ic95_sup_pct"]) * 1.22)
    ax2.set_title("Efecto diploma: convexidad de los retornos educativos", loc="left", pad=16)
    ax2.text(
        0,
        1.02,
        "El salto salarial se concentra en el título universitario y el posgrado (controlando edad, sexo, área y sector)",
        transform=ax2.transAxes,
        fontsize=8.6,
        color="#4b5563",
    )
    for rect, fila in zip(barras, df_dip.to_dict(orient="records")):
        w = rect.get_width()
        ax2.text(
            fila["ic95_sup_pct"] + 2.0,
            rect.get_y() + rect.get_height() / 2,
            f"+{w:.1f}%",
            va="center",
            fontsize=8.8,
            fontweight="bold",
            color="#1f2937",
        )

    plt.tight_layout()
    ruta = dir_figuras / "07_ecuacion_mincer_y_efecto_diploma.png"
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def fig_08_oaxaca_blinder_brecha_genero(
    res_oaxaca: dict[str, Any],
    dir_figuras: Path = DIR_FIGURAS,
) -> Path:
    """Muestra la descomposición de Kitagawa-Oaxaca-Blinder de la brecha salarial por hora."""
    configurar_estilo()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.6, 5.6))

    desc = res_oaxaca["descriptivos_ocupados"]
    oax = res_oaxaca["resumen_oaxaca"]

    etiquetas_res = [
        "Brecha mensual bruta\n(incluye diferencia de horas)",
        "Brecha por hora bruta\n(log salario/hora × 100)",
        "Efecto dotaciones\n(explicado por capital humano)",
        "Efecto estructura / retornos\n(no explicado: brecha ajustada)",
    ]
    valores_res = [
        desc["brecha_mensual_bruta_pct"],
        oax["brecha_log_total"] * 100.0,
        oax["dotaciones_explicada_log"] * 100.0,
        oax["retornos_no_explicada_log"] * 100.0,
    ]
    colores_res = [
        PALETA["gris"],
        PALETA["primario"],
        PALETA["exito"],
        PALETA["mujer"],
    ]

    y1 = np.arange(len(etiquetas_res))
    b1 = ax1.barh(y1, valores_res, height=0.52, color=colores_res, alpha=0.9)
    ax1.axvline(0.0, color="#374151", linewidth=1.0)
    ax1.set_yticks(y1)
    ax1.set_yticklabels(etiquetas_res, fontsize=9.0)
    ax1.invert_yaxis()
    ax1.set_xlabel("Diferencia Hombre − Mujer (puntos logarítmicos / %)")
    min_x = min(valores_res) - 8
    max_x = max(valores_res) + 9
    ax1.set_xlim(min_x, max_x)
    ax1.set_title("Descomposición de Kitagawa-Oaxaca-Blinder (Hombre − Mujer)", loc="left", pad=16)
    ax1.text(
        0,
        1.02,
        f"Las mujeres ocupadas tienen más escolaridad ({_num(desc['escolaridad_media_mujer'])} vs {_num(desc['escolaridad_media_hombre'])} años): dotaciones negativas",
        transform=ax1.transAxes,
        fontsize=8.6,
        color="#4b5563",
    )

    for rect, v in zip(b1, valores_res):
        offset = 0.7 if v >= 0 else -0.7
        ha = "left" if v >= 0 else "right"
        ax1.text(
            v + offset,
            rect.get_y() + rect.get_height() / 2,
            f"{v:+.1f}%",
            va="center",
            ha=ha,
            fontsize=8.8,
            fontweight="bold",
            color="#1f2937",
        )

    # Panel derecho: contribución al efecto dotaciones por factor
    df_comp = pd.DataFrame(res_oaxaca["componentes"])
    df_comp = df_comp.loc[df_comp["componente"] != "Constante (brecha base inobservada)"].copy()
    y2 = np.arange(len(df_comp))
    vals_dot = df_comp["dotaciones_pct_aprox"].to_numpy()
    cols_dot = [PALETA["exito"] if v < 0 else PALETA["acento"] for v in vals_dot]

    b2 = ax2.barh(y2, vals_dot, height=0.52, color=cols_dot, alpha=0.88)
    ax2.axvline(0.0, color="#374151", linewidth=1.0)
    ax2.set_yticks(y2)
    ax2.set_yticklabels(df_comp["componente"], fontsize=9.0)
    ax2.invert_yaxis()
    ax2.set_xlabel("Contribución a la brecha explicada por dotaciones (puntos %)")
    ax2.set_xlim(min(vals_dot) - 4.5, max(vals_dot) + 4.5)
    ax2.set_title("¿Qué explica el efecto dotaciones? Desglose por factor", loc="left", pad=16)
    ax2.text(
        0,
        1.02,
        "Valores negativos indican que las mujeres ocupadas tienen mejores dotaciones observables que los hombres",
        transform=ax2.transAxes,
        fontsize=8.6,
        color="#4b5563",
    )
    for rect, v in zip(b2, vals_dot):
        offset = 0.25 if v >= 0 else -0.25
        ha = "left" if v >= 0 else "right"
        ax2.text(
            v + offset,
            rect.get_y() + rect.get_height() / 2,
            f"{v:+.2f} pp",
            va="center",
            ha=ha,
            fontsize=8.5,
            color="#1f2937",
        )

    plt.tight_layout()
    ruta = dir_figuras / "08_oaxaca_blinder_brecha_genero.png"
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def fig_09_brecha_cuantilica_piso_pegajoso_techo_cristal(
    df_cuantiles: pd.DataFrame,
    dir_figuras: Path = DIR_FIGURAS,
) -> Path:
    """Muestra la brecha salarial por cuantiles (piso pegajoso informal vs SBU formal)."""
    configurar_estilo()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 5.4))

    cfg = [
        ("Sector informal", PALETA["informal"], "o-", 2.4),
        ("Sector formal", PALETA["formal"], "s-", 2.4),
        ("Total ocupados", PALETA["gris"], "^--", 1.8),
    ]
    for sec, col, est, lw in cfg:
        g = df_cuantiles.loc[df_cuantiles["sector"] == sec].sort_values("percentil")
        ax1.plot(
            g["percentil"],
            g["brecha_hora_pct"],
            est,
            color=col,
            linewidth=lw,
            markersize=6,
            label=sec,
        )
        ax2.plot(
            g["percentil"],
            g["brecha_mensual_pct"],
            est,
            color=col,
            linewidth=lw,
            markersize=6,
            label=sec,
        )

    inf_q = df_cuantiles.loc[df_cuantiles["sector"] == "Sector informal"].set_index("percentil").sort_index()
    for_q = df_cuantiles.loc[df_cuantiles["sector"] == "Sector formal"].set_index("percentil").sort_index()
    ax1.axhline(0.0, color="#374151", linewidth=0.9, linestyle=":")
    ax1.set_xlabel("Percentil de la distribución salarial (P10 a P90)")
    ax1.set_ylabel("Brecha salarial por hora Hombre − Mujer (%)")
    ax1.set_title("Brecha de salario por hora a lo largo de los cuantiles", loc="left", pad=16)
    ax1.text(
        0,
        1.02,
        f"Informal: brecha por hora de {_num(inf_q.loc[10, 'brecha_hora_pct'])}% en P10 · formal: "
        f"{_num(for_q.loc[50, 'brecha_hora_pct'])}% en la mediana (compresión por el SBU)",
        transform=ax1.transAxes,
        fontsize=8.6,
        color="#4b5563",
    )
    ax1.legend(loc="upper right", frameon=True, fontsize=8.8)

    ax2.axhline(0.0, color="#374151", linewidth=0.9, linestyle=":")
    ax2.set_xlabel("Percentil de la distribución de ingresos (P10 a P90)")
    ax2.set_ylabel("Brecha de ingreso mensual Hombre − Mujer (%)")
    ax2.set_title("Brecha de ingreso laboral mensual por cuantiles", loc="left", pad=16)
    ax2.text(
        0,
        1.02,
        f"Brecha mensual informal entre {_num(inf_q.loc[:50, 'brecha_mensual_pct'].min())}% y "
        f"{_num(inf_q.loc[:50, 'brecha_mensual_pct'].max())}% hasta la mediana (incluye menos horas remuneradas)",
        transform=ax2.transAxes,
        fontsize=8.6,
        color="#4b5563",
    )
    ax2.legend(loc="upper right", frameon=True, fontsize=8.8)

    plt.tight_layout()
    ruta = dir_figuras / "09_brecha_cuantilica_piso_pegajoso_techo_cristal.png"
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def fig_10_curva_lorenz_y_pobreza_laboral(
    res_desig: dict[str, Any],
    dir_figuras: Path = DIR_FIGURAS,
) -> Path:
    """Dibuja las curvas de Lorenz ponderadas y la tasa de pobreza según inserción laboral."""
    configurar_estilo()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.6, 5.6))

    df_lor_pc = pd.DataFrame(res_desig["curva_lorenz_ingpc"])
    df_lor_lab = pd.DataFrame(res_desig["curva_lorenz_laboral"])
    gini_pc = res_desig["ingreso_per_capita_hogar"]["gini"]
    palma_pc = res_desig["ingreso_per_capita_hogar"]["indice_palma"]
    gini_lab = res_desig["ingreso_laboral_ocupados"]["gini"]

    ax1.plot(
        df_lor_pc["poblacion_acum_pct"],
        df_lor_pc["igualdad_pct"],
        "--",
        color="#6b7280",
        linewidth=1.3,
        label="Línea de equidistribución (Gini = 0)",
    )
    ax1.plot(
        df_lor_pc["poblacion_acum_pct"],
        df_lor_pc["ingreso_acum_pct"],
        color=PALETA["primario"],
        linewidth=2.5,
        label=f"Ingreso per cápita hogar (Gini = {gini_pc:.3f} · Palma = {palma_pc:.2f})",
    )
    ax1.plot(
        df_lor_lab["poblacion_acum_pct"],
        df_lor_lab["ingreso_acum_pct"],
        color=PALETA["acento"],
        linewidth=2.2,
        linestyle="-.",
        label=f"Ingreso laboral ocupados (Gini = {gini_lab:.3f})",
    )
    ax1.fill_between(
        df_lor_pc["poblacion_acum_pct"],
        df_lor_pc["ingreso_acum_pct"],
        df_lor_pc["igualdad_pct"],
        color=PALETA["primario"],
        alpha=0.10,
    )
    ax1.set_xlim(0, 100)
    ax1.set_ylim(0, 100)
    ax1.set_xlabel("Población acumulada (%)")
    ax1.set_ylabel("Ingreso acumulado (%)")
    ax1.set_title("Curvas de Lorenz ponderadas en el Ecuador (ENEMDU 2025)", loc="left", pad=16)
    d10 = res_desig["ingreso_per_capita_hogar"]["participacion_d10_pct"]
    d1_4 = res_desig["ingreso_per_capita_hogar"]["participacion_d1_a_d4_pct"]
    ax1.text(
        0,
        1.02,
        f"El 10% más rico concentra el {_num(d10)}% del ingreso frente al {_num(d1_4)}% del 40% más pobre",
        transform=ax1.transAxes,
        fontsize=8.8,
        color="#4b5563",
    )
    ax1.legend(loc="upper left", frameon=True, fontsize=8.5)

    # Panel derecho: Pobreza y pobreza extrema por condición laboral
    df_pob = pd.DataFrame(res_desig["pobreza_por_condicion_laboral"])
    y = np.arange(len(df_pob))
    h = 0.38

    b_pob = ax2.barh(
        y + h / 2,
        df_pob["pobreza_pct"],
        xerr=1.96 * df_pob["pobreza_ee_pct"],
        height=h,
        color=PALETA["acento"],
        alpha=0.9,
        label="Pobreza por ingresos",
        error_kw={"ecolor": "#374151", "lw": 1.0, "capsize": 2.5},
    )
    ax2.barh(
        y - h / 2,
        df_pob["pobreza_extrema_pct"],
        height=h,
        color=PALETA["alerta"],
        alpha=0.85,
        label="Pobreza extrema",
    )
    ax2.set_yticks(y)
    ax2.set_yticklabels(df_pob["condicion_laboral"], fontsize=9.0)
    ax2.invert_yaxis()
    ax2.set_xlabel("Incidencia en la PEA (% de personas en hogares pobres)")
    ax2.set_xlim(0, max(df_pob["pobreza_ic95_sup"]) * 1.22)
    ax2.set_title("Pobreza según condición de actividad y sector laboral", loc="left", pad=16)
    pob_cond = df_pob.set_index("condicion_laboral")["pobreza_pct"]
    ax2.text(
        0,
        1.02,
        f"En el empleo adecuado la pobreza es {_num(pob_cond['Empleo adecuado/pleno'])}% vs "
        f"{_num(pob_cond['Sector informal (ocupados)'])}% en el sector informal",
        transform=ax2.transAxes,
        fontsize=8.8,
        color="#4b5563",
    )
    ax2.legend(loc="upper right", frameon=True, fontsize=8.8)

    for rect, fila in zip(b_pob, df_pob.to_dict(orient="records")):
        ax2.text(
            fila["pobreza_ic95_sup"] + 0.8,
            rect.get_y() + rect.get_height() / 2,
            f"{fila['pobreza_pct']:.1f}% (ext. {fila['pobreza_extrema_pct']:.1f}%)",
            va="center",
            fontsize=8.2,
            color="#1f2937",
        )

    plt.tight_layout()
    ruta = dir_figuras / "10_curva_lorenz_y_pobreza_laboral.png"
    fig.savefig(ruta)
    plt.close(fig)
    return ruta


def generar_todas_las_figuras(
    df: pd.DataFrame,
    df_reconciliacion: pd.DataFrame,
    df_serie: pd.DataFrame,
    df_prov: pd.DataFrame,
    df_subgrupos: pd.DataFrame,
    df_ramas: pd.DataFrame,
    res_ingresos_sector: dict[str, dict[str, float]],
    res_mincer: dict[str, Any],
    res_oaxaca: dict[str, Any],
    df_cuantiles: pd.DataFrame,
    res_desig: dict[str, Any],
    *,
    dir_figuras: Path = DIR_FIGURAS,
) -> list[str]:
    """Genera las 10 figuras del estudio y devuelve sus rutas.

    Todos los subtítulos con cifras se construyen a partir de los datos recibidos,
    de modo que no puedan quedar desfasados respecto a reports/.
    """
    dir_figuras.mkdir(parents=True, exist_ok=True)
    rutas = [
        fig_01_diseno_muestral_y_reconciliacion(df_reconciliacion, dir_figuras),
        fig_02_evolucion_mercado_laboral_2018_2025(df_serie, dir_figuras),
        fig_03_radiografia_provincial_informalidad_adecuado(df_prov, dir_figuras),
        fig_04_brechas_demograficas_etnia_educacion(df_subgrupos, dir_figuras),
        fig_05_ramas_actividad_informalidad_ingresos(df_ramas, dir_figuras),
        fig_06_distribucion_ingresos_y_sbu(df, res_ingresos_sector, dir_figuras),
        fig_07_ecuacion_mincer_y_efecto_diploma(res_mincer, dir_figuras),
        fig_08_oaxaca_blinder_brecha_genero(res_oaxaca, dir_figuras),
        fig_09_brecha_cuantilica_piso_pegajoso_techo_cristal(df_cuantiles, dir_figuras),
        fig_10_curva_lorenz_y_pobreza_laboral(res_desig, dir_figuras),
    ]
    return [str(r) for r in rutas]
