import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture
def diario_sintetico() -> pd.DataFrame:
    """Una ciudad inventada, 1981–2020, con un calentamiento conocido de +0,3 °C/década y lluvia sin tendencia."""
    rng = np.random.default_rng(7)
    fechas = pd.date_range("1981-01-01", "2020-12-31", freq="D")
    t = (fechas - fechas[0]).days.to_numpy() / 3652.5           # décadas
    estacional = 1.5 * np.sin(2 * np.pi * fechas.dayofyear.to_numpy() / 365.25)
    tmed = 20 + estacional + 0.3 * t + rng.normal(0, 0.8, len(fechas))
    lluvia = rng.gamma(0.6, 8, len(fechas)) * (rng.random(len(fechas)) < 0.5)
    return pd.DataFrame({"punto": "Ciudad X", "fecha": fechas, "tmed": tmed, "tmax": tmed + 5, "tmin": tmed - 5,
                         "precip": lluvia, "humedad": 80.0, "viento_max": 10.0, "radiacion": 15.0})
