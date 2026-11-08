"""Rutas, países, indicadores y estilo de gráficos del proyecto."""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parents[2]
CRUDOS = RAIZ / "data" / "raw"                 # caché de descargas (no se versiona)
PROCESADOS = RAIZ / "data" / "procesados"      # panel limpio, pequeño: sí se versiona (app)
FIGURAS = RAIZ / "reports" / "figures"
REPORTES = RAIZ / "reports"

PANEL = PROCESADOS / "panel_latam.csv"
COBERTURA = PROCESADOS / "cobertura.csv"

# ---------------------------------------------------------------------------
# Fuentes
# ---------------------------------------------------------------------------
URL_BANCO_MUNDIAL = "https://api.worldbank.org/v2"
URL_OWID = "https://raw.githubusercontent.com/owid/co2-data/master/owid-co2-data.csv"

ANIO_INICIO = 1990
ANIO_FIN = 2024  # tope; el último año útil lo decide la cobertura real de los datos

# 20 países de América Latina (ISO 3166-1 alfa-3 -> nombre en español).
# Es el código que usan las dos fuentes, así que la unión se hace por ISO3, nunca por nombre.
PAISES = {
    "ARG": "Argentina", "BOL": "Bolivia", "BRA": "Brasil", "CHL": "Chile", "COL": "Colombia",
    "CRI": "Costa Rica", "CUB": "Cuba", "DOM": "Rep. Dominicana", "ECU": "Ecuador",
    "SLV": "El Salvador", "GTM": "Guatemala", "HTI": "Haití", "HND": "Honduras", "MEX": "México",
    "NIC": "Nicaragua", "PAN": "Panamá", "PRY": "Paraguay", "PER": "Perú", "URY": "Uruguay",
    "VEN": "Venezuela",
}
# Agregado regional: suma de los países que tienen PIB y CO2 en todos los años.
# Cuba y Venezuela no tienen PIB en el Banco Mundial, así que la región es de 18 países.
REGION = "LATAM"
NOMBRE_REGION = "América Latina (18)"
SUMABLES = ["pib_ppa", "poblacion_bm", "co2_mt", "co2_consumo_mt", "co2_con_luc_mt", "co2_luc_mt",
            "co2_petroleo_mt", "co2_gas_mt", "co2_carbon_mt", "co2_cemento_mt", "co2_quema_mt",
            "energia_twh", "gei_total_mt"]

# Banco Mundial: código del indicador -> nombre de columna en el panel
INDICADORES_BM = {
    "NY.GDP.MKTP.PP.KD": "pib_ppa",            # PIB, PPA, USD internacionales constantes de 2021
    "NY.GDP.PCAP.PP.KD": "pib_pc_ppa",         # PIB per cápita, PPA, constantes de 2021
    "SP.POP.TOTL": "poblacion_bm",
    "SP.URB.TOTL.IN.ZS": "urbana_pct",
    "NV.IND.TOTL.ZS": "industria_pct_pib",
    "EG.FEC.RNEW.ZS": "renovable_pct_consumo", # energía renovable, % del consumo final
    "EG.ELC.ACCS.ZS": "acceso_electricidad_pct",
    "SI.POV.DDAY": "pobreza_extrema_pct",      # línea internacional de pobreza extrema (PPA)
    "AG.LND.FRST.ZS": "bosque_pct",
}

# Our World in Data: columna original -> nombre en el panel
COLUMNAS_OWID = {
    "co2": "co2_mt",                           # CO2 fósil + industria (territorial), Mt
    "co2_per_capita": "co2_pc_t",
    "consumption_co2": "co2_consumo_mt",       # CO2 basado en consumo (ajustado por comercio)
    "co2_including_luc": "co2_con_luc_mt",     # incluye cambio de uso del suelo
    "land_use_change_co2": "co2_luc_mt",
    "oil_co2": "co2_petroleo_mt",
    "gas_co2": "co2_gas_mt",
    "coal_co2": "co2_carbon_mt",
    "cement_co2": "co2_cemento_mt",
    "flaring_co2": "co2_quema_mt",
    "primary_energy_consumption": "energia_twh",
    "total_ghg": "gei_total_mt",
    "population": "poblacion_owid",
}

# ---------------------------------------------------------------------------
# Análisis
# ---------------------------------------------------------------------------
# Desacople: se comparan promedios de 3 años al inicio y al final para que un año atípico
# (crisis, sequía, pandemia) no decida la clasificación.
PERIODO_DESACOPLE = (2000, 2024)
PERIODO_CONSUMO = (2000, 2023)   # el CO2 basado en consumo llega hasta 2023
VENTANA_EXTREMOS = 3
SUBPERIODOS = [(2000, 2012), (2012, 2024)]   # auge y fin del súper ciclo de materias primas
VENTANA_MOVIL = 10

# ---------------------------------------------------------------------------
# Estilo de gráficos (paleta categórica validada para daltonismo, orden fijo)
# ---------------------------------------------------------------------------
COLORES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
GRIS = "#8a8984"
GRIS_CLARO = "#c9c8c3"
SUPERFICIE = "#fcfcfb"
TEXTO = "#0b0b0b"
TEXTO_SECUNDARIO = "#52514e"

CATEGORIAS_DESACOPLE = ["Absoluto", "Relativo", "Sin desacople", "Recesión", "Sin datos"]
COLOR_DESACOPLE = {
    "Absoluto": COLORES[2], "Relativo": COLORES[0], "Sin desacople": COLORES[1],
    "Recesión": COLORES[6], "Sin datos": GRIS_CLARO,
}
COLOR_ECUADOR = COLORES[0]
COLOR_REGION = COLORES[1]
