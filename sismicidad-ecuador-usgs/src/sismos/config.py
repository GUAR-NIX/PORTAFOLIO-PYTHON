"""Rutas, regiones y parámetros del proyecto (un solo lugar para cambiarlos)."""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CRUDOS = RAIZ / "data" / "raw"
CACHE_USGS = CRUDOS / "usgs"
PROCESADOS = RAIZ / "data" / "procesados"
MUESTRA = RAIZ / "data" / "muestra"
REPORTES = RAIZ / "reports"
FIGURAS = REPORTES / "figures"

CATALOGO_ECUADOR = PROCESADOS / "catalogo_ecuador.parquet"
CATALOGO_CINTURON = PROCESADOS / "catalogo_cinturon_m5.parquet"
CATALOGO_HISTORICO = PROCESADOS / "catalogo_ecuador_m6_historico.parquet"
RESULTADOS = REPORTES / "resultados.json"

# ---- API FDSN del USGS (dominio público) -------------------------------------------------
URL_USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"
LIMITE_USGS = 20_000          # máximo de eventos que devuelve una consulta
PAUSA_SEGUNDOS = 1.0          # pausa entre llamadas reales (respeto a la API)
TIEMPO_ESPERA = 90            # segundos por petición
REINTENTOS = 5

# ---- Regiones -----------------------------------------------------------------------------
# Ecuador ampliado: incluye la fosa, el sur de Colombia y el norte del Perú
ECUADOR = {"minlatitude": -6, "maxlatitude": 3, "minlongitude": -82, "maxlongitude": -74}
ANIO_INICIO_ECUADOR = 1970
ANIO_FIN = 2025               # último año completo (la descarga va hasta el 1 de enero siguiente)
MAG_MIN_ECUADOR = 2.5

# Catálogo global M>=5 desde 1973 (inicio de la red moderna del USGS/NEIC): de aquí salen las zonas
ANIO_INICIO_GLOBAL = 1973
MAG_MIN_GLOBAL = 5.0

# Sismos fuertes históricos del Ecuador ampliado (M>=6 desde 1900), para la línea base empírica
ANIO_INICIO_HISTORICO = 1900
MAG_MIN_HISTORICO = 6.0

# Zonas del Cinturón de Fuego del Pacífico: (lat_min, lat_max, lon_min, lon_max).
# Cajas simples y sin solaparse, elegidas sobre las fosas de subducción principales.
ZONAS_CINTURON: dict[str, tuple[float, float, float, float]] = {
    "Ecuador":             (-6, 3, -82, -74),
    "Colombia–Panamá":     (3, 10, -84, -72),
    "Perú":                (-18, -6, -82, -68),
    "Chile norte":         (-30, -18, -76, -66),
    "Chile centro-sur":    (-46, -30, -78, -68),
    "Centroamérica":       (8, 16, -94, -84),
    "México":              (14, 22, -107, -94),
    "Alaska–Aleutianas":   (50, 62, -180, -145),
    "Kamchatka–Kuriles":   (42, 60, 145, 165),
    "Japón":               (30, 42, 128, 146),
    "Filipinas":           (5, 20, 118, 128),
    "Tonga–Kermadec":      (-38, -14, -180, -172),
    "Nueva Zelanda":       (-48, -36, 165, 179),
}

# ---- Terremoto de Pedernales (16-abr-2016, M7,8 Mww, evento us20005j32 del USGS) -------------
PEDERNALES = {
    "id": "us20005j32",
    "tiempo": "2016-04-16T23:58:36.980Z",
    "latitud": 0.3819,
    "longitud": -79.9218,
    "magnitud": 7.8,
}
RADIO_REPLICAS_KM = 150      # cubre la ruptura (~120 km de norte a sur) y su entorno
DIAS_REPLICAS = 365

# ---- Análisis -----------------------------------------------------------------------------
DELTA_M = 0.1                 # ancho de clase de magnitud (los catálogos reportan con un decimal)
CORRECCION_MAXC = 0.2         # Mc = máxima curvatura + 0,2 (Woessner y Wiemer, 2005)
N_BOOTSTRAP = 1000
SEMILLA = 42

# ---- Capas para los mapas (opcionales) -------------------------------------------------------
URL_PLACAS = ("https://raw.githubusercontent.com/fraxen/tectonicplates/master/GeoJSON/"
              "PB2002_boundaries.json")
URL_COSTAS = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
              "ne_50m_coastline.geojson")
URL_FRONTERAS = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
                 "ne_50m_admin_0_boundary_lines_land.geojson")
