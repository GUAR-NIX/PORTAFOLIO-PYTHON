"""Fixtures compartidos para la suite de pruebas de PYTHON_06_empleo_enemdu."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from empleo_enemdu.config import DIR_MUESTRA, DIR_PROCESADOS, DIR_REPORTS, DIR_TABLAS


@pytest.fixture(scope="session")
def df_muestra() -> pd.DataFrame:
    """Carga la muestra versionada de 120 UPM en data/muestra/muestra_enemdu_2025.parquet."""
    ruta = DIR_MUESTRA / "muestra_enemdu_2025.parquet"
    if not ruta.exists():
        pytest.skip("No hay muestra en data/muestra/ (se omiten las pruebas que la usan)")
    return pd.read_parquet(ruta)


@pytest.fixture(scope="session")
def resultados_json() -> dict[str, Any]:
    """Carga el archivo reports/resultados.json generado por el pipeline."""
    return json.loads((DIR_REPORTS / "resultados.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def df_reconciliacion() -> pd.DataFrame:
    """Carga la tabla de reconciliación contra el INEC."""
    return pd.read_csv(DIR_TABLAS / "reconciliacion_inec_2025.csv")


@pytest.fixture(scope="session")
def df_provincias() -> pd.DataFrame:
    """Carga la tabla de indicadores de las 24 provincias."""
    return pd.read_csv(DIR_TABLAS / "indicadores_provincias_2025.csv")


@pytest.fixture(scope="session")
def df_serie_historica() -> pd.DataFrame:
    """Carga la serie histórica oficial 2018-2025."""
    return pd.read_csv(DIR_PROCESADOS / "serie_historica_2018_2025.csv")
