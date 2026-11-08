"""Rutas, ciudades, estaciones, variables, periodos y estilo de gráficos del proyecto."""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parents[2]
CRUDOS = RAIZ / "data" / "raw"                  # caché de descargas (no se versiona)
ERA5_CRUDO = CRUDOS / "era5"                    # un Parquet por variable y bloque (año o trozo de 21 días)
INTERMEDIOS = RAIZ / "data" / "interim"         # serie horaria unida (~100 MB, no se versiona)
PROCESADOS = RAIZ / "data" / "procesados"       # tablas diarias/mensuales pequeñas: sí se versionan
FIGURAS = RAIZ / "reports" / "figures"
REPORTES = RAIZ / "reports"

HORARIO = INTERMEDIOS / "era5_horario.parquet"
DIARIO = PROCESADOS / "era5_diario.parquet"
MENSUAL = PROCESADOS / "era5_mensual.parquet"
ANUAL = PROCESADOS / "indices_anuales.parquet"
CELDAS = PROCESADOS / "celdas_era5.csv"
ONI = PROCESADOS / "oni.csv"
NINO12 = PROCESADOS / "nino12.csv"
ESTACIONES_DIARIO = PROCESADOS / "ghcn_diario.parquet"
MUESTRA_API = CRUDOS / "api_muestra"
GEOJSON_PROVINCIAS = CRUDOS / "ecuador_provincias.geojson"
RESULTADOS = REPORTES / "resultados.json"

# ---------------------------------------------------------------------------
# Fuentes
# ---------------------------------------------------------------------------
# Open-Meteo publica su archivo ERA5 en AWS Open Data (sin clave ni límite de llamadas).
# Archivos .om: year_YYYY.om (1940–2021, ~4 GB por variable y año) y chunk_N.om (504 h, desde 2022).
S3_BUCKET = "openmeteo"
S3_ERA5 = f"{S3_BUCKET}/data/copernicus_era5"
HORAS_POR_TROZO = 504            # chunk_N cubre las horas [N·504, (N+1)·504) desde 1970-01-01 UTC
ULTIMO_ANIO_ARCHIVO = 2021       # último year_YYYY.om; después se usan los trozos
RESOLUCION = 0.25                # malla regular de ERA5: lat −90…90 (721), lon −180…179,75 (1440)

URL_API_ARCHIVO = "https://archive-api.open-meteo.com/v1/archive"
URL_ONI = "https://psl.noaa.gov/data/correlation/oni.data"
# Niño 1+2 (0–10° S, 90–80° O): el mar frente a la costa del Ecuador; anomalía respecto a 1981–2010
URL_NINO12 = "https://psl.noaa.gov/data/correlation/nina1.anom.data"
URL_GHCN = "https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/{estacion}.csv"
URL_PROVINCIAS = ("https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/ECU/ADM1/"
                  "geoBoundaries-ECU-ADM1_simplified.geojson")

ANIO_INICIO = 1980
ANIO_FIN = 2024
PERIODO_REFERENCIA = (1981, 2010)   # normal climatológica de la OMM usada para las anomalías y percentiles

# Variables horarias que se leen del archivo .om (nombre en S3 -> columna)
VARIABLES_S3 = {
    "temperature_2m": "temp",             # °C
    "dew_point_2m": "punto_rocio",        # °C
    "precipitation": "precip",            # mm en la hora anterior
    "shortwave_radiation": "radiacion",   # W/m², media de la hora anterior
    "wind_u_component_10m": "viento_u",   # m/s
    "wind_v_component_10m": "viento_v",   # m/s
    "wind_gusts_10m": "rafagas",          # m/s
}
# Lluvia y radiación de la hora t son lo acumulado en la hora que *termina* en t: el día D suma de 01:00 a 24:00.
# Verificado contra la API: horario idéntico sin desplazar; diario idéntico (0,000 mm) solo con esta convención.
ACUMULADAS = ["precip", "radiacion"]

