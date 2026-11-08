"""Paginación, reintentos y reanudación de la descarga con respuestas grabadas de la API (sin red).

Las tres respuestas de `tests/datos/` se grabaron de la API real para marzo de 2025 con páginas de
2 filas (offset 0, 2 y 4); la última se recortó a 1 fila para simular el final del mes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest
import requests

from nyc311.config import COLUMNAS
from nyc311.descarga import (
    consolidar,
    descargar_mes,
    filtro_mes,
    leer_csv_pagina,
    meses_de_ventana,
    obtener_con_reintentos,
    parametros_pagina,
)

DATOS = Path(__file__).parent / "datos"


class Respuesta:
    def __init__(self, texto: str, estado: int = 200) -> None:
        self.text = texto
        self.status_code = estado

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class SesionGrabada:
    """Devuelve la respuesta grabada según `$offset`; registra cada llamada y puede fallar antes."""

    def __init__(self, fallos_previos: int = 0) -> None:
        self.llamadas: list[dict] = []
        self.fallos_previos = fallos_previos

    def get(self, url, params=None, timeout=None):
        self.llamadas.append(dict(params))
        if self.fallos_previos:
            self.fallos_previos -= 1
            return Respuesta("Service Unavailable", 503)
        ruta = DATOS / f"respuesta_2025-03_offset{params['$offset']}.csv"
        return Respuesta(ruta.read_text(encoding="utf-8"))


def sin_espera(_segundos: float) -> None:
    pass


def test_parametros_soql() -> None:
    p = parametros_pagina("2025-12", 100_000, 50_000)
    assert p["$where"] == "created_date >= '2025-12-01T00:00:00' AND created_date < '2026-01-01T00:00:00'"
    assert p["$order"] == "unique_key"  # orden estable: sin él el offset repite o salta filas
    assert p["$limit"] == "50000" and p["$offset"] == "100000"
    assert p["$select"].split(",") == COLUMNAS
    assert filtro_mes("2024-02").endswith("'2024-03-01T00:00:00'")
    assert meses_de_ventana("2024-11", "2025-02") == ["2024-11", "2024-12", "2025-01", "2025-02"]


def test_pagina_hasta_la_ultima_incompleta(tmp_path: Path) -> None:
    sesion = SesionGrabada()
    filas = descargar_mes("2025-03", sesion, tmp_path, tamano=2, dormir=sin_espera)
    assert filas == 5
    assert [c["$offset"] for c in sesion.llamadas] == ["0", "2", "4"]
    paginas = sorted((tmp_path / "2025-03").glob("pagina_*.parquet"))
    assert [pq.read_metadata(p).num_rows for p in paginas] == [2, 2, 1]
    marca = json.loads((tmp_path / "2025-03" / "_completo.json").read_text(encoding="utf-8"))
    assert marca["filas"] == 5 and marca["paginas"] == 3


def test_reanuda_sin_repetir_paginas(tmp_path: Path) -> None:
    descargar_mes("2025-03", SesionGrabada(), tmp_path, tamano=2, dormir=sin_espera)
    # Simula un apagón: se perdió la última página y la marca de mes completo
    (tmp_path / "2025-03" / "_completo.json").unlink()
    (tmp_path / "2025-03" / "pagina_00002.parquet").unlink()
    sesion = SesionGrabada()
    assert descargar_mes("2025-03", sesion, tmp_path, tamano=2, dormir=sin_espera) == 5
    assert [c["$offset"] for c in sesion.llamadas] == ["4"]
    # Con la marca presente no se hace ninguna petición
    sesion = SesionGrabada()
    assert descargar_mes("2025-03", sesion, tmp_path, tamano=2, dormir=sin_espera) == 5
    assert sesion.llamadas == []


def test_reintenta_ante_503(tmp_path: Path) -> None:
    esperas: list[float] = []
    sesion = SesionGrabada(fallos_previos=2)
    texto = obtener_con_reintentos(sesion, "http://x", parametros_pagina("2025-03", 0, 2), dormir=esperas.append)
    assert texto.startswith('"unique_key"')
    assert esperas == [2.0, 4.0]  # espera exponencial


def test_falla_tras_agotar_reintentos() -> None:
    with pytest.raises(RuntimeError, match="Fallaron 3 intentos"):
        obtener_con_reintentos(SesionGrabada(fallos_previos=10), "http://x", parametros_pagina("2025-03", 0, 2),
                               reintentos=3, dormir=sin_espera)


def test_csv_a_arrow_y_consolidado(tmp_path: Path) -> None:
    tabla = leer_csv_pagina((DATOS / "respuesta_2025-03_offset0.csv").read_text(encoding="utf-8"))
    assert tabla.column_names == COLUMNAS and tabla.num_rows == 2
    # Columna ausente en el CSV (Socrata omite las que vienen todas nulas): se completa con nulos
    sin_borough = "unique_key,created_date\n1,2025-03-01T00:00:00.000\n"
    t2 = leer_csv_pagina(sin_borough)
    assert t2.column("borough").null_count == 1

    descargar_mes("2025-03", SesionGrabada(), tmp_path / "paginas", tamano=2, dormir=sin_espera)
    destino = tmp_path / "crudo.parquet"
    assert consolidar(["2025-03"], tmp_path / "paginas", destino) == 5
    df = pq.read_table(destino).to_pandas()
    assert df["unique_key"].is_unique
    assert str(df["agency"].dtype) == "category"
    with pytest.raises(RuntimeError, match="sin terminar"):
        consolidar(["2025-04"], tmp_path / "paginas", destino)
