"""
Pipeline completo: descarga (con caché) → calidad → exploratorio → Gutenberg-Richter → retorno → Omori.

    python -m sismos.pipeline                 # descarga lo que falte y analiza
    python -m sismos.pipeline --sin-descarga  # solo analiza con lo que ya está en data/raw/

Salidas: data/procesados/*.parquet, reports/resultados.json, reports/*.csv y reports/figures/*.png.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import numpy as np
import pandas as pd

from . import analisis, config, graficos
from . import gutenberg_richter as gr
from .calidad import asignar_zona, limpiar
from .desagrupar import gardner_knopoff
from .descarga import descargar_todo, union_cruda

MC_COMUN_CINTURON = 5.5


def _json(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return round(float(o), 6)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp,)):
        return str(o)
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(type(o))


def ejecutar(descargar: bool = True) -> dict:
    inicio = time.time()
    if descargar:
        descargar_todo()
    config.PROCESADOS.mkdir(parents=True, exist_ok=True)
    resultados: dict = {}

    # 2 · Calidad
    print("Calidad y homogeneización de magnitudes")
    ecuador, inf_ec = limpiar(pd.read_parquet(union_cruda("ecuador_m2.5")), semilla=config.SEMILLA)
    mundo, inf_mu = limpiar(pd.read_parquet(union_cruda("mundo_m5")), semilla=config.SEMILLA)
    historico, inf_hi = limpiar(pd.read_parquet(union_cruda("ecuador_m6_historico")), semilla=config.SEMILLA)
    ecuador["principal_gk"] = gardner_knopoff(ecuador)
    mundo["zona"] = asignar_zona(mundo, config.ZONAS_CINTURON)
    ecuador.to_parquet(config.CATALOGO_ECUADOR, index=False)
    mundo.to_parquet(config.CATALOGO_CINTURON, index=False)
    historico.to_parquet(config.CATALOGO_HISTORICO, index=False)
    config.MUESTRA.mkdir(parents=True, exist_ok=True)
    ecuador[ecuador["anio"].between(2016, 2017)].to_csv(config.MUESTRA / "catalogo_ecuador_muestra.csv",
                                                        index=False)
    resultados["calidad"] = {"ecuador": inf_ec, "mundo_m5": inf_mu, "historico_m6": inf_hi}

    # 3 · Exploratorio
    print("Exploratorio y mapas")
    resultados["exploratorio"] = analisis.resumen_exploratorio(ecuador)
    pendiente = analisis.pendiente_placa(ecuador)
    resultados["exploratorio"]["pendiente_placa"] = pendiente
    graficos.fig_calidad(ecuador)
    graficos.fig_eventos_por_anio(ecuador)
    graficos.fig_magnitud_profundidad(ecuador)
    graficos.fig_mapa_ecuador(ecuador)
    graficos.fig_perfil(analisis.perfil_subduccion(ecuador), pendiente)

    # 4 · Gutenberg-Richter
    print("Gutenberg-Richter")
    anios_ec = analisis.anios_catalogo(config.ANIO_INICIO_ECUADOR)
    gr_ec = analisis.ajuste_completo(ecuador["mw"], anios_ec)
    gr_ec_original = analisis.ajuste_completo(ecuador["mag_original"], anios_ec)
    resultados["gutenberg_richter_ecuador"] = gr_ec
    resultados["gutenberg_richter_ecuador_magnitud_original"] = gr_ec_original
    estabilidad = pd.DataFrame(gr.estabilidad_b(ecuador["mw"], np.round(np.arange(4.5, 6.55, 0.1), 1)))
    estabilidad.to_csv(config.REPORTES / "estabilidad_valor_b.csv", index=False)
    graficos.fig_gutenberg_richter(ecuador["mw"], gr_ec,
                                   f"Gutenberg-Richter, Ecuador ampliado 1970–{config.ANIO_FIN} "
                                   f"({graficos.miles(len(ecuador))} sismos)",
                                   "06_gutenberg_richter_ecuador.png")
    graficos.fig_estabilidad_b(estabilidad, gr_ec["mc_maxc"], gr_ec["mc_mbs"])

    cinturon = analisis.comparar_cinturon(mundo, mc_comun=MC_COMUN_CINTURON)
    cinturon.to_csv(config.REPORTES / "valor_b_cinturon.csv", index=False)
    resultados["cinturon"] = {"mc_comun": MC_COMUN_CINTURON, "zonas": cinturon.to_dict("records"),
                              "eventos_en_zonas": int(mundo["zona"].notna().sum()),
                              "eventos_mundo": int(len(mundo)),
                              "zonas_gr_subestima_m7": int((cinturon["tasa_m7_gr"] < cinturon["tasa_m7_empirica"]).sum()),
                              "mediana_cociente_empirica_gr_m7": float((cinturon["tasa_m7_empirica"]
                                                                        / cinturon["tasa_m7_gr"]).median())}
    graficos.fig_mapa_cinturon(mundo[mundo["zona"].notna() | mundo["longitud"].abs().gt(95)])
    graficos.fig_b_por_zona(cinturon, MC_COMUN_CINTURON)
    graficos.fig_gr_vs_empirico(cinturon)

    # 5 · Periodos de retorno (Mc por estabilidad de b: el de máxima curvatura subestima mucho M7)
    print("Periodos de retorno")
    mc_ret = gr_ec["mc_mbs"]
    ret = analisis.periodos_retorno(ecuador, historico, mc_ret)
    ret_maxc = analisis.periodos_retorno(ecuador, historico, gr_ec["mc_maxc"])
    resultados["retorno"] = ret
    resultados["retorno_con_mc_maxc"] = {k: ret_maxc[k] for k in ("mc", "gr_desagrupado", "b_desagrupado")}
    principales = ecuador[ecuador["principal_gk"]]
    hist_pr = historico[gardner_knopoff(historico)]
    graficos.fig_retorno(principales, hist_pr, ret["b_desagrupado"], ret["anios"],
                         analisis.anios_catalogo(config.ANIO_INICIO_HISTORICO))
    filas = []
    for clave, etiqueta in (("gr_desagrupado", "GR desagrupado (principal)"), ("gr_completo", "GR con réplicas"),
                            ("gr_superficiales", "GR solo superficiales <70 km")):
        for f in ret[clave]:
            filas.append({"modelo": etiqueta, "magnitud": f["magnitud"], "periodo_retorno_anios": f["periodo_retorno_anios"],
                          "periodo_ic95_bajo": f["periodo_ic95"][0], "periodo_ic95_alto": f["periodo_ic95"][1],
                          "prob_anual": f["prob_anual"], "prob_50_anios": f["prob_50_anios"]})
    for m in ("m6", "m7"):
        e = ret["empirica_1970"][m]
        filas.append({"modelo": "Conteo 1970–2025 (línea base)", "magnitud": float(m[1:]),
                      "periodo_retorno_anios": e["periodo_retorno_anios"], "periodo_ic95_bajo": 1 / e["tasa_ic95"][1],
                      "periodo_ic95_alto": 1 / e["tasa_ic95"][0] if e["tasa_ic95"][0] else None,
                      "prob_anual": e["prob_anual"], "prob_50_anios": 1 - np.exp(-50 * e["tasa_anual"])})
    e = ret["empirica_1900_m7"]
    filas.append({"modelo": "Conteo 1900–2025 (línea base)", "magnitud": 7.0,
                  "periodo_retorno_anios": e["periodo_retorno_anios"], "periodo_ic95_bajo": 1 / e["tasa_ic95"][1],
                  "periodo_ic95_alto": 1 / e["tasa_ic95"][0], "prob_anual": e["prob_anual"],
                  "prob_50_anios": 1 - np.exp(-50 * e["tasa_anual"])})
    pd.DataFrame(filas).to_csv(config.REPORTES / "periodos_retorno.csv", index=False)

    # 6 · Réplicas de Pedernales
    print("Omori-Utsu, Pedernales 2016")
    om = analisis.replicas_pedernales(ecuador)
    rep = om.pop("_replicas")
    rep.to_csv(config.REPORTES / "replicas_pedernales.csv", index=False)
    resultados["omori_pedernales"] = om
    graficos.fig_mapa_replicas(rep, om["mc"])
    graficos.fig_omori(rep.loc[rep["mw"] >= om["mc"], "dias"].to_numpy(), om)

    resultados["segundos"] = round(time.time() - inicio, 1)
    config.RESULTADOS.write_text(json.dumps(resultados, ensure_ascii=False, indent=2, default=_json),
                                 encoding="utf-8")
    print(f"Listo en {resultados['segundos']} s → {config.RESULTADOS}")
    return resultados


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sin-descarga", action="store_true", help="no consultar la API; usar data/raw/")
    ejecutar(descargar=not p.parse_args().sin_descarga)


if __name__ == "__main__":
    main()
