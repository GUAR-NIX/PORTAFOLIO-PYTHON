"""Verifica que README.es.md y la guía citen exactamente las cifras de reports/."""
from __future__ import annotations

import json
import re

import pandas as pd

from delitos_chicago.cifras_readme import documentos_esperados, n, s
from delitos_chicago.config import RAIZ, REPORTES

README = (RAIZ / "README.es.md").read_text(encoding="utf-8")
GUIA = (RAIZ / "docs" / "GUIA_PASO_A_PASO.md").read_text(encoding="utf-8")


def _json(nombre: str) -> dict:
    return json.loads((REPORTES / nombre).read_text(encoding="utf-8"))


def test_readme_y_guia_coinciden_con_plantillas_y_resultados() -> None:
    """Falla si alguien edita el README a mano o si cambian los resultados sin regenerarlo."""
    for destino, esperado in documentos_esperados().items():
        assert destino.read_text(encoding="utf-8") == esperado, (
            f"{destino.name} está desfasado: ejecuta `python -m delitos_chicago.cifras_readme`"
        )
    assert "{{" not in README and "{{" not in GUIA


def test_cifras_clave_salen_de_reports() -> None:
    """Contrasta en el README, leyéndolas directamente de reports/, las cifras clave."""
    res = _json("resultados.json")
    covid = res["temporal"]["covid"]
    caso = pd.read_csv(REPORTES / "control_calidad_renombres_2019_2024.csv").set_index("categoria")
    cambio = pd.read_csv(REPORTES / "cambio_porcentual_2019_2024.csv").set_index("tipo_primario")
    areas = pd.read_csv(REPORTES / "delitos_por_area_comunitaria.csv")
    pron = _json("evaluacion_pronostico.json")
    ganador = pron["metricas"][pron["ganador"]]
    gi = res["espacial"]["gi"]
    hora = res["temporal"]["patron_horario"]

    armonizada = caso.loc["CRIMINAL SEXUAL ASSAULT (armonizada)"]
    esperadas = [
        n(res["periodo_datos"]["registros_totales"]),
        # 1. Armonización: 1.754 → 1.747 (−0,4 %) y la categoría armonizada en la tabla de cambios
        f"{n(armonizada['conteo_2019'])} a {n(armonizada['conteo_2024'])} ({s(armonizada['cambio_pct'])} %)",
        f"| Agresión sexual criminal | {n(cambio.loc['CRIMINAL SEXUAL ASSAULT', 'conteo_2019'])} |",
        f"{s(cambio.loc['MOTOR VEHICLE THEFT', 'cambio_pct'])} %",
        # 2. Gi* y Jaccard
        f"**{n(gi['jaccard_consecutivo_promedio'], 2)}**",
        f"**{gi['celdas_hotspot_todos_los_anios']} celdas**",
        # 3. Serie interrumpida con IC
        f"**{s(covid['cambio_pct'])} %** (IC 95 %: {s(covid['cambio_inf_pct'])} a {s(covid['cambio_sup_pct'])} %)",
        # 4. Tasas anuales: el primero por tasa y el puesto de Austin
        f"**{areas.iloc[0]['nombre_area']}** ({n(areas.iloc[0]['tasa_anual_100k'])} por 100 mil al año)",
        f"la {int(areas.set_index('area_comunitaria').loc[25, 'puesto_tasa'])}.ª en tasa",
        # 6. Pronóstico: ganador, WAPE y cobertura del intervalo
        f"WAPE {n(ganador['WAPE_pct'], 2)} %",
        f"**{n(ganador['cobertura_pct'], 1)} %**",
        # 10. Una sola franja horaria
        f"**{hora['franja_pico_inicio']:02d}:00–{hora['franja_pico_fin']:02d}:00**",
    ]
    faltan = [cifra for cifra in esperadas if cifra not in README]
    assert not faltan, f"Cifras de reports/ ausentes en el README: {faltan}"
    assert areas.iloc[0]["puesto_tasa"] == 1


def test_no_quedan_afirmaciones_corregidas() -> None:
    """Afirmaciones de la versión anterior que la revisión encontró erróneas o sin respaldo."""
    viejas = [
        "muestra de 10.000 registros",  # la frase ocultaba que el CSV tiene 500
        "llave inteligente",  # atribución sin cita
        "pico entre las 15:00 y las 21:00",  # contradecía «18–20 h»
        "Delitos 2001–2026",  # totales con el año parcial
        "491.843",  # conteo acumulado de Austin usado como ranking
        "509.381",  # tasa acumulada 2001–2026
        "Polars",  # no se usa
        "+114,6 % |",  # el artefacto ya no aparece como resultado en la tabla
    ]
    presentes = [v for v in viejas if v in README or v in GUIA]
    assert not presentes, f"Afirmaciones corregidas que reaparecen: {presentes}"
    assert not re.search(r"[\U0001F300-\U0001FAFF]", README), "El README no usa emojis"


def test_sin_rutas_personales_en_salidas_versionadas() -> None:
    """Ningún archivo versionado del proyecto debe contener rutas de la máquina del autor."""
    patron = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+|/home/[a-z]+/")
    rutas = [*RAIZ.glob("notebooks/*.ipynb"), *REPORTES.glob("*.json"), *REPORTES.glob("*.csv"),
             RAIZ / "data" / "manifiesto_fuente.json", RAIZ / "README.es.md"]
    con_ruta = [p.name for p in rutas if patron.search(p.read_text(encoding="utf-8"))]
    assert not con_ruta, f"Rutas personales en: {con_ruta}"