# ---------------------------------------------------------------------------
# Ciudades: 22 en las 4 regiones naturales (lat, lon, altitud en m)
# ---------------------------------------------------------------------------
REGIONES = ["Costa", "Sierra", "Amazonía", "Galápagos"]
CIUDADES = {
    # Costa
    "Guayaquil":        (-2.170, -79.922, 4, "Costa"),
    "Manta":            (-0.967, -80.709, 6, "Costa"),
    "Esmeraldas":       (0.968, -79.652, 15, "Costa"),
    "Machala":          (-3.258, -79.955, 6, "Costa"),
    "Portoviejo":       (-1.054, -80.454, 53, "Costa"),
    "Salinas":          (-2.215, -80.958, 5, "Costa"),
    "Santo Domingo":    (-0.254, -79.172, 550, "Costa"),
    # Sierra
    "Quito":            (-0.180, -78.467, 2850, "Sierra"),
    "Cuenca":           (-2.900, -79.005, 2560, "Sierra"),
    "Ambato":           (-1.249, -78.617, 2580, "Sierra"),
    "Riobamba":         (-1.664, -78.654, 2754, "Sierra"),
    "Loja":             (-3.993, -79.204, 2060, "Sierra"),
    "Ibarra":           (0.352, -78.122, 2225, "Sierra"),
    "Latacunga":        (-0.935, -78.616, 2780, "Sierra"),
    # Amazonía
    "Puyo":             (-1.492, -78.003, 950, "Amazonía"),
    "Tena":             (-0.993, -77.813, 510, "Amazonía"),
    "Nueva Loja":       (0.085, -76.894, 297, "Amazonía"),
    "Macas":            (-2.309, -78.118, 1030, "Amazonía"),
    "Zamora":           (-4.067, -78.951, 970, "Amazonía"),
    "Coca":             (-0.462, -76.987, 255, "Amazonía"),
    # Galápagos
    "Puerto Ayora":     (-0.743, -90.313, 10, "Galápagos"),
    "Puerto Baquerizo": (-0.902, -89.610, 10, "Galápagos"),
}

# Estaciones de NOAA GHCN-Daily en Ecuador con datos recientes: validación independiente de ERA5.
# (id, nombre, lat, lon, altitud, región)
ESTACIONES = {
    "ECM00084008": ("San Cristóbal (Galápagos)", -0.917, -89.617, 19, "Galápagos"),
    "ECM00084135": ("Portoviejo", -1.033, -80.450, 60, "Costa"),
    "ECM00084050": ("La Concordia", 0.017, -79.367, 360, "Costa"),
    "ECM00084088": ("Izobamba (Quito)", -0.350, -78.550, 3058, "Sierra"),
    "ECM00084226": ("Cañar", -2.550, -78.933, 3083, "Sierra"),
    "ECM00084270": ("Loja La Argelia", -4.033, -79.200, 2160, "Sierra"),
    "ECM00084179": ("Puyo", -1.500, -77.900, 960, "Amazonía"),
    "ECM00084132": ("Nuevo Rocafuerte", -0.917, -75.417, 265, "Amazonía"),
}


def puntos() -> dict[str, tuple[float, float, float, str, str]]:
    """Todos los puntos a extraer: ciudades y estaciones. nombre -> (lat, lon, altitud, región, tipo)."""
    p = {c: (la, lo, z, reg, "ciudad") for c, (la, lo, z, reg) in CIUDADES.items()}
    p.update({f"est_{k}": (la, lo, z, reg, "estacion") for k, (_, la, lo, z, reg) in ESTACIONES.items()})
    return p


def desfase_utc(region: str) -> int:
    """Horas respecto a UTC: Ecuador continental UTC−5 y Galápagos UTC−6 (sin horario de verano)."""
    return -6 if region == "Galápagos" else -5


# ---------------------------------------------------------------------------
# Análisis
# ---------------------------------------------------------------------------
GRADIENTE_TERMICO = -0.0065      # °C por metro: corrección por altitud (la misma idea que usa Open-Meteo)
UMBRAL_DIA_LLUVIA = 1.0          # mm: día húmedo (ETCCDI)
UMBRAL_LLUVIA_INTENSA = 20.0     # mm: R20mm (ETCCDI)
PERCENTIL_CALOR = 90             # TX90p / TN90p con ventana de 5 días centrada en el día del año
DIAS_OLA_CALOR = 3               # ola de calor: al menos 3 días seguidos con Tmáx > p90
ALFA = 0.05
REZAGOS_ONI = range(0, 7)        # meses de rezago (ONI adelantado respecto al clima local)

# ---------------------------------------------------------------------------
# Estilo de gráficos (paleta categórica validada para daltonismo, orden fijo)
# ---------------------------------------------------------------------------
COLORES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
COLOR_REGION = {"Costa": COLORES[0], "Sierra": COLORES[1], "Amazonía": COLORES[2], "Galápagos": COLORES[6]}
GRIS = "#8a8984"
GRIS_CLARO = "#c9c8c3"
SUPERFICIE = "#fcfcfb"
TEXTO = "#0b0b0b"
TEXTO_SECUNDARIO = "#52514e"
CALIDO = "#c8432d"
FRIO = "#2a78d6"
