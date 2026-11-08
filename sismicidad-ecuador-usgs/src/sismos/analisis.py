"""Cada paso del análisis como una función que devuelve tablas y cifras (las usan el pipeline y los notebooks)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config
from . import gutenberg_richter as gr
from . import omori
from . import retorno
from .calidad import asignar_zona
from .desagrupar import gardner_knopoff


def anios_catalogo(anio_inicio: int, anio_fin: int = config.ANIO_FIN) -> int:
    return anio_fin - anio_inicio + 1


# ---- 3 · Exploratorio ----------------------------------------------------------------------
def resumen_exploratorio(df: pd.DataFrame) -> dict:
    prof = df.loc[~df["profundidad_fija"], "clase_profundidad"].value_counts(normalize=True)
    por_anio = df.groupby("anio").size()
    return {
        "eventos": int(len(df)),
        "eventos_m5": int((df["mw"] >= 5).sum()),
        "eventos_m6": int((df["mw"] >= 6).sum()),
        "eventos_m7": int((df["mw"] >= 7).sum()),
        "anio_mas_activo": int(por_anio.idxmax()), "eventos_anio_mas_activo": int(por_anio.max()),
        "eventos_por_anio_mediana": float(por_anio.median()),
        "profundidad_mediana_km": float(df["profundidad_km"].median()),
        "pct_por_clase_profundidad_sin_fijas": {str(k): round(100 * v, 1) for k, v in prof.items()},
        "mayor": df.loc[df["mw"].idxmax(), ["id", "tiempo", "mw", "profundidad_km", "lugar"]]
                   .astype(str).to_dict(),
    }


def perfil_subduccion(df: pd.DataFrame, lat_min: float = -2.5, lat_max: float = 1.5) -> pd.DataFrame:
    """Eventos de una franja de latitud para el corte longitud–profundidad (profundidades no fijas)."""
    return df[df["latitud"].between(lat_min, lat_max) & ~df["profundidad_fija"]]


def pendiente_placa(df: pd.DataFrame, lat_min: float = -2.5, lat_max: float = 1.5) -> dict:
    """Ajuste lineal profundidad ~ distancia a la fosa (aprox. por longitud) para los eventos de la franja:
    da el ángulo medio de inclinación de la placa de Nazca bajo el Ecuador."""
    d = perfil_subduccion(df, lat_min, lat_max)
    d = d[d["profundidad_km"] > 40]           # quitar la corteza superior y el interplaca más somero
    km_por_grado = 111.32 * np.cos(np.radians((lat_min + lat_max) / 2))
    x = (d["longitud"] - d["longitud"].min()) * km_por_grado
    pendiente, _ = np.polyfit(x, d["profundidad_km"], 1)
    return {"n": int(len(d)), "km_profundidad_por_km": float(pendiente),
            "angulo_grados": float(np.degrees(np.arctan(pendiente)))}


# ---- 4 · Gutenberg-Richter -----------------------------------------------------------------
def ajuste_completo(m, anios: float, dm: float = config.DELTA_M) -> dict:
    """Mc por MAXC y por MBS; b de Aki (con IC analítico y bootstrap) y de mínimos cuadrados en ambos."""
    m = np.asarray(m, dtype=float)
    mc_maxc = gr.mc_maxc(m, dm, config.CORRECCION_MAXC)
    mc_media, mc_sd = gr.mc_bootstrap(m, dm, config.CORRECCION_MAXC, n_boot=200, semilla=config.SEMILLA)
    mc_mbs = gr.mc_mbs(m, dm)
    salida = {"n_total": int(len(m)), "anios": anios, "mc_maxc": mc_maxc, "mc_maxc_bootstrap_sd": round(mc_sd, 3),
              "mc_mbs": mc_mbs}
    for nombre, mc in (("maxc", mc_maxc), ("mbs", mc_mbs)):
        if mc is None:
            salida[nombre] = None
            continue
        aj = gr.valor_b_aki(m, mc, dm, anios=anios, n_boot=config.N_BOOTSTRAP, semilla=config.SEMILLA)
        b_mc, a_mc = gr.valor_b_minimos_cuadrados(m, mc, dm)
        salida[nombre] = {**aj.como_dict(), "b_minimos_cuadrados": round(b_mc, 4)}
    return salida


def comparar_cinturon(mundo: pd.DataFrame, zonas=config.ZONAS_CINTURON, mc_comun: float = 5.5) -> pd.DataFrame:
    """Valor b por zona del Cinturón con el catálogo global M≥5 (1973–2025), mismo método para todas:
    Mc propio por MBS y, para comparar en igualdad, b con un Mc común."""
    mundo = mundo.assign(zona=asignar_zona(mundo, zonas))
    anios = anios_catalogo(config.ANIO_INICIO_GLOBAL)
    filas = []
    for zona, g in mundo.dropna(subset=["zona"]).groupby("zona"):
        m = g["mw"].to_numpy()
        mc_maxc = gr.mc_maxc(m)
        mc_mbs = gr.mc_mbs(m) or mc_maxc
        propio = gr.valor_b_aki(m, mc_mbs, anios=anios, n_boot=config.N_BOOTSTRAP, semilla=config.SEMILLA)
        comun = gr.valor_b_aki(m, mc_comun, anios=anios, n_boot=config.N_BOOTSTRAP, semilla=config.SEMILLA)
        tasa7 = retorno.tasa_anual(7.0, comun.n / anios, comun.b, mc_comun)
        filas.append({
            "zona": zona, "eventos_m5": int(len(g)), "eventos_m7": int((g["mw"] >= 7).sum()),
            "pct_profundos_70km": round(100 * float((g["profundidad_km"] > 70).mean()), 1),
            "mc_maxc": mc_maxc, "mc_mbs": mc_mbs, "b_mc_propio": propio.b,
            "b_mc_propio_ic95_bajo": propio.ic95_bajo, "b_mc_propio_ic95_alto": propio.ic95_alto,
            "n_mc_propio": propio.n,
            "b_mc_comun": comun.b, "b_mc_comun_ic95_bajo": comun.ic95_bajo, "b_mc_comun_ic95_alto": comun.ic95_alto,
            "b_mc_comun_boot_bajo": comun.ic95_boot_bajo, "b_mc_comun_boot_alto": comun.ic95_boot_alto,
            "n_mc_comun": comun.n, "tasa_m7_gr": tasa7, "retorno_m7_gr_anios": 1 / tasa7,
            "tasa_m7_empirica": (g["mw"] >= 7).sum() / anios,
        })
    return pd.DataFrame(filas).sort_values("b_mc_comun").reset_index(drop=True)


# ---- 5 · Periodos de retorno ---------------------------------------------------------------
def periodos_retorno(df: pd.DataFrame, historico: pd.DataFrame, mc: float) -> dict:
    """Tasas de M≥6 y M≥7 en el Ecuador ampliado según Gutenberg-Richter (catálogo completo y
    desagrupado) frente a la línea base empírica (contar y dividir)."""
    anios = anios_catalogo(config.ANIO_INICIO_ECUADOR)
    principal = gardner_knopoff(df)
    salida = {"mc": mc, "anios": anios, "eventos_principales": int(principal.sum()),
              "pct_eliminados_desagrupar": round(100 * (1 - principal.mean()), 1)}
    for nombre, d in (("completo", df), ("desagrupado", df[principal])):
        salida[f"gr_{nombre}"] = retorno.retorno_con_incertidumbre(
            d["mw"].to_numpy(), mc, anios, objetivos=(6.0, 7.0), n_boot=config.N_BOOTSTRAP,
            semilla=config.SEMILLA)
        salida[f"b_{nombre}"] = gr.valor_b_aki(d["mw"], mc, anios=anios).como_dict()
    # Línea base empírica 1: el mismo catálogo 1970–2025, desagrupado
    salida["empirica_1970"] = {f"m{int(m)}": retorno.tasa_empirica(int((df.loc[principal, 'mw'] >= m).sum()), anios)
                               for m in (6.0, 7.0)}
    # Línea base empírica 2: M≥7 desde 1900 (catálogo histórico desagrupado), más largo pero menos preciso
    hist_pr = historico[gardner_knopoff(historico)]
    anios_h = anios_catalogo(config.ANIO_INICIO_HISTORICO)
    salida["empirica_1900_m7"] = retorno.tasa_empirica(int((hist_pr["mw"] >= 7).sum()), anios_h)
    salida["historico_m7"] = hist_pr.loc[hist_pr["mw"] >= 7, ["tiempo", "mw", "profundidad_km", "lugar"]] \
        .astype(str).to_dict("records")
    # Sismos superficiales (<70 km): los de la interfaz de subducción, como Pedernales, 1979 o 1906
    sup = df[principal & (df["profundidad_km"] < 70)]
    salida["gr_superficiales"] = retorno.retorno_con_incertidumbre(
        sup["mw"].to_numpy(), mc, anios, objetivos=(6.0, 7.0), n_boot=config.N_BOOTSTRAP, semilla=config.SEMILLA)
    salida["empirica_superficiales_1970"] = {f"m{int(m)}": retorno.tasa_empirica(int((sup["mw"] >= m).sum()), anios)
                                            for m in (6.0, 7.0)}
    return salida


# ---- 6 · Omori-Utsu ------------------------------------------------------------------------
def replicas_pedernales(df: pd.DataFrame, mc: float | None = None) -> dict:
    p = config.PEDERNALES
    rep = omori.seleccionar_replicas(df, p, config.RADIO_REPLICAS_KM, config.DIAS_REPLICAS)
    mc = mc if mc is not None else gr.mc_maxc(rep["mw"])
    t = rep.loc[rep["mw"] >= mc, "dias"].to_numpy()
    s, fin = 0.0, float(config.DIAS_REPLICAS)
    utsu = omori.ajustar_omori_utsu(t, s, fin)
    p1 = omori.ajustar_omori_utsu(t, s, fin, p_fijo=1.0)
    expo = omori.ajustar_exponencial(t, s, fin)
    sensibilidad = []
    for umbral in (4.5, 4.7, 4.9, 5.0, 5.2):
        tt = rep.loc[rep["mw"] >= umbral, "dias"].to_numpy()
        if len(tt) >= 25:
            a = omori.ajustar_omori_utsu(tt, s, fin)
            sensibilidad.append({"mc": umbral, "n": a["n"], "p": a["p"], "se_p": a["se_p"], "c": a["c"], "K": a["K"]})
    mayor = rep.loc[rep["mw"].idxmax()]
    return {
        "replicas_m25_150km_365d": int(len(rep)), "mc": mc, "n_sobre_mc": int(len(t)),
        "omori_utsu": utsu, "omori_p1": p1, "exponencial": expo,
        "delta_aic_exponencial_vs_utsu": expo["aic"] - utsu["aic"],
        "delta_aic_p1_vs_utsu": p1["aic"] - utsu["aic"],
        "sensibilidad_mc": sensibilidad,
        "pct_primera_semana": round(100 * float((t <= 7).mean()), 1),
        "pct_primer_mes": round(100 * float((t <= 30).mean()), 1),
        "mayor_replica": {"tiempo": str(mayor["tiempo"]), "mw": float(mayor["mw"]), "dias": float(mayor["dias"]),
                          "lugar": str(mayor["lugar"])},
        "ley_bath_delta_m": round(p["magnitud"] - float(mayor["mw"]), 2),
        "_replicas": rep,
    }
