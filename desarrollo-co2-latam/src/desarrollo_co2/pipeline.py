"""
Orquestador: descarga (con caché) → panel → desacople → Kaya → Kuznets → figuras y reportes.

    python -m desarrollo_co2.pipeline
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from . import config, descarga, desacople, graficos, kaya, kuznets, limpieza, union

VARIABLES_COBERTURA = ["pib_ppa", "pib_pc_ppa", "poblacion_bm", "urbana_pct", "industria_pct_pib",
                       "renovable_pct_consumo", "acceso_electricidad_pct", "pobreza_extrema_pct", "bosque_pct",
                       "co2_mt", "co2_consumo_mt", "co2_con_luc_mt", "energia_twh", "gei_total_mt"]


def _limpio(v):
    """Convierte tipos de numpy/pandas para que json los acepte."""
    if isinstance(v, dict):
        return {k: _limpio(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_limpio(x) for x in v]
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else round(float(v), 4)
    if isinstance(v, np.integer):
        return int(v)
    return v


def ejecutar(descargar: bool = True) -> dict:
    t0 = time.perf_counter()
    config.REPORTES.mkdir(parents=True, exist_ok=True)
    config.PROCESADOS.mkdir(parents=True, exist_ok=True)
    if descargar:
        pd.DataFrame(descarga.descargar_todo()).to_csv(config.REPORTES / "log_descarga.csv", index=False)

    # 1. Panel
    panel, informe = union.construir_panel()
    cob = limpieza.cobertura(panel[panel["iso3"] != config.REGION], VARIABLES_COBERTURA)
    panel.to_csv(config.PANEL, index=False)
    cob.to_csv(config.COBERTURA, index=False)
    informe["diferencia_poblacion"].to_csv(config.REPORTES / "control_poblacion.csv", index=False)

    # 2. Desacople
    ini, fin = config.PERIODO_DESACOPLE
    tabla = desacople.tabla_desacople(panel, ini, fin)
    tabla.to_csv(config.REPORTES / "desacople_2000_2024.csv", index=False)
    subs = {f"{a}-{b}": desacople.tabla_desacople(panel, a, b) for a, b in config.SUBPERIODOS}
    robustez = desacople.comparar_medidas(panel, *config.PERIODO_CONSUMO)
    robustez.to_csv(config.REPORTES / "desacople_robustez_medidas.csv", index=False)
    movil = desacople.desacople_movil(panel)

    # 3. Kaya (Ecuador y región)
    kayas = {"Ecuador": kaya.descomponer(panel, "ECU", ini, fin, ventana=config.VENTANA_EXTREMOS),
             "América Latina": kaya.descomponer(panel, config.REGION, ini, fin, ventana=config.VENTANA_EXTREMOS)}
    pd.concat(kayas.values()).to_csv(config.REPORTES / "kaya_lmdi.csv", index=False)

    # 4. Kuznets
    d = kuznets.preparar(panel)
    modelos = kuznets.tabla_modelos(panel)
    modelos.to_csv(config.REPORTES / "kuznets_modelos.csv", index=False)
    boot = kuznets.bootstrap_punto_giro(d)
    pend = kuznets.pendientes_por_pais(panel)
    pend.to_csv(config.REPORTES / "kuznets_pendientes.csv", index=False)

    # 5. Figuras
    anio_ult = int(panel.dropna(subset=["pib_ppa", "co2_mt"])["anio"].max())
    graficos.cobertura(cob, VARIABLES_COBERTURA)
    graficos.emisiones_vs_ingreso(panel, anio_ult)
    graficos.indices(desacople.serie_indice(panel, config.REGION, ini),
                     f"América Latina: el PIB creció más que el CO2 desde {ini}",
                     f"Índices {ini} = 100, agregado de 18 países. La intensidad de carbono cae ~1 % al año.",
                     "03_region_indices.png")
    graficos.desacople_dispersion(tabla, config.PERIODO_DESACOPLE)
    (a1, b1), (a2, b2) = config.SUBPERIODOS
    graficos.elasticidad_subperiodos(subs[f"{a1}-{b1}"], subs[f"{a2}-{b2}"], (f"{a1}–{b1}", f"{a2}–{b2}"))
    graficos.desacople_movil(movil, config.VENTANA_MOVIL)
    graficos.ecuador_vs_region(panel)
    graficos.kaya_comparacion(kayas, config.PERIODO_DESACOPLE)
    graficos.fuentes_co2(panel)
    m_pool, m_fe = kuznets.ajustar(d, "pooled"), kuznets.ajustar(d, "fe_pais_anio")
    graficos.kuznets(d, {"MCO agrupado": kuznets.curva(m_pool, d), "Efectos fijos país + año": kuznets.curva(m_fe, d)})
    graficos.pendientes(pend)

    # 6. Resumen con las cifras que cita el README
    ecu = tabla.set_index("iso3").loc["ECU"]
    reg = tabla.set_index("iso3").loc[config.REGION]
    p_ult = panel[panel["anio"] == anio_ult].set_index("iso3")
    resultados = {
        "periodo_desacople": config.PERIODO_DESACOPLE,
        "ultimo_anio": anio_ult,
        "filas_panel": len(panel),
        "informe_union": {k: v for k, v in informe.items() if k != "diferencia_poblacion"},
        "max_dif_poblacion_pct": informe["diferencia_poblacion"]["max_abs"].max(),
        "conteo_desacople": desacople.conteo_categorias(tabla).to_dict(),
        "conteo_subperiodos": {k: desacople.conteo_categorias(t).to_dict() for k, t in subs.items()},
        "absolutos_2012_2024": subs[f"{a2}-{b2}"].query("categoria == 'Absoluto'")["pais"].tolist(),
        "tapio": tabla.set_index("pais")["tapio"].to_dict(),
        "conteo_tapio": tabla[tabla["iso3"] != config.REGION]["tapio"].value_counts().to_dict(),
        "robustez_consumo": robustez.set_index("pais")["Consumo"].astype(str).to_dict(),
        "ecuador": {
            "crec_pib_anual": ecu["crec_pib_anual"], "crec_co2_anual": ecu["crec_co2_anual"],
            "elasticidad": ecu["elasticidad"], "categoria": str(ecu["categoria"]), "tapio": ecu["tapio"],
            "co2_pc": p_ult.loc["ECU", "co2_pc_t"], "intensidad": p_ult.loc["ECU", "intensidad_co2_kg_usd"],
            "petroleo_pct": p_ult.loc["ECU", "petroleo_pct_co2"],
            "comercio_neto_pct_2023": panel.query("iso3 == 'ECU' and anio == 2023")["comercio_neto_co2_pct"].item(),
        },
        "region": {
            "crec_pib_anual": reg["crec_pib_anual"], "crec_co2_anual": reg["crec_co2_anual"],
            "elasticidad": reg["elasticidad"], "co2_pc": p_ult.loc[config.REGION, "co2_pc_t"],
            "intensidad": p_ult.loc[config.REGION, "intensidad_co2_kg_usd"],
        },
        "kaya": {k: t.set_index("factor")["pct_co2_inicial"].to_dict() for k, t in kayas.items()},
        "kuznets_modelos": modelos.to_dict(orient="records"),
        "kuznets_bootstrap": {k: v for k, v in boot.items() if k != "giros"},
        "pendientes_rango": [pend["elasticidad"].min(), pend["elasticidad"].max()],
        "segundos": round(time.perf_counter() - t0, 1),
    }
    resultados = _limpio(resultados)
    (config.REPORTES / "resultados.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2),
                                                    encoding="utf-8")
    return resultados


if __name__ == "__main__":
    r = ejecutar()
    print(f"Listo en {r['segundos']} s · panel de {r['filas_panel']} filas · desacople: {r['conteo_desacople']}")
