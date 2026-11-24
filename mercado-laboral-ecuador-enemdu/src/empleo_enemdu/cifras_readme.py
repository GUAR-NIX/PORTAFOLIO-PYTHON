"""Genera README.es.md y docs/GUIA_PASO_A_PASO.md a partir de plantillas y de los resultados en reports/.

Ninguna cifra de esos documentos se escribe a mano: las plantillas de `scripts/plantillas/` contienen
marcadores `{{clave}}` que este módulo rellena leyendo `reports/resultados.json`, `reports/tablas/*.csv`,
la serie oficial del INEC y la validación con microdatos 2024. Así el texto no puede desfasarse de
los resultados; la prueba `tests/test_cifras_readme.py` falla si alguien edita el README a mano.

Uso:
    python -m empleo_enemdu.cifras_readme             # regenera README.es.md y la guía
    python -m empleo_enemdu.cifras_readme --verificar # solo comprueba (código 1 si hay desfase)
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from empleo_enemdu.config import DIR_PROCESADOS, DIR_REPORTS, RAIZ

DIR_PLANTILLAS = RAIZ / "scripts" / "plantillas"
DOCUMENTOS: dict[str, Path] = {
    "README.md": RAIZ / "README.es.md",
    "GUIA_PASO_A_PASO.md": RAIZ / "docs" / "GUIA_PASO_A_PASO.md",
}
_MARCADOR = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")

# Indicadores de la tabla de reconciliación del README (mismo orden que la figura 01)
INDICADORES_TABLA = [
    "Empleo Adecuado/Pleno",
    "Subempleo",
    "Otro Empleo no pleno",
    "Empleo no Remunerado",
    "Desempleo",
    "Sector informal",
    "Empleo Bruto",
    "Participación Global",
]
ETIQUETA_INDICADOR = {
    "Sector informal": "Sector informal (% ocupados)",
    "Empleo Bruto": "Empleo Bruto (% PET)",
    "Participación Global": "Participación Global (% PET)",
}


def n(valor: float, decimales: int = 1) -> str:
    """Formato numérico es-EC: punto de miles y coma decimal (334.786 · 37,1)."""
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def con_signo(valor: float, decimales: int = 1) -> str:
    """Como `n`, pero con signo explícito (+4,7 / -3,9)."""
    return ("+" if valor >= 0 else "") + n(valor, decimales)


def potencia_diez(p: float) -> str:
    """Expresa un p-valor muy pequeño como «1,5 × 10⁻⁵⁴»."""
    if p <= 0:
        return "0"
    exponente = math.floor(math.log10(p))
    mantisa = p / 10**exponente
    superindices = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")
    return f"{n(mantisa, 1)} × 10{str(exponente).translate(superindices)}"


def _cargar_fuentes(dir_reports: Path, dir_procesados: Path) -> dict[str, Any]:
    dir_tablas = dir_reports / "tablas"
    return {
        "res": json.loads((dir_reports / "resultados.json").read_text(encoding="utf-8")),
        "val24": json.loads((dir_reports / "validacion_microdatos_2024.json").read_text(encoding="utf-8")),
        "rec": pd.read_csv(dir_tablas / "reconciliacion_inec_2025.csv"),
        "prov": pd.read_csv(dir_tablas / "indicadores_provincias_2025.csv"),
        "sub": pd.read_csv(dir_tablas / "indicadores_subgrupos_2025.csv"),
        "ramas": pd.read_csv(dir_tablas / "indicadores_ramas_ciiu_2025.csv"),
        "cuant": pd.read_csv(dir_tablas / "brecha_cuantilica_genero_2025.csv"),
        "serie": pd.read_csv(dir_procesados / "serie_historica_2018_2025.csv"),
    }


def tabla_reconciliacion(rec: pd.DataFrame) -> str:
    """Tabla markdown de los 8 indicadores nacionales frente al tabulado oficial del INEC."""
    tot = rec.loc[rec["dominio"].eq("Total")].set_index("indicador").loc[INDICADORES_TABLA]
    filas = [
        "| Indicador nacional (ENEMDU 2025) | Calculado (%) | Oficial INEC (%) | Dif. (pp, a 1 decimal) "
        "| Sin ponderar (%) | Sesgo sin `fexp` (pp) | EE complejo (%) | EE oficial (%) | EE MAS ingenuo (%) "
        "| `DEFT` | `DEFF` | IC 95 % complejo |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for ind, f in tot.iterrows():
        filas.append(
            f"| **{ETIQUETA_INDICADOR.get(ind, ind)}** | **{n(f['estimacion_pct'])}** "
            f"| **{n(f['indicador_oficial_pct'])}** | `{n(f['dif_indicador_pp'])}` "
            f"| {n(f['sin_ponderar_pct'])} | `{con_signo(f['sesgo_sin_ponderar_pp'])}` "
            f"| {n(f['ee_complejo_pct'], 2)} | {n(f['ee_oficial_pct'])} | {n(f['ee_mas_pct'], 2)} "
            f"| **{n(f['deft'], 2)}x** | {n(f['deff'], 2)} "
            f"| `[{n(f['ic95_inf_pct'])}; {n(f['ic95_sup_pct'])}]` |"
        )
    return "\n".join(filas)


def tabla_mincer(mincer: dict[str, Any]) -> str:
    """Tabla markdown de las 5 especificaciones de Mincer leída de resultados.json."""
    modelos = mincer["modelos"]
    m2 = modelos["m2_formalidad"]["coeficientes"]
    hallazgos = {
        "m1_base": "Retorno bruto de un año de escolaridad",
        "m2_formalidad": (
            f"Informal {con_signo(m2['informal']['efecto_porcentual'], 2)} % · "
            f"afiliado IESS {con_signo(m2['afiliado_seguro']['efecto_porcentual'], 2)} %"
        ),
        "m3_completo": "Retorno dentro de la misma provincia y rama económica",
        "m4_sector_formal": "Retorno dentro del sector formal",
        "m5_sector_informal": "La escolaridad se remunera poco en la informalidad",
    }
    filas = [
        "| Especificación (WLS con `fexp`, EE agrupados por UPM) | n | $\\hat{\\beta}_{\\text{esc}}$ "
        "| Retorno por año | $\\text{EE}_{\\text{cluster}}$ | $\\text{EE}_{\\text{WLS}}$ | Razón EE "
        "| $R^2$ ponderado | Lectura |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ]
    for clave, mod in modelos.items():
        esc = mod["coeficientes"]["escolaridad"]
        filas.append(
            f"| **M{mod['modelo']}** | {n(mod['n_observaciones'], 0)} | `{n(esc['beta'], 5)}` "
            f"| **{con_signo(esc['efecto_porcentual'], 2)} %** | `{n(esc['ee_cluster_upm'], 5)}` "
            f"| `{n(esc['ee_ingenuo_wls'], 5)}` | {n(esc['razon_ee_cluster_vs_ingenuo'], 2)}x "
            f"| `{n(mod['r2_ponderado'], 4)}` | {hallazgos.get(clave, '')} |"
        )
    return "\n".join(filas)


def construir_contexto(
    dir_reports: Path = DIR_REPORTS,
    dir_procesados: Path = DIR_PROCESADOS,
) -> dict[str, str]:
    """Devuelve el diccionario clave → texto con todas las cifras citadas en los documentos."""
    f = _cargar_fuentes(dir_reports, dir_procesados)
    res, rec, prov, sub, ramas, cuant, serie, val24 = (
        f["res"], f["rec"], f["prov"], f["sub"], f["ramas"], f["cuant"], f["serie"], f["val24"]
    )
    c: dict[str, str] = {}

    # Calidad de datos y diseño muestral
    cal = res["calidad_y_diseno"]
    cen = cal["centinelas_detectados"]
    c |= {
        "personas": n(cal["filas_totales_personas"], 0),
        "hogares": n(cal["hogares_unicos"], 0),
        "upm": n(cal["upm_unicas"], 0),
        "estratos": n(cal["estratos_unicos"], 0),
        "poblacion": n(cal["poblacion_total_expandida"], 0),
        "pet": n(cal["pet_expandida"], 0),
        "pea": n(cal["pea_expandida"], 0),
        "ocupados": n(cal["ocupados_expandidos"], 0),
        "ingrl_999999": n(cen["ingrl_999999_no_informa"], 0),
        "ingrl_menos1": n(cen["ingrl_menos_1_sin_ingreso"], 0),
        "media_cruda": n(cen["media_ingrl_cruda_sin_limpiar_usd"], 2),
        "media_limpia": n(cen["media_ingrl_limpia_ponderada_usd"], 2),
        "factor_distorsion": n(cen["factor_distorsion_centinela"], 1),
        "tiempo_pipeline": n(res["tiempo_ejecucion_seg"], 0),
    }

    # Reconciliación con el tabulado oficial 2025
    resu = res["resumen_reconciliacion"]
    tot = rec.loc[rec["dominio"].eq("Total")].set_index("indicador")
    deft_tabla = tot.loc[INDICADORES_TABLA, "deft"]
    c |= {
        "celdas_ok": str(resu["celdas_reconciliadas_ok"]),
        "celdas_total": str(resu["celdas_evaluadas"]),
        "dif_max_ind": n(resu["error_max_indicador_pp"], 1),
        "dif_max_ee": n(resu["error_max_ee_pp"], 1),
        "deft_min": n(deft_tabla.min(), 2),
        "deft_max": n(deft_tabla.max(), 2),
        "tabla_reconciliacion": tabla_reconciliacion(rec),
        "adec_nac": n(tot.loc["Empleo Adecuado/Pleno", "estimacion_pct"]),
        "adec_deft": n(tot.loc["Empleo Adecuado/Pleno", "deft"], 2),
        "adec_deff": n(tot.loc["Empleo Adecuado/Pleno", "deff"], 2),
        "inf_nac": n(tot.loc["Sector informal", "estimacion_pct"]),
        "inf_deft": n(tot.loc["Sector informal", "deft"], 2),
        "inf_deff": n(tot.loc["Sector informal", "deff"], 2),
        "desempleo_nac": n(tot.loc["Desempleo", "estimacion_pct"]),
    }

    # Serie publicada por el INEC
    nac = serie.loc[serie["dominio"].eq("Total")].pivot_table(index="anio", columns="indicador", values="valor_pct")
    anios = sorted(int(a) for a in nac.index)
    faltan = [a for a in range(anios[0], anios[-1] + 1) if a not in anios]
    c |= {
        "serie_anio_ini": str(anios[0]),
        "serie_anio_fin": str(anios[-1]),
        "serie_anios_faltan": ", ".join(str(a) for a in faltan) if faltan else "ninguno",
        "serie_n_anios": str(len(anios)),
        "inf_serie_ini": n(nac.loc[anios[0], "Sector informal"]),
        "inf_serie_fin": n(nac.loc[anios[-1], "Sector informal"]),
        "inf_serie_cambio": con_signo(nac.loc[anios[-1], "Sector informal"] - nac.loc[anios[0], "Sector informal"]),
        "inf_serie_max": n(nac["Sector informal"].max()),
        "inf_serie_max_anio": str(int(nac["Sector informal"].idxmax())),
        "des_serie_ini": n(nac.loc[anios[0], "Desempleo"]),
        "adec_serie_ini": n(nac.loc[anios[0], "Empleo Adecuado/Pleno"]),
    }

    # Validación con microdatos 2024
    v_nac = val24["nacional"]
    c |= {
        "v24_ok": str(val24["celdas_coinciden"]),
        "v24_total": str(val24["celdas_comparadas"]),
        "v24_dif": n(val24["dif_max_abs_pp"], 1),
        "v24_personas": n(val24["personas"], 0),
        "v24_upm": n(val24["upm"], 0),
        "v24_inf_calc": n(v_nac["Sector informal"]["calculado_pct"], 2),
        "v24_inf_serie": n(v_nac["Sector informal"]["serie_inec_pct"]),
        "v24_adec_calc": n(v_nac["Empleo Adecuado/Pleno"]["calculado_pct"], 2),
        "v24_adec_serie": n(v_nac["Empleo Adecuado/Pleno"]["serie_inec_pct"]),
        "v24_des_calc": n(v_nac["Desempleo"]["calculado_pct"], 2),
        "v24_des_serie": n(v_nac["Desempleo"]["serie_inec_pct"]),
    }

    # Subgrupos (área, edad, etnia, sexo, instrucción)
    sg = sub.set_index(["dimension", "categoria"])
    rural, urb = sg.loc[("Área", "Rural")], sg.loc[("Área", "Urbana")]
    jov = sg.loc[("Grupo de edad", "15 a 24 años")]
    indig, mest = sg.loc[("Autoidentificación étnica", "Indígena")], sg.loc[("Autoidentificación étnica", "Mestizo/a")]
    sup = sg.loc[("Nivel de instrucción", "Superior")]
    bas = sg.loc[("Nivel de instrucción", "Educación Básica")]
    c |= {
        "rural_inf": n(rural["informalidad_pct"]),
        "rural_adec": n(rural["empleo_adecuado_pct"]),
        "urb_inf": n(urb["informalidad_pct"]),
        "urb_adec": n(urb["empleo_adecuado_pct"]),
        "jov_des": n(jov["desempleo_pct"], 2),
        "jov_adec": n(jov["empleo_adecuado_pct"]),
        "jov_inf": n(jov["informalidad_pct"]),
        "jov_nr": n(jov["no_remunerado_pct"]),
        "jov_n": n(jov["n_muestral_pea"], 0),
        "jov_razon": n(jov["desempleo_pct"] / tot.loc["Desempleo", "estimacion_pct"], 1),
        "indig_inf": n(indig["informalidad_pct"], 2),
        "indig_adec": n(indig["empleo_adecuado_pct"], 2),
        "indig_nr": n(indig["no_remunerado_pct"], 2),
        "indig_ing": n(indig["ingreso_medio_usd"], 2),
        "mest_inf": n(mest["informalidad_pct"], 2),
        "mest_adec": n(mest["empleo_adecuado_pct"], 2),
        "mest_ing": n(mest["ingreso_medio_usd"], 2),
        "sup_adec": n(sup["empleo_adecuado_pct"]),
        "bas_adec": n(bas["empleo_adecuado_pct"]),
    }

    # Contraste de género en empleo adecuado (con covarianza intra-UPM)
    gen = next(x for x in res["contrastes_hipotesis"] if x["contraste"].startswith("Empleo adecuado: Hombre"))
    c |= {
        "h_adec": n(gen["tasa_a_pct"], 2),
        "m_adec": n(gen["tasa_b_pct"], 2),
        "gen_dif": con_signo(gen["diferencia_pp"], 2),
        "gen_ee": n(gen["ee_complejo_pp"], 2),
        "gen_ee_indep": n(gen["ee_independiente_pp"], 2),
        "gen_t": n(gen["estadistico_t"], 2),
        "gen_p": potencia_diez(gen["p_valor"]),
        "gen_ic": f"[{n(gen['ic95_inf_pp'], 2)}; {n(gen['ic95_sup_pp'], 2)}]",
    }

    # Provincias: extremos de informalidad y empleo adecuado
    p_inf = prov.sort_values("informalidad_pct").reset_index(drop=True)
    p_adec = prov.sort_values("empleo_adecuado_pct", ascending=False).reset_index(drop=True)
    for i in range(2):
        c[f"prov_inf_min{i + 1}"] = p_inf.loc[i, "provincia"]
        c[f"prov_inf_min{i + 1}_v"] = n(p_inf.loc[i, "informalidad_pct"], 2)
    for i in range(3):
        fila = p_inf.iloc[-(i + 1)]
        c[f"prov_inf_max{i + 1}"] = fila["provincia"]
        c[f"prov_inf_max{i + 1}_v"] = n(fila["informalidad_pct"], 2)
    for i in range(2):
        c[f"prov_adec_max{i + 1}"] = p_adec.loc[i, "provincia"]
        c[f"prov_adec_max{i + 1}_v"] = n(p_adec.loc[i, "empleo_adecuado_pct"], 2)
        fila = p_adec.iloc[-(i + 1)]
        c[f"prov_adec_min{i + 1}"] = fila["provincia"]
        c[f"prov_adec_min{i + 1}_v"] = n(fila["empleo_adecuado_pct"], 2)
    prov_serie = serie.loc[serie["anio"].eq(anios[-1])].set_index(["indicador", "dominio"])["valor_pct"]
    dif_prov = [
        abs(round(fila[col], 1) - prov_serie[(ind, fila["provincia"])])
        for _, fila in prov.iterrows()
        for ind, col in [("Sector informal", "informalidad_pct"), ("Empleo Adecuado/Pleno", "empleo_adecuado_pct")]
    ]
    c["prov_dif_max"] = n(max(dif_prov), 1)

    # Ramas CIIU
    rm = ramas.set_index("rama_nombre")
    agri = rm.loc["Agricultura, ganadería, caza y silvicultura y pesca"]
    cons = rm.loc["Construcción"]
    adm = rm.loc["Administración pública y defensa; planes de seguridad social"]
    ens = rm.loc["Enseñanza"]
    c |= {
        "agri_inf": n(agri["informalidad_pct"], 2),
        "agri_med": n(agri["ingreso_mediano_usd"], 0),
        "agri_part": n(agri["participacion_ocupados_pct"]),
        "cons_inf": n(cons["informalidad_pct"], 2),
        "adm_inf": n(adm["informalidad_pct"], 2),
        "adm_med": n(adm["ingreso_mediano_usd"], 0),
        "ens_inf": n(ens["informalidad_pct"], 2),
        "ens_med": n(ens["ingreso_mediano_usd"], 0),
    }

    # Ingresos por sector y SBU
    ing = res["ingresos_por_sector_2025"]
    c |= {
        "inf_bajo_sbu": n(ing["sector_informal"]["bajo_sbu_pct"], 1),
        "for_bajo_sbu": n(ing["sector_formal"]["bajo_sbu_pct"], 1),
        "inf_mediana": n(ing["sector_informal"]["ingreso_mediano_usd"], 0),
        "for_mediana": n(ing["sector_formal"]["ingreso_mediano_usd"], 0),
    }

    # Mincer
    mincer = res["mincer"]
    mod = mincer["modelos"]
    b1 = mod["m1_base"]["coeficientes"]["escolaridad"]
    b2 = mod["m2_formalidad"]["coeficientes"]["escolaridad"]
    dip = {d["codigo"]: d for d in mincer["efecto_diploma"]}
    basica = dip["2_Basica_Primaria"]
    c |= {
        "tabla_mincer": tabla_mincer(mincer),
        "mincer_n": n(mincer["n_muestra_mincer"], 0),
        "mincer_upm": n(mod["m1_base"]["n_upm_clusters"], 0),
        "mincer_m1": n(b1["efecto_porcentual"], 2),
        "mincer_m2": n(b2["efecto_porcentual"], 2),
        "mincer_m3": n(mod["m3_completo"]["coeficientes"]["escolaridad"]["efecto_porcentual"], 2),
        "mincer_m4": n(mod["m4_sector_formal"]["coeficientes"]["escolaridad"]["efecto_porcentual"], 2),
        "mincer_m5": n(mod["m5_sector_informal"]["coeficientes"]["escolaridad"]["efecto_porcentual"], 2),
        "mincer_m1_razon": n(b1["razon_ee_cluster_vs_ingenuo"], 2),
        "mincer_canal_formalidad": n((b1["beta"] - b2["beta"]) / b1["beta"] * 100.0, 0),
        "mincer_informal": con_signo(mod["m2_formalidad"]["coeficientes"]["informal"]["efecto_porcentual"], 2),
        "mincer_iess": con_signo(mod["m2_formalidad"]["coeficientes"]["afiliado_seguro"]["efecto_porcentual"], 2),
        "mincer_exp_pico": n(mincer["experiencia_pico_anios"], 1),
        "dip_basica": con_signo(basica["premio_salarial_pct"], 2),
        "dip_basica_signif": (
            "no significativo al 95 %" if basica["ic95_inf_pct"] <= 0 <= basica["ic95_sup_pct"] else "significativo al 95 %"
        ),
        "dip_bach": con_signo(dip["3_Bachillerato_Secundaria"]["premio_salarial_pct"], 2),
        "dip_tec": con_signo(dip["4_Superior_Tecnica"]["premio_salarial_pct"], 2),
        "dip_univ": con_signo(dip["5_Superior_Universitaria"]["premio_salarial_pct"], 2),
        "dip_posgrado": con_signo(dip["6_Posgrado"]["premio_salarial_pct"], 2),
    }

    # Oaxaca-Blinder
    oax = res["oaxaca_blinder"]
    desc, ro = oax["descriptivos_ocupados"], oax["resumen_oaxaca"]
    comp = {x["componente"]: x for x in oax["componentes"]}
    comp_esc = next(v for k, v in comp.items() if k.startswith("Escolaridad"))
    comp_for = next(v for k, v in comp.items() if k.startswith("Formalidad"))

    def _ic(limites: list[float]) -> str:
        return f"[{n(limites[0], 4)}; {n(limites[1], 4)}]"

    c |= {
        "oax_n_h": n(oax["n_hombres"], 0),
        "oax_n_m": n(oax["n_mujeres"], 0),
        "ing_h": n(desc["ingreso_mensual_hombre_usd"], 2),
        "ing_m": n(desc["ingreso_mensual_mujer_usd"], 2),
        "brecha_mensual": n(desc["brecha_mensual_bruta_pct"], 2),
        "horas_h": n(desc["horas_semana_hombre"], 1),
        "horas_m": n(desc["horas_semana_mujer"], 1),
        "esc_h": n(desc["escolaridad_media_hombre"], 2),
        "esc_m": n(desc["escolaridad_media_mujer"], 2),
        "brecha_log": n(ro["brecha_log_total"], 4),
        "brecha_log_pct": n(ro["brecha_pct"], 2),
        "dot_log": n(ro["dotaciones_explicada_log"], 4),
        "dot_pct": n(ro["dotaciones_explicada_pct"], 2),
        "dot_pct_abs": n(abs(ro["dotaciones_explicada_pct"]), 2),
        "dot_ic": _ic(ro["ic95_dotaciones_log"]),
        "ret_log": con_signo(ro["retornos_no_explicada_log"], 4),
        "ret_pct": con_signo(ro["retornos_no_explicada_pct"], 2),
        "ret_ic": _ic(ro["ic95_retornos_log"]),
        "dot_esc_log": n(comp_esc["dotaciones_log"], 4),
        "dot_esc_pp": n(comp_esc["dotaciones_pct_aprox"], 2),
        "dot_for_pp": n(comp_for["dotaciones_pct_aprox"], 2),
    }

    # Brecha cuantílica
    q = cuant.set_index(["sector", "percentil"])
    inf10 = q.loc[("Sector informal", 10)]
    c |= {
        "q_inf_p10": n(inf10["brecha_hora_pct"], 1),
        "q_inf_p10_h": n(inf10["salario_hora_hombre_usd"], 2),
        "q_inf_p10_m": n(inf10["salario_hora_mujer_usd"], 2),
        "q_inf_p25": n(q.loc[("Sector informal", 25), "brecha_hora_pct"], 1),
        "q_for_p30": n(q.loc[("Sector formal", 30), "brecha_hora_pct"], 1),
        "q_for_p50": n(q.loc[("Sector formal", 50), "brecha_hora_pct"], 1),
        "q_for_p10": n(q.loc[("Sector formal", 10), "brecha_hora_pct"], 1),
    }

    # Desigualdad y pobreza
    des = res["desigualdad_y_pobreza"]
    pc = des["ingreso_per_capita_hogar"]
    ofi = des["referencia_oficial_inec"]
    pob = {x["condicion_laboral"]: x for x in des["pobreza_por_condicion_laboral"]}
    sim = des["simulacion_contrafactual_sbu"]
    c |= {
        "gini": n(pc["gini"], 3),
        "gini_oficial": n(ofi["gini_oficial"], 3),
        "gini_laboral": n(des["ingreso_laboral_ocupados"]["gini"], 3),
        "palma": n(pc["indice_palma"], 2),
        "d10": n(pc["participacion_d10_pct"], 2),
        "d1_4": n(pc["participacion_d1_a_d4_pct"], 2),
        "pobreza_calc": n(sim["tasa_pobreza_actual_pct"], 2),
        "pobreza_oficial": n(ofi["pobreza_oficial_pct"], 1),
        "pob_adec": n(pob["Empleo adecuado/pleno"]["pobreza_pct"], 2),
        "pob_sub": n(pob["Subempleo"]["pobreza_pct"], 2),
        "pob_inf": n(pob["Sector informal (ocupados)"]["pobreza_pct"], 2),
        "pob_nr": n(pob["Empleo no remunerado"]["pobreza_pct"], 2),
        "pob_des": n(pob["Desempleo"]["pobreza_pct"], 2),
        "sim_contra": n(sim["tasa_pobreza_contrafactual_pct"], 2),
        "sim_red": n(sim["reduccion_pobreza_pp"], 2),
    }
    return c


def renderizar(plantilla: str, contexto: dict[str, str]) -> str:
    """Sustituye los marcadores `{{clave}}`; falla si alguno no existe en el contexto."""
    faltan = sorted({m for m in _MARCADOR.findall(plantilla) if m not in contexto})
    if faltan:
        raise KeyError(f"Marcadores sin valor en el contexto: {faltan}")
    return _MARCADOR.sub(lambda m: contexto[m.group(1)], plantilla)


def documentos_esperados(contexto: dict[str, str] | None = None) -> dict[Path, str]:
    """Texto que deberían tener README.es.md y la guía según los resultados actuales."""
    contexto = contexto or construir_contexto()
    return {
        destino: renderizar((DIR_PLANTILLAS / nombre).read_text(encoding="utf-8"), contexto)
        for nombre, destino in DOCUMENTOS.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenera README y guía con las cifras de reports/.")
    parser.add_argument("--verificar", action="store_true", help="Solo comprueba; no escribe archivos.")
    args = parser.parse_args()

    desfasados = []
    for destino, texto in documentos_esperados().items():
        actual = destino.read_text(encoding="utf-8") if destino.exists() else ""
        if actual == texto:
            continue
        if args.verificar:
            desfasados.append(destino.relative_to(RAIZ).as_posix())
        else:
            destino.write_text(texto, encoding="utf-8")
            print(f"Actualizado {destino.relative_to(RAIZ).as_posix()}")
    if desfasados:
        print(f"Documentos desfasados respecto a reports/: {desfasados}")
        sys.exit(1)
    if args.verificar:
        print("README y guía coinciden con reports/.")


if __name__ == "__main__":
    main()
