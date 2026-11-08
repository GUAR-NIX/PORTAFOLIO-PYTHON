"""Verifica que README.md y la guía citen exactamente las cifras de reports/ (sin desfases)."""

from __future__ import annotations

import json
import re

import pandas as pd
import pytest

from empleo_enemdu.cifras_readme import construir_contexto, documentos_esperados, n
from empleo_enemdu.config import DIR_PROCESADOS, DIR_REPORTS, DIR_TABLAS, RAIZ

README = (RAIZ / "README.md").read_text(encoding="utf-8")
GUIA = (RAIZ / "docs" / "GUIA_PASO_A_PASO.md").read_text(encoding="utf-8")


def test_readme_y_guia_coinciden_con_plantillas_y_resultados() -> None:
    """Si alguien edita el README a mano o cambian los resultados, esta prueba falla."""
    for destino, esperado in documentos_esperados().items():
        actual = destino.read_text(encoding="utf-8")
        assert actual == esperado, (
            f"{destino.name} está desfasado: ejecuta `python -m empleo_enemdu.cifras_readme`"
        )
    assert "{{" not in README and "{{" not in GUIA


def test_cifras_clave_del_readme_salen_de_las_tablas() -> None:
    """Contrasta en el README las cifras que la revisión encontró desfasadas, leyéndolas de reports/."""
    prov = pd.read_csv(DIR_TABLAS / "indicadores_provincias_2025.csv").set_index("provincia")
    sub = pd.read_csv(DIR_TABLAS / "indicadores_subgrupos_2025.csv").set_index(["dimension", "categoria"])
    ramas = pd.read_csv(DIR_TABLAS / "indicadores_ramas_ciiu_2025.csv").set_index("rama_nombre")
    res = json.loads((DIR_REPORTS / "resultados.json").read_text(encoding="utf-8"))

    esperadas = [
        n(prov.loc["Galápagos", "informalidad_pct"], 2),
        n(prov.loc["Pichincha", "informalidad_pct"], 2),
        n(prov.loc["Morona Santiago", "informalidad_pct"], 2),
        n(sub.loc[("Sexo", "Hombre"), "empleo_adecuado_pct"], 2),
        n(sub.loc[("Sexo", "Mujer"), "empleo_adecuado_pct"], 2),
        n(sub.loc[("Autoidentificación étnica", "Indígena"), "informalidad_pct"], 2),
        n(sub.loc[("Autoidentificación étnica", "Indígena"), "empleo_adecuado_pct"], 2),
        n(sub.loc[("Autoidentificación étnica", "Mestizo/a"), "informalidad_pct"], 2),
        n(sub.loc[("Autoidentificación étnica", "Mestizo/a"), "empleo_adecuado_pct"], 2),
        n(ramas.loc["Construcción", "informalidad_pct"], 2),
        n(sub.loc[("Grupo de edad", "15 a 24 años"), "desempleo_pct"], 2),
    ]
    for modelo in res["mincer"]["modelos"].values():
        esperadas += [f"`{n(modelo['r2_ponderado'], 4)}`", n(modelo["n_observaciones"], 0)]
        esc = modelo["coeficientes"]["escolaridad"]
        esperadas += [f"`{n(esc['ee_cluster_upm'], 5)}`", f"{n(esc['razon_ee_cluster_vs_ingenuo'], 2)}x"]

    faltan = [cifra for cifra in esperadas if cifra not in README]
    assert not faltan, f"Cifras de reports/ ausentes en el README: {faltan}"


def test_readme_no_contiene_cifras_viejas_detectadas_en_la_revision() -> None:
    """Las cifras desfasadas que señaló la revisión no deben reaparecer."""
    viejas = ["0,2409", "0,3392", "55.661", "75.568", "27,8%", "32,5%", "79,6%", "41,5%", "31,0%", "75,3%", "71,6%"]
    presentes = [v for v in viejas if v in README]
    assert not presentes, f"Cifras desfasadas en el README: {presentes}"
    assert "exacta de 0,0" not in README and "300 DPI" not in README


def test_validacion_microdatos_2024_coincide_con_serie_oficial() -> None:
    """Recalcular 2024 con microdatos debe coincidir con la serie publicada (redondeo a 1 decimal)."""
    val = pd.read_csv(DIR_TABLAS / "validacion_microdatos_2024.csv")
    assert len(val) == 80
    assert val["coincide"].all()
    assert (val["estimacion_pct"].round(1) - val["serie_inec_pct"]).abs().max() <= 0.1 + 1e-9


def test_provincias_2025_coinciden_con_la_serie_oficial() -> None:
    """Las tasas provinciales propias coinciden con el tabulado oficial 2025 dentro de 0,1 pp."""
    serie = pd.read_csv(DIR_PROCESADOS / "serie_historica_2018_2025.csv")
    of = serie.loc[serie["anio"].eq(2025)].set_index(["indicador", "dominio"])["valor_pct"]
    prov = pd.read_csv(DIR_TABLAS / "indicadores_provincias_2025.csv")
    for ind, col in [("Sector informal", "informalidad_pct"), ("Empleo Adecuado/Pleno", "empleo_adecuado_pct")]:
        dif = (prov[col].round(1) - prov["provincia"].map(lambda p: of[(ind, p)])).abs()
        assert dif.max() <= 0.1 + 1e-9, f"{ind}: diferencia máxima {dif.max():.2f} pp"


def test_guia_tiene_al_menos_ocho_preguntas_con_respuesta() -> None:
    preguntas = re.findall(r"^### Pregunta \d+", GUIA, flags=re.MULTILINE)
    respuestas = re.findall(r"^> \*\*Respuesta:\*\*", GUIA, flags=re.MULTILINE)
    assert len(preguntas) >= 8
    assert len(respuestas) == len(preguntas)


@pytest.mark.parametrize(
    "ruta",
    [
        DIR_REPORTS / "resultados.json",
        DIR_REPORTS / "validacion_microdatos_2024.json",
        *sorted((RAIZ / "notebooks").glob("*.ipynb")),
        *sorted(DIR_TABLAS.glob("*.csv")),
        RAIZ / "README.md",
        *sorted((RAIZ / "docs").rglob("*.md")),
    ],
    ids=lambda p: p.name,
)
def test_salidas_sin_rutas_personales(ruta) -> None:
    """Ninguna salida versionada debe exponer rutas del equipo local (C:\\Users\\...)."""
    texto = ruta.read_text(encoding="utf-8")
    assert not re.search(r"[A-Za-z]:\\\\?Users|/Users/|/home/", texto), f"Ruta personal en {ruta.name}"


def test_contexto_refleja_las_80_celdas_coincidentes() -> None:
    contexto = construir_contexto()
    assert contexto["celdas_ok"] == contexto["celdas_total"] == "80"
