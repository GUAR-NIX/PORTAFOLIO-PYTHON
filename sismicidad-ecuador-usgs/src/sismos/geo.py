"""Utilidades geográficas mínimas (sin dependencias pesadas)."""
from __future__ import annotations

import numpy as np

RADIO_TIERRA_KM = 6371.0


def distancia_km(lat1, lon1, lat2, lon2):
    """Distancia de gran círculo (haversine) en km; acepta escalares o arreglos."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * RADIO_TIERRA_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
