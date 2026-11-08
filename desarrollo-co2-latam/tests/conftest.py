import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture
def panel_sintetico() -> pd.DataFrame:
    """Tres países inventados, 2000–2010, con trayectorias conocidas:

    * AAA: PIB +4 %/año y CO2 −1 %/año            -> desacople absoluto
    * BBB: PIB +4 %/año y CO2 +2 %/año            -> relativo
    * CCC: PIB +2 %/año y CO2 +3 %/año            -> sin desacople
    """
    anios = np.arange(2000, 2011)
    t = anios - 2000
    filas = []
    for iso, g_pib, g_co2 in [("AAA", 0.04, -0.01), ("BBB", 0.04, 0.02), ("CCC", 0.02, 0.03)]:
        for a, k in zip(anios, t):
            filas.append({
                "iso3": iso, "pais": iso.title(), "anio": int(a),
                "pib_ppa": 1e11 * (1 + g_pib) ** k, "co2_mt": 50 * (1 + g_co2) ** k,
                "poblacion_bm": 1e7 * 1.01 ** k, "energia_twh": 200 * 1.015 ** k,
            })
    return pd.DataFrame(filas)
