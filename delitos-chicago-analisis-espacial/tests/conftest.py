"""Configuración global y fixtures para el suite de pruebas de delitos de Chicago."""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon


@pytest.fixture
def df_delitos_sinteticos() -> pd.DataFrame:
    """Genera un DataFrame sintético con estructura idéntica a los datos limpios."""
    np.random.seed(42)
    n = 200
    fechas = pd.date_range("2020-01-01", periods=n, freq="D")

    tipos = ["THEFT", "BATTERY", "CRIMINAL DAMAGE", "NARCOTICS", "ASSAULT"]
    distritos = [1, 2, 3, 4, 11, 12, 17]
    areas = [1, 2, 8, 25, 32, 67, 77]

    df = pd.DataFrame({
        "id_delito": np.arange(1000, 1000 + n),
        "numero_caso": [f"JC{100000 + i}" for i in range(n)],
        "fecha": fechas,
        "cuadra": ["001XX N STATE ST"] * n,
        "codigo_iucr": ["0820"] * n,
        "tipo_primario": np.random.choice(tipos, n),
        "descripcion": ["$500 AND UNDER"] * n,
        "lugar": ["STREET"] * n,
        "arresto": np.random.choice([True, False], n, p=[0.25, 0.75]),
        "domestico": np.random.choice([True, False], n, p=[0.2, 0.8]),
        "beat": np.random.choice([111, 222, 333], n),
        "distrito": np.random.choice(distritos, n),
        "barrio_ward": np.random.randint(1, 50, n),
        "area_comunitaria": np.random.choice(areas, n),
        "codigo_fbi": ["06"] * n,
        "coord_x": np.random.uniform(1100000, 1200000, n),
        "coord_y": np.random.uniform(1800000, 1950000, n),
        "anio": fechas.year,
        "latitud": np.random.uniform(41.7, 42.0, n),
        "longitud": np.random.uniform(-87.8, -87.6, n),
    })
    return df


@pytest.fixture
def gdf_areas_sinteticas() -> gpd.GeoDataFrame:
    """Genera polígonos sintéticos para probar análisis espacial."""
    poly1 = Polygon([(-87.7, 41.8), (-87.6, 41.8), (-87.6, 41.9), (-87.7, 41.9)])
    poly2 = Polygon([(-87.7, 41.7), (-87.6, 41.7), (-87.6, 41.8), (-87.7, 41.8)])
    gdf = gpd.GeoDataFrame({
        "area_comunitaria": [1, 2],
        "nombre_area": ["Rogers Park", "West Ridge"],
        "geometry": [poly1, poly2],
    })
    return gdf
