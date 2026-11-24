"""
Orquestador: de los bloques crudos a las tablas, figuras y ``reports/resultados.json``.

    python -m clima_ecuador.pipeline              # usa la caché de data/raw (descarga lo que falte)
    python -m clima_ecuador.pipeline --sin-descarga
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

from . import agregacion, calidad, clima, config, descarga, enso, extremos, graficos, tendencias, validacion

VARIABLES_TENDENCIA = ["tmed", "tmax", "tmin", "precip", "humedad", "viento_max", "radiacion"]


def _guardar(df: pd.DataFrame, nombre: str) -> None:
    config.REPORTES.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.REPORTES / nombre, index=False, float_format="%.4f")


def construir_series(avisar=print) -> dict:
    """Horario → diario → mensual → anual, con los controles de calidad."""
    celdas = pd.read_csv(config.CELDAS)
    horario, solape = agregacion.unir_horario()
    horario = agregacion.variables_derivadas(horario, celdas)
    horario, viento_espurio = calidad.filtrar_viento_espurio(horario)
    avisar(f"Horario: {len(horario):,} filas · {horario['punto'].nunique()} puntos · "
           f"{len(viento_espurio)} horas de viento espurio anuladas")
    config.INTERMEDIOS.mkdir(parents=True, exist_ok=True)
    horario.to_parquet(config.HORARIO, index=False)

    diario = agregacion.a_diario(horario)
    mensual = agregacion.a_mensual(diario)
    anual = agregacion.a_anual(mensual)
    config.PROCESADOS.mkdir(parents=True, exist_ok=True)
    diario.to_parquet(config.DIARIO, index=False)
    mensual.to_parquet(config.MENSUAL, index=False)

    controles = {
        "completitud": calidad.completitud(horario), "huecos": calidad.huecos_tiempo(horario),
        "rangos": calidad.fuera_de_rango(horario), "pegados": calidad.valores_pegados(horario),
        "alineacion": calidad.alineacion_horaria(horario), "consistencia": calidad.consistencia_diaria(diario),
    }
    muestra = descarga.descargar_muestra_api()
    controles["api"] = calidad.comparar_con_api(diario, muestra)
    controles["solape"] = solape
    controles["viento_espurio"] = viento_espurio
    controles["viento_espurio_por_hora"] = (viento_espurio["hora_utc"].dt.hour.value_counts().sort_index()
                                            .rename_axis("hora_utc").reset_index(name="horas"))
    for nombre, t in controles.items():
        _guardar(t, f"calidad_{nombre}.csv")
    resumen = calidad.resumen(controles)
    assert resumen["saltos"] == 0 and resumen["duplicadas"] == 0, "Hay huecos en la serie horaria"
    assert resumen["fuera_de_rango"] == 0, "Hay valores fuera de rango físico"
    assert resumen["inconsistencias_diarias"] == 0, "Tmín/Tmed/Tmáx inconsistentes"
    ciclo = clima.ciclo_diurno(horario)
    ciclo.to_csv(config.PROCESADOS / "ciclo_diurno.csv", index=False)
    return {"celdas": celdas, "diario": diario, "mensual": mensual, "anual": anual, "controles": controles,
            "resumen_calidad": resumen, "ciclo": ciclo}


def analizar(s: dict, avisar=print) -> dict:
    diario, mensual, anual = s["diario"], s["mensual"], s["anual"]
    ciudades_diario = agregacion.solo_ciudades(diario)
    ciudades_mensual = agregacion.solo_ciudades(mensual)
    ciudades_anual = agregacion.solo_ciudades(anual)

    # --- Estacionalidad y climatología ---------------------------------------------------------
    clim = clima.climatologia_mensual(ciudades_mensual)
    clim_region = agregacion.con_region(clim).groupby(["region", "m"])[clima.VARIABLES].mean().reset_index()
    clim_region.to_csv(config.PROCESADOS / "climatologia_regiones.csv", index=False)
    estacional = clima.estacionalidad_lluvia(clim_region)
    _guardar(estacional, "estacionalidad_lluvia.csv")

    # --- Anomalías --------------------------------------------------------------------------------
    anom_m = clima.anomalias_mensuales(ciudades_mensual)
    anom_a = clima.anomalias_anuales(ciudades_anual)
    anom_m.to_parquet(config.PROCESADOS / "anomalias_mensuales.parquet", index=False)
    anom_a.to_csv(config.PROCESADOS / "anomalias_anuales.csv", index=False)
    anom_reg_a = agregacion.con_region(anom_a).groupby(["region", "anio"])[
        clima.VARIABLES + ["precip_pct"]].mean().reset_index()
    anom_reg_m = agregacion.con_region(anom_m).groupby(["region", "mes"])[
        clima.VARIABLES + ["precip_pct"]].mean().reset_index()
    anom_reg_a.to_csv(config.PROCESADOS / "anomalias_anuales_regiones.csv", index=False)
    anom_nac = anom_a.groupby("anio")[clima.VARIABLES + ["precip_pct"]].mean().reset_index()

    # --- Tendencias ------------------------------------------------------------------------------
    tend_ciudad = tendencias.tabla_tendencias(ciudades_anual, VARIABLES_TENDENCIA)
    tend_ciudad["region"] = tend_ciudad["punto"].map({c: v[3] for c, v in config.CIUDADES.items()})
    tend_ciudad = tend_ciudad.merge(ciudades_anual.groupby("punto")["precip"].mean().rename("precip_media"),
                                    left_on="punto", right_index=True)
    es_lluvia = tend_ciudad["variable"] == "precip"
    tend_ciudad["pendiente_pct_decada"] = np.where(es_lluvia, 100 * tend_ciudad["pendiente_decada"]
                                                   / tend_ciudad["precip_media"], np.nan)
    _guardar(tend_ciudad, "tendencias_ciudades.csv")
    anual_region = agregacion.promedio_regional(ciudades_anual, VARIABLES_TENDENCIA, "anio")
    tend_region = tendencias.tabla_tendencias(anual_region, VARIABLES_TENDENCIA, grupo="region")
    _guardar(tend_region, "tendencias_regiones.csv")
    tend_nac = tendencias.tabla_tendencias(anom_nac.assign(pais="Ecuador"), ["tmed", "tmax", "tmin", "precip_pct"],
                                           grupo="pais")
    _guardar(tend_nac, "tendencias_nacional.csv")

    # Puntos de cambio (Pettitt) en la temperatura media anual: ¿hay saltos que sugieran inhomogeneidades?
    pett = []
    for punto, d in ciudades_anual.groupby("punto"):
        d = d.sort_values("anio")
        k, p = tendencias.pettitt(d["tmed"].to_numpy())
        k2, p2 = tendencias.pettitt_sin_tendencia(d["tmed"].to_numpy())
        pett.append({"punto": punto, "anio_cambio": int(d["anio"].iloc[k + 1]), "p": p,
                     "anio_cambio_sin_tendencia": int(d["anio"].iloc[k2 + 1]), "p_sin_tendencia": p2})
    pett = pd.DataFrame(pett)
    _guardar(pett, "pettitt_tmed.csv")

    # --- Extremos --------------------------------------------------------------------------------
    indices = extremos.indices_anuales(ciudades_diario)
    indices.to_parquet(config.ANUAL, index=False)
    todos_ind = extremos.INDICES_CALOR + extremos.INDICES_LLUVIA
    tend_ext = tendencias.tabla_tendencias(indices, todos_ind)
    tend_ext["region"] = tend_ext["punto"].map({c: v[3] for c, v in config.CIUDADES.items()})
    _guardar(tend_ext, "tendencias_extremos_ciudades.csv")
    ind_region = agregacion.promedio_regional(indices, todos_ind, "anio")
    ind_region.to_csv(config.PROCESADOS / "extremos_regiones.csv", index=False)
    tend_ext_reg = tendencias.tabla_tendencias(ind_region, todos_ind, grupo="region")
    _guardar(tend_ext_reg, "tendencias_extremos_regiones.csv")
    decadas = indices.assign(decada=(indices["anio"] // 10) * 10)
    decadas = agregacion.con_region(decadas)
    por_decada = decadas[decadas["anio"].between(1981, 2020) | (decadas["anio"] >= 2015)]
    comp = pd.DataFrame({
        "1981_1990": indices[indices["anio"].between(1981, 1990)].groupby("punto")[todos_ind].mean().mean(),
        "2015_2024": indices[indices["anio"].between(2015, 2024)].groupby("punto")[todos_ind].mean().mean(),
    })
    comp["cambio"] = comp["2015_2024"] - comp["1981_1990"]
    _guardar(comp.reset_index(names="indice"), "extremos_1980s_vs_ultima_decada.csv")
    del por_decada

    # --- El Niño ---------------------------------------------------------------------------------
    oni = descarga.leer_oni(config.CRUDOS / "oni.data")
    oni = oni[oni["fecha"].dt.year.between(config.ANIO_INICIO - 1, config.ANIO_FIN)]
    oni.to_csv(config.ONI, index=False)
    corr_region = enso.correlaciones_rezago(anom_reg_m, oni, ["precip_pct", "tmed", "tmax"], grupo="region")
    _guardar(corr_region, "enso_correlaciones_regiones.csv")
    corr_ciudad = enso.correlaciones_rezago(anom_m, oni, ["precip_pct", "tmed"], grupo="punto")
    _guardar(corr_ciudad, "enso_correlaciones_ciudades.csv")
    mejor = enso.mejor_rezago(corr_ciudad)
    _guardar(mejor, "enso_mejor_rezago_ciudades.csv")
    comp_enso = enso.compuestos(anom_reg_m, oni)
    _guardar(comp_enso, "enso_compuestos_ene_abr.csv")
    episodios = enso.episodios_fuertes(anom_reg_m, oni)
    _guardar(episodios, "enso_episodios_fuertes.csv")
    nino12 = descarga.leer_oni(config.CRUDOS / "nino12.data", "nino12")
    nino12 = nino12[nino12["fecha"].dt.year.between(config.ANIO_INICIO - 1, config.ANIO_FIN)]
    nino12.to_csv(config.NINO12, index=False)
    temporada = enso.temporada_lluviosa(anom_reg_m, {"oni": oni, "nino12": nino12})
    _guardar(temporada, "enso_temporada_ene_abr.csv")
    comp_indices = enso.comparar_indices(temporada, config.REGIONES, ["oni", "nino12"])
    _guardar(comp_indices, "enso_oni_vs_nino12.csv")
    corr_nino12 = enso.correlaciones_rezago(anom_reg_m, nino12.rename(columns={"nino12": "oni"}), ["precip_pct"],
                                            grupo="region")
    _guardar(corr_nino12, "enso_correlaciones_nino12_regiones.csv")

    # --- Validación con estaciones -------------------------------------------------------------
    ghcn = descarga.leer_ghcn(sorted((config.CRUDOS / "ghcn").glob("*.csv")))
    ghcn = ghcn[ghcn["fecha"].dt.year.between(config.ANIO_INICIO, config.ANIO_FIN)]
    ghcn.to_parquet(config.ESTACIONES_DIARIO, index=False)
    unidas = validacion.unir_estaciones(diario, ghcn)
    met = validacion.metricas(unidas)
    _guardar(met, "validacion_estaciones.csv")

    return {"clim_region": clim_region, "estacional": estacional, "anom_reg_a": anom_reg_a, "anom_reg_m": anom_reg_m,
            "anom_nac": anom_nac, "anom_a": anom_a, "tend_ciudad": tend_ciudad, "tend_region": tend_region,
            "tend_nac": tend_nac, "pettitt": pett, "indices": indices, "tend_ext": tend_ext,
            "ind_region": ind_region, "tend_ext_reg": tend_ext_reg, "comp_extremos": comp, "oni": oni,
            "corr_region": corr_region, "corr_ciudad": corr_ciudad, "mejor_rezago": mejor, "comp_enso": comp_enso,
            "episodios": episodios, "temporada": temporada, "comp_indices": comp_indices,
            "corr_nino12": corr_nino12, "nino12": nino12, "unidas": unidas, "validacion": met, "anual_region": anual_region}


def _r(x, n=3):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def resultados(s: dict, a: dict) -> dict:
    """Cifras que cita el README: todas salen de aquí."""
    tc, tr, tn = a["tend_ciudad"], a["tend_region"], a["tend_nac"]
    tmed_c = tc[tc["variable"] == "tmed"]
    lluvia_c = tc[tc["variable"] == "precip"]
    r = {
        "calidad": s["resumen_calidad"],
        "api_vs_propio": a_dict(s["controles"]["api"], "variable"),
        "nacional": {f["variable"]: {"pendiente_decada": _r(f["pendiente_decada"]), "p_hr": _r(f["p_hamed_rao"], 4),
                                     "p_original": _r(f["p_original"], 6), "cambio_total": _r(f["cambio_total"])}
                     for _, f in tn.iterrows()},
        "regiones": {f"{f['region']}|{f['variable']}": {"pendiente_decada": _r(f["pendiente_decada"]),
                                                         "ic": [_r(f["ic_bajo_decada"]), _r(f["ic_alto_decada"])],
                                                         "p_hr": _r(f["p_hamed_rao"], 4),
                                                         "p_original": _r(f["p_original"], 6)}
                     for _, f in tr.iterrows()},
        "ciudades_tmed": {
            "significativas_sube": int(((tmed_c["tendencia"] == "sube")).sum()),
            "significativas_fdr": int(tmed_c["significativa_fdr"].sum()),
            "total": int(len(tmed_c)),
            "max": tmed_c.nlargest(1, "pendiente_decada")[["punto", "pendiente_decada"]].to_dict("records"),
            "min": tmed_c.nsmallest(1, "pendiente_decada")[["punto", "pendiente_decada"]].to_dict("records"),
            "significativas_sin_correccion": int((tmed_c["p_original"] < config.ALFA).sum()),
        },
        "ciudades_lluvia": {
            "sube": lluvia_c[lluvia_c["tendencia"] == "sube"]["punto"].tolist(),
            "baja": lluvia_c[lluvia_c["tendencia"] == "baja"]["punto"].tolist(),
            "sin_tendencia": int((lluvia_c["tendencia"] == "sin tendencia").sum()),
        },
        "anios_mas_calidos": a["anom_nac"].nlargest(5, "tmed")[["anio", "tmed"]].round(3).to_dict("records"),
        "pettitt": {
            "con_tendencia": a["pettitt"]["anio_cambio"][a["pettitt"]["p"] < 0.05].value_counts().head(5).to_dict(),
            "sin_tendencia_significativos": int((a["pettitt"]["p_sin_tendencia"] < 0.05).sum()),
            "sin_tendencia": a["pettitt"]["anio_cambio_sin_tendencia"][a["pettitt"]["p_sin_tendencia"] < 0.05]
            .value_counts().head(5).to_dict(),
        },
        "hamed_rao_factor_menor_1": int((tc["factor_hr"] < 1).sum()),
        "tendencias_evaluadas": int(len(tc)),
        "extremos_regiones": {f"{f['region']}|{f['variable']}": {"pendiente_decada": _r(f["pendiente_decada"]),
                                                                  "p_hr": _r(f["p_hamed_rao"], 4)}
                              for _, f in a["tend_ext_reg"].iterrows()},
        "extremos_1980s_vs_ultima_decada": {k: {kk: _r(vv) for kk, vv in v.items()}
                                            for k, v in a["comp_extremos"].to_dict("index").items()},
        "enso_regiones": a["corr_region"].loc[a["corr_region"].assign(x=a["corr_region"]["r"].abs())
                                              .groupby(["region", "variable"])["x"].idxmax()]
        .round(3).to_dict("records"),
        "enso_compuestos": a["comp_enso"].round(2).to_dict("records"),
        "enso_episodios": a["episodios"].round(2).to_dict("records"),
        "enso_oni_vs_nino12": a["comp_indices"].round(3).to_dict("records"),
        "enso_temporada_fuertes": a["temporada"][a["temporada"]["anio"].isin([1983, 1992, 1998, 2016, 2024])]
        .round(2).to_dict("records"),
        "estacionalidad": a["estacional"].round(2).to_dict("records"),
        "validacion": a["validacion"].round(3).to_dict("records"),
    }
    return r


def a_dict(df: pd.DataFrame, clave: str) -> dict:
    return {f[clave]: {k: _r(v, 4) if isinstance(v, float) else v for k, v in f.items() if k != clave}
            for f in df.to_dict("records")}


def main(descargar: bool = True) -> dict:
    t0 = time.perf_counter()
    if descargar:
        descarga.descargar_todo()
    s = construir_series()
    a = analizar(s)
    graficos.todas(s, a)
    r = resultados(s, a)
    config.RESULTADOS.write_text(json.dumps(r, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"Listo en {time.perf_counter() - t0:.0f} s · {len(s['diario']):,} días-punto · "
          f"tendencia nacional Tmed {r['nacional']['tmed']['pendiente_decada']} °C/década")
    return r


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sin-descarga", action="store_true")
    main(descargar=not p.parse_args().sin_descarga)
