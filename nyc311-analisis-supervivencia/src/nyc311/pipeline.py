"""Pipeline completo: limpieza → KM y log-rank → sesgo → Cox → equidad → evolución → reports/.

Uso:
    python -m nyc311.pipeline                 # usa data/raw/nyc311_crudo.parquet (descárgalo antes)
    python -m nyc311.pipeline --sin-limpieza  # reutiliza data/procesados/nyc311_supervivencia.parquet

Todo lo que citan el README, la guía, los notebooks y la app sale de `reports/` (resultados.json,
tablas/*.csv y curvas_km.parquet), así que se puede revisar sin descargar los 7,5 M de filas.
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

import numpy as np
import pandas as pd

from nyc311 import cox, equidad, graficos, sesgo
from nyc311.config import (
    ARCHIVO_CRUDO,
    ARCHIVO_LIMPIO,
    ARCHIVO_MANIFIESTO,
    ARCHIVO_RESULTADOS,
    DIR_FIGURAS,
    DIR_PROCESADOS,
    DIR_TABLAS,
    URL_FICHA,
)
from nyc311.limpieza import agrupar_top, cargar_crudo, limpiar, validar_tabla
from nyc311.supervivencia import (
    curva_en_rejilla,
    evaluar,
    kaplan_meier,
    logrank,
    mediana_con_ic,
    resumen_por_grupo,
    tiempo_medio_restringido,
)

REJILLA = np.concatenate(([0.0], np.geomspace(1 / 1440, 400, 320)))  # 1 minuto a 400 días
N_AGENCIAS = 9
N_TIPOS = 20
N_TIPOS_APP = 30
MIN_N_CURVA = 30
ARCHIVO_CURVAS = DIR_TABLAS / "curvas_km.parquet"


def _limpio(x: Any) -> Any:
    """Convierte numpy/pandas a tipos JSON y los infinitos a None."""
    if isinstance(x, dict):
        return {str(k): _limpio(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_limpio(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else float(x)
    return x


def _registros(df: pd.DataFrame) -> list[dict[str, Any]]:
    return _limpio(df.to_dict(orient="records"))


def curvas(df: pd.DataFrame, columna: str, dimension: str, borough: str = "Toda la ciudad") -> list[pd.DataFrame]:
    salida = []
    for nombre, sub in df.groupby(columna, observed=True):
        if len(sub) < MIN_N_CURVA:
            continue
        c = curva_en_rejilla(sub["duracion_dias"].to_numpy(), sub["evento"].to_numpy(), REJILLA)
        c.insert(0, "dimension", dimension)
        c.insert(1, "grupo", str(nombre))
        c.insert(2, "borough", borough)
        c["n"] = len(sub)
        salida.append(c)
    return salida


def resumen_app(df: pd.DataFrame, tipos: pd.Index) -> pd.DataFrame:
    """Mediana KM, IC y % cerradas por tipo de queja × borough (incluye «Todos» y «Toda la ciudad»)."""
    con_tipo = df["tipo_queja"].isin(tipos)
    con_borough = df["borough"].ne("SIN DATO")
    partes = [
        df.loc[con_tipo & con_borough, ["tipo_queja", "borough"]].astype("string"),
        df.loc[con_tipo, ["tipo_queja"]].astype("string").assign(borough="Toda la ciudad"),
        df.loc[con_borough, ["borough"]].astype("string").assign(tipo_queja="Todos los tipos"),
        pd.DataFrame({"tipo_queja": "Todos los tipos", "borough": "Toda la ciudad"}, index=df.index),
    ]
    filas = []
    for p in partes:
        clave = (p["tipo_queja"] + "||" + p["borough"]).rename("clave")
        datos = df.loc[p.index, ["duracion_dias", "evento"]].assign(clave=clave.to_numpy())
        filas.append(resumen_por_grupo(datos, "clave", min_n=MIN_N_CURVA))
    r = pd.concat(filas, ignore_index=True)
    r[["tipo_queja", "borough"]] = r["clave"].str.split(r"\|\|", expand=True)
    return r.drop(columns="clave")


def resumen_global(df: pd.DataFrame) -> dict[str, Any]:
    dur, ev = df["duracion_dias"].to_numpy(), df["evento"].to_numpy()
    tabla = kaplan_meier(dur, ev)
    med, lo, hi = mediana_con_ic(tabla)
    return {
        "n": int(len(df)),
        "mediana_km_dias": med,
        "mediana_km_horas": med * 24,
        "mediana_ic_inf_horas": lo * 24,
        "mediana_ic_sup_horas": hi * 24,
        "promedio_ingenuo_cerradas_dias": float(dur[ev == 1].mean()),
        "mediana_ingenua_cerradas_horas": float(np.median(dur[ev == 1]) * 24),
        "rmst_90d_dias": tiempo_medio_restringido(tabla, 90),
        "pct_cerradas_1d": 100 * (1 - float(evaluar(tabla, 1)[0])),
        "pct_cerradas_7d": 100 * (1 - float(evaluar(tabla, 7)[0])),
        "pct_cerradas_30d": 100 * (1 - float(evaluar(tabla, 30)[0])),
        "pct_abiertas_90d": 100 * float(evaluar(tabla, 90)[0]),
    }


def pruebas_logrank(df: pd.DataFrame) -> pd.DataFrame:
    filas = []
    dims = {
        "agencia": df["agencia_top"],
        "tipo_queja": df["tipo_top"],
        "borough": df["borough"],
        "canal": df["canal"],
    }
    for nombre, grupos in dims.items():
        mascara = grupos.astype("string").ne("SIN DATO").to_numpy()
        r = logrank(df["duracion_dias"].to_numpy()[mascara], df["evento"].to_numpy()[mascara], grupos.to_numpy()[mascara])
        filas.append({"dimension": nombre, "grupos": r.grados_libertad + 1, "chi2": r.estadistico,
                      "gl": r.grados_libertad, "p_valor": r.p_valor})
    # Dentro de un mismo tipo de queja: ¿difieren los boroughs?
    for tipo in ["Illegal Parking", "Noise - Residential", "HEAT/HOT WATER", "Street Condition", "Rodent"]:
        sub = df.loc[df["tipo_queja"].eq(tipo) & df["borough"].ne("SIN DATO")]
        r = logrank(sub["duracion_dias"].to_numpy(), sub["evento"].to_numpy(), sub["borough"].astype("string").to_numpy())
        filas.append({"dimension": f"borough | {tipo}", "grupos": r.grados_libertad + 1, "chi2": r.estadistico,
                      "gl": r.grados_libertad, "p_valor": r.p_valor})
    return pd.DataFrame(filas)


def evolucion(df: pd.DataFrame, obs: pd.Series, esp: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Mediana KM, % cerrado ≤ 7 d y O/E ajustado por mezcla, por mes de creación y por año de la cohorte."""
    km_mes = resumen_por_grupo(df, "mes_creacion").rename(columns={"mes_creacion": "mes"})
    oe_mes = equidad.razon_oe(obs, esp, df["mes_creacion"].rename("mes"))
    mensual = km_mes.merge(oe_mes[["mes", "o_entre_e", "ic_inf", "ic_sup", "pct_esperado_7d"]], on="mes")
    mensual = mensual.sort_values("mes").reset_index(drop=True)

    anio = np.where(df["creada"] < "2025-10-01", "oct-2024 a sep-2025", "oct-2025 a sep-2026")
    anio = pd.Series(anio, index=df.index, name="periodo")
    tmp = df[["agencia_top", "duracion_dias", "evento"]].assign(periodo=anio)
    filas = []
    for (ag, per), sub in tmp.groupby(["agencia_top", "periodo"], observed=True):
        tabla = kaplan_meier(sub["duracion_dias"].to_numpy(), sub["evento"].to_numpy())
        filas.append({"agencia": ag, "periodo": per, "n": len(sub), "mediana_km_dias": mediana_con_ic(tabla)[0]})
    por_agencia = pd.DataFrame(filas).pivot(index="agencia", columns="periodo", values="mediana_km_dias")
    por_agencia.columns = ["mediana_anio1_dias", "mediana_anio2_dias"]
    por_agencia["cambio_pct"] = 100 * (por_agencia["mediana_anio2_dias"] / por_agencia["mediana_anio1_dias"] - 1)
    por_agencia = por_agencia.reset_index()

    oe_anio = equidad.razon_oe(obs, esp, anio)
    resumen = {"periodos": {}}
    for per in sorted(anio.unique()):
        sub = df.loc[anio.eq(per)]
        tabla = kaplan_meier(sub["duracion_dias"].to_numpy(), sub["evento"].to_numpy())
        fila = oe_anio.loc[oe_anio["periodo"].eq(per)].iloc[0]
        resumen["periodos"][per] = {
            "n": int(len(sub)),
            "mediana_km_horas": mediana_con_ic(tabla)[0] * 24,
            "pct_cerradas_7d": float(fila["pct_cerradas_7d"]),
            "o_entre_e": float(fila["o_entre_e"]),
        }
    # Cambios de proceso que mueven la mediana sin que cambie la atención real (ver README, limitaciones)
    dohmh = df["agencia"].eq("DOHMH")
    inst = df.loc[dohmh, "cierre_instantaneo"].groupby(anio[dohmh]).mean() * 100
    roedor = df["tipo_queja"].eq("Rodent")
    inst_roedor = df.loc[roedor, "cierre_instantaneo"].groupby(anio[roedor]).mean() * 100
    comida = df["tipo_queja"].eq("Food Establishment") & df["evento"].eq(1)
    resumen["dohmh"] = {
        "pct_instantaneos": {k: float(v) for k, v in inst.items()},
        "pct_instantaneos_roedores": {k: float(v) for k, v in inst_roedor.items()},
        "pct_comida_cerradas_a_60_dias": float(100 * df.loc[comida, "duracion_dias"].between(59.9, 60.1).mean()),
    }
    resumen["mes_mediana_max"] = mensual.loc[mensual["mediana_km_dias"].idxmax(), ["mes", "mediana_km_dias"]].to_dict()
    resumen["mes_mediana_min"] = mensual.loc[mensual["mediana_km_dias"].idxmin(), ["mes", "mediana_km_dias"]].to_dict()
    resumen["mes_oe_min"] = mensual.loc[mensual["o_entre_e"].idxmin(), ["mes", "o_entre_e"]].to_dict()
    resumen["mes_oe_max"] = mensual.loc[mensual["o_entre_e"].idxmax(), ["mes", "o_entre_e"]].to_dict()
    # Participación de calefacción/agua caliente (HPD) en invierno: explica el pico estacional de la mediana
    calef = df["tipo_queja"].eq("HEAT/HOT WATER").groupby(df["mes_creacion"], observed=True).mean() * 100
    resumen["pct_calefaccion_max"] = {"mes": str(calef.idxmax()), "pct": float(calef.max())}
    resumen["pct_calefaccion_min"] = {"mes": str(calef.idxmin()), "pct": float(calef.min())}
    return mensual, por_agencia, resumen


