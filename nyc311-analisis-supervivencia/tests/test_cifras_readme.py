"""Verifica que README.md y la guía citen exactamente las cifras de reports/ (sin desfases)."""

from __future__ import annotations

import json
import re

import pandas as pd

from nyc311.cifras_readme import documentos_esperados, duracion, n
from nyc311.config import DIR_REPORTS, DIR_TABLAS, RAIZ

README = (RAIZ / "README.md").read_text(encoding="utf-8")
GUIA = (RAIZ / "docs" / "GUIA_PASO_A_PASO.md").read_text(encoding="utf-8")
RES = json.loads((DIR_REPORTS / "resultados.json").read_text(encoding="utf-8"))


def test_readme_y_guia_coinciden_con_plantillas_y_resultados() -> None:
    """Si alguien edita el README a mano o cambian los resultados, esta prueba falla."""
    for destino, esperado in documentos_esperados().items():
        assert destino.read_text(encoding="utf-8") == esperado, (
            f"{destino.name} está desfasado: ejecuta `python -m nyc311.cifras_readme`"
        )
    assert "{{" not in README and "{{" not in GUIA
    assert "nan" not in README.lower().replace("financ", "")


def test_cifras_clave_del_readme_salen_de_reports() -> None:
    """Contrasta en el README las cifras centrales, leídas directamente de reports/ (no del contexto)."""
    g, cal = RES["global"], RES["calidad"]
    km = pd.read_csv(DIR_TABLAS / "km_agencias.csv").set_index("agencia")
    sesgo = pd.read_csv(DIR_TABLAS / "sesgo_corte_retrospectivo.csv").set_index("grupo")
    cox_b = pd.read_csv(DIR_TABLAS / "cox_modelo_B.csv").set_index("covariable")
    eq = pd.read_csv(DIR_TABLAS / "equidad_boroughs.csv").set_index("borough")

    esperadas = [
        n(cal["filas_limpias"], 0),
        n(cal["censuradas_abiertas"], 0),
        n(cal["cierre_antes_de_apertura"], 0),
        n(g["mediana_km_horas"], 1) + " horas",
        n(g["promedio_ingenuo_cerradas_dias"], 1) + " días",
        duracion(km.loc["NYPD", "mediana_km_dias"]),
        duracion(km.loc["TLC", "mediana_km_dias"]),
        duracion(km.loc["TLC", "mediana_ingenua_cerradas_dias"]),
        duracion(sesgo.loc["DPR", "mediana_ingenua_ficticio"]),
        duracion(sesgo.loc["DPR", "mediana_km_ficticio"]),
        duracion(sesgo.loc["DPR", "mediana_verdad"]),
        duracion(sesgo.loc["DOB", "mediana_verdad"]),
        f"HR {n(cox_b.loc['borough=BRONX', 'hr'], 2)}",
        f"O/E {n(eq.loc['STATEN ISLAND', 'o_entre_e'], 3)}",
        f"O/E {n(eq.loc['BRONX', 'o_entre_e'], 3)}",
    ]
    faltan = [cifra for cifra in esperadas if cifra not in README]
    assert not faltan, f"Cifras de reports/ ausentes en el README: {faltan}"


def test_hallazgos_del_readme_son_coherentes_con_los_datos() -> None:
    """Las afirmaciones cualitativas del README siguen siendo ciertas con los resultados actuales."""
    km = pd.read_csv(DIR_TABLAS / "km_agencias.csv").set_index("agencia")
    sesgo = pd.read_csv(DIR_TABLAS / "sesgo_corte_retrospectivo.csv").set_index("grupo")
    eq = pd.read_csv(DIR_TABLAS / "equidad_boroughs.csv").set_index("borough")
    ven = pd.read_csv(DIR_TABLAS / "cox_hr_por_ventana.csv")
    bronx = ven.loc[ven["covariable"].eq("borough=BRONX"), "hr"].to_numpy()
    # «NYPD cierra en horas; Parques y Edificios, en semanas»
    assert km.loc["NYPD", "mediana_km_dias"] < 1 / 6
    assert km.loc["DPR", "mediana_km_dias"] > 7 and km.loc["DOB", "mediana_km_dias"] > 7
    # «KM recupera la mediana real y la ingenua se queda corta» donde hay censura
    for ag in ["DOB", "DPR"]:
        assert sesgo.loc[ag, "mediana_ingenua_ficticio"] < 0.5 * sesgo.loc[ag, "mediana_verdad"]
        assert abs(sesgo.loc[ag, "mediana_km_ficticio"] / sesgo.loc[ag, "mediana_verdad"] - 1) < 0.05
    assert pd.isna(sesgo.loc["EDC", "mediana_km_ficticio"]) or sesgo.loc["EDC", "mediana_km_ficticio"] == float("inf")
    # «Staten Island es el único borough claramente más rápido de lo esperado; el resto a menos de 0,5 % de 1»
    boroughs = eq.loc[eq.index != "SIN DATO", "o_entre_e"]
    assert boroughs.idxmax() == "STATEN ISLAND" and boroughs["STATEN ISLAND"] > 1.01
    assert (boroughs.drop("STATEN ISLAND") - 1).abs().max() < 0.005
    # «el efecto del Bronx se invierte»: < 1 el primer día y > 1 pasados 30 días
    assert bronx[0] < 1 < bronx[-1]
    # «la brecha del Bronx es de horas, no de días»
    oe_h = RES["equidad"]["oe_por_horizonte"]["BRONX"]
    assert oe_h["1 h"] < 0.9 and abs(oe_h["1 día"] - 1) < 0.02
    # «el segundo año fue algo más lento», también ajustando por mezcla
    p1, p2 = sorted(RES["evolucion"]["periodos"].items())
    assert p2[1]["pct_cerradas_7d"] < p1[1]["pct_cerradas_7d"] and p2[1]["o_entre_e"] < p1[1]["o_entre_e"]


def test_guia_tiene_al_menos_8_preguntas_de_entrevista() -> None:
    preguntas = re.findall(r"^\*\*\d+\. .+\?\*\*$", GUIA, flags=re.MULTILINE)
    assert len(preguntas) >= 8


def test_sin_rutas_personales_en_documentos_y_reports() -> None:
    patron = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]|/c/Users/", re.IGNORECASE)
    archivos = [RAIZ / "README.md", RAIZ / "docs" / "GUIA_PASO_A_PASO.md", DIR_REPORTS / "resultados.json"]
    archivos += list((RAIZ / "notebooks").glob("*.ipynb"))
    for archivo in archivos:
        assert not patron.search(archivo.read_text(encoding="utf-8")), f"Ruta personal en {archivo.name}"