def ejecutar(sin_limpieza: bool = False) -> dict[str, Any]:
    t0 = time.time()
    manifiesto = json.loads(ARCHIVO_MANIFIESTO.read_text(encoding="utf-8"))
    if sin_limpieza and ARCHIVO_LIMPIO.exists():
        df = pd.read_parquet(ARCHIVO_LIMPIO)
        calidad = json.loads(ARCHIVO_RESULTADOS.read_text(encoding="utf-8"))["calidad"]
    else:
        df, calidad = limpiar(cargar_crudo(ARCHIVO_CRUDO), manifiesto["fecha_corte"])
        DIR_PROCESADOS.mkdir(parents=True, exist_ok=True)
        df.to_parquet(ARCHIVO_LIMPIO, index=False)
    problemas = validar_tabla(df)
    if problemas:
        raise RuntimeError(f"La tabla limpia no pasa la validación: {problemas}")
    print(f"[{time.time() - t0:5.0f} s] limpieza: {len(df):,} filas")

    df["agencia_top"] = agrupar_top(df["agencia"], N_AGENCIAS, "Otras")
    df["tipo_top"] = agrupar_top(df["tipo_queja"], N_TIPOS, "Otros")
    DIR_TABLAS.mkdir(parents=True, exist_ok=True)
    res: dict[str, Any] = {
        "fuente": {"dataset": "311 Service Requests from 2010 to Present", "url": URL_FICHA,
                   "fecha_corte": manifiesto["fecha_corte"], "mes_inicio": manifiesto["mes_inicio"],
                   "mes_fin": manifiesto["mes_fin"], "fecha_descarga_utc": manifiesto["inicio_descarga_utc"][:10]},
        "calidad": calidad,
        "global": resumen_global(df),
    }

    # 1) Kaplan-Meier por grupo y log-rank
    resumenes = {}
    for columna, archivo in [("agencia", "agencias"), ("tipo_queja", "tipos_queja"), ("borough", "boroughs"), ("canal", "canales")]:
        r = resumen_por_grupo(df, columna, min_n=1_000)
        r.to_csv(DIR_TABLAS / f"km_{archivo}.csv", index=False)
        resumenes[columna] = r
    # Mezcla de agencias por canal: explica por qué el teléfono parece «lento» sin ajustar
    mezcla = pd.crosstab(df["canal"], df["agencia"], normalize="index") * 100
    res["mezcla_canal"] = {c: {"pct_hpd": float(mezcla.loc[c, "HPD"]), "pct_nypd": float(mezcla.loc[c, "NYPD"])}
                           for c in mezcla.index}
    res["pct_solicitudes_por_borough"] = {str(k): float(v) for k, v in
                                          (df["borough"].value_counts(normalize=True) * 100).items()}
    lr = pruebas_logrank(df)
    lr.to_csv(DIR_TABLAS / "logrank.csv", index=False)
    res["logrank"] = _registros(lr)
    print(f"[{time.time() - t0:5.0f} s] Kaplan-Meier y log-rank")

    # 2) Sesgo del promedio: corte retrospectivo
    exp = sesgo.experimento_corte_retrospectivo(df)
    exp.to_csv(DIR_TABLAS / "sesgo_corte_retrospectivo.csv", index=False)
    res["sesgo"] = {"cohorte_desde": sesgo.COHORTE_DESDE, "cohorte_hasta": sesgo.COHORTE_HASTA,
                    "corte_ficticio": sesgo.CORTE_FICTICIO, "tabla": _registros(exp)}
    print(f"[{time.time() - t0:5.0f} s] experimento de corte retrospectivo")

    # 3) Curvas (figuras y app)
    lista = []
    lista += curvas(df, "agencia_top", "agencia")
    lista += curvas(df, "borough", "borough")
    lista += curvas(df, "canal", "canal")
    lista += curvas(df.assign(todo="Todos los tipos"), "todo", "tipo_borough")
    tipos_app = df["tipo_queja"].value_counts().head(N_TIPOS_APP).index
    app = df.loc[df["tipo_queja"].isin(tipos_app)]
    lista += curvas(app, "tipo_queja", "tipo_borough")
    for b, sub in df.loc[df["borough"].ne("SIN DATO")].groupby("borough", observed=True):
        lista += curvas(sub.assign(todo="Todos los tipos"), "todo", "tipo_borough", str(b))
        lista += curvas(sub.loc[sub["tipo_queja"].isin(tipos_app)], "tipo_queja", "tipo_borough", str(b))
    cohorte = df.loc[(df["creada"] >= sesgo.COHORTE_DESDE) & (df["creada"] < sesgo.COHORTE_HASTA)]
    for ag in ["DPR", "DOB"]:
        sub = cohorte.loc[cohorte["agencia"].eq(ag)]
        fic = sesgo.recensurar(sub, sesgo.CORTE_FICTICIO)
        for nombre, d, e in [
            ("Verdad (seguimiento completo)", sub["duracion_dias"], sub["evento"]),
            ("Kaplan-Meier al corte ficticio", fic["duracion_dias"], fic["evento"]),
            ("Ingenuo: solo cerradas al corte ficticio", fic["duracion_dias"][fic["evento"].eq(1)],
             np.ones(int(fic["evento"].sum()))),
        ]:
            c = curva_en_rejilla(np.asarray(d), np.asarray(e), REJILLA)
            c.insert(0, "dimension", f"sesgo_{ag}")
            c.insert(1, "grupo", nombre)
            c.insert(2, "borough", "Toda la ciudad")
            c["n"] = len(d)
            lista.append(c)
    curvas_df = pd.concat(lista, ignore_index=True)
    curvas_df.to_parquet(ARCHIVO_CURVAS, index=False)
    resumen_app(df, tipos_app).to_csv(DIR_TABLAS / "resumen_app.csv", index=False)
    print(f"[{time.time() - t0:5.0f} s] curvas ({len(curvas_df):,} filas)")

    # 4) Cox
    muestra = cox.muestra_modelo(df)
    res["cox"] = {"n_muestra": int(len(muestra)), "eventos_muestra": int(muestra["evento"].sum())}
    for modelo in ["A", "B"]:
        X = cox.matriz_modelo(muestra, modelo)
        cph = cox.ajustar(X, modelo)
        hr = cox.tabla_hr(cph)
        hr.to_csv(DIR_TABLAS / f"cox_modelo_{modelo}.csv", index=False)
        ph = cox.prueba_supuesto_ph(cph, X)
        ph.to_csv(DIR_TABLAS / f"supuesto_ph_modelo_{modelo}.csv", index=False)
        res["cox"][f"modelo_{modelo}"] = {"concordancia": float(cph.concordance_index_), "hr": _registros(hr),
                                          "ph": _registros(ph)}
        print(f"[{time.time() - t0:5.0f} s] Cox modelo {modelo}")
    ventanas = cox.hr_por_ventana(cox.matriz_modelo(muestra.sample(n=60_000, random_state=311), "B"), "B")
    ventanas.to_csv(DIR_TABLAS / "cox_hr_por_ventana.csv", index=False)
    res["cox"]["hr_por_ventana"] = _registros(ventanas)
    print(f"[{time.time() - t0:5.0f} s] HR por ventana de tiempo")

    # 5) Equidad territorial (O/E ajustado por tipo × descriptor)
    obs = equidad.marcar_resultado(df)
    esp = equidad.probabilidad_esperada(df, obs)
    eq_b = equidad.razon_oe(obs, esp, df["borough"].rename("borough"))
    # El mismo O/E a horizontes cortos: ¿la brecha está en las primeras horas o en los días?
    horizontes = []
    for etiqueta, dias in equidad.HORIZONTES.items():
        obs_h = equidad.marcar_resultado(df, dias)
        r = equidad.razon_oe(obs_h, equidad.probabilidad_esperada(df, obs_h), df["borough"].rename("borough"))
        horizontes.append(r.assign(horizonte=etiqueta, horizonte_dias=dias))
    eq_h = pd.concat(horizontes, ignore_index=True)
    eq_h.to_csv(DIR_TABLAS / "equidad_boroughs_horizontes.csv", index=False)
    eq_b.to_csv(DIR_TABLAS / "equidad_boroughs.csv", index=False)
    eq_z = equidad.razon_oe(obs, esp, df["zip"].rename("zip"), min_n=1_000)
    eq_z["significativo_fdr"] = equidad.benjamini_hochberg(eq_z["p_valor"].to_numpy())
    zip_borough = df.groupby("zip", observed=True)["borough"].agg(lambda s: s.mode().iat[0])
    eq_z["borough"] = eq_z["zip"].map(zip_borough).astype("string")
    eq_z = eq_z.sort_values("o_entre_e").reset_index(drop=True)
    eq_z.to_csv(DIR_TABLAS / "equidad_zip.csv", index=False)
    lentos = eq_z.loc[eq_z["significativo_fdr"] & eq_z["o_entre_e"].lt(1)]
    rapidos = eq_z.loc[eq_z["significativo_fdr"] & eq_z["o_entre_e"].gt(1)]
    res["equidad"] = {
        "horizonte_dias": equidad.HORIZONTE_DIAS,
        "boroughs": _registros(eq_b),
        "oe_por_horizonte": {b: dict(zip(g["horizonte"], g["o_entre_e"])) for b, g in eq_h.groupby("borough")},
        "n_zip_analizados": int(len(eq_z)),
        "n_zip_significativos": int(eq_z["significativo_fdr"].sum()),
        "n_zip_lentos": int(len(lentos)),
        "n_zip_rapidos": int(len(rapidos)),
        "pct_lentos_en_bronx": float(100 * lentos["borough"].eq("BRONX").mean()) if len(lentos) else None,
        "pct_rapidos_en_staten_island": float(100 * rapidos["borough"].eq("STATEN ISLAND").mean()) if len(rapidos) else None,
        "oe_zip_p05": float(eq_z["o_entre_e"].quantile(0.05)),
        "oe_zip_p95": float(eq_z["o_entre_e"].quantile(0.95)),
        "zip_mas_lentos": _registros(eq_z.head(5)[["zip", "borough", "n", "pct_cerradas_7d", "pct_esperado_7d", "o_entre_e"]]),
        "zip_mas_rapidos": _registros(eq_z.tail(5)[["zip", "borough", "n", "pct_cerradas_7d", "pct_esperado_7d", "o_entre_e"]]),
    }
    print(f"[{time.time() - t0:5.0f} s] equidad territorial")

    # 6) Evolución temporal
    mensual, por_agencia, resumen_t = evolucion(df, obs, esp)
    mensual.to_csv(DIR_TABLAS / "evolucion_mensual.csv", index=False)
    por_agencia.to_csv(DIR_TABLAS / "evolucion_agencias_anual.csv", index=False)
    res["evolucion"] = _limpio(resumen_t) | {"agencias": _registros(por_agencia)}
    print(f"[{time.time() - t0:5.0f} s] evolución temporal")

    res["tiempo_ejecucion_s"] = round(time.time() - t0)
    ARCHIVO_RESULTADOS.write_text(json.dumps(_limpio(res), indent=2, ensure_ascii=False), encoding="utf-8")

    DIR_FIGURAS.mkdir(parents=True, exist_ok=True)
    graficos.generar_todas()
    print(f"[{time.time() - t0:5.0f} s] figuras listas")
    return res


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sin-limpieza", action="store_true")
    ejecutar(parser.parse_args().sin_limpieza)


if __name__ == "__main__":
    main()
