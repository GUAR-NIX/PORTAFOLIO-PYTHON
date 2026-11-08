"""Rutas, ventana de estudio y parámetros compartidos del proyecto."""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DIR_DATOS = RAIZ / "data"
DIR_RAW = DIR_DATOS / "raw"
DIR_PAGINAS = DIR_RAW / "paginas"
DIR_PROCESADOS = DIR_DATOS / "procesados"
DIR_REPORTS = RAIZ / "reports"
DIR_FIGURAS = DIR_REPORTS / "figures"
DIR_TABLAS = DIR_REPORTS / "tablas"

ARCHIVO_MANIFIESTO = DIR_RAW / "manifiesto_descarga.json"
ARCHIVO_CRUDO = DIR_RAW / "nyc311_crudo.parquet"
ARCHIVO_LIMPIO = DIR_PROCESADOS / "nyc311_supervivencia.parquet"
ARCHIVO_RESULTADOS = DIR_REPORTS / "resultados.json"

# Fuente: NYC Open Data, «311 Service Requests from 2010 to Present» (API Socrata SODA 2.1, sin clave)
ID_DATASET = "erm2-nwe9"
URL_API = f"https://data.cityofnewyork.us/resource/{ID_DATASET}.csv"
URL_FICHA = f"https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2010-to-Present/{ID_DATASET}"
URL_TERMINOS = "https://www.nyc.gov/home/terms-of-use.page"

# Solo las columnas que usa el análisis (el dataset completo tiene 40+)
COLUMNAS = [
    "unique_key",
    "created_date",
    "closed_date",
    "agency",
    "complaint_type",
    "descriptor",
    "status",
    "incident_zip",
    "borough",
    "open_data_channel_type",
]

# Cohorte: solicitudes creadas en 24 meses completos. La fecha de corte (censura) es el instante
# en que empezó la descarga y queda fija en el manifiesto, aunque la descarga se reanude días después.
MES_INICIO = "2024-10"
MES_FIN = "2026-09"

TAMANO_PAGINA = 50_000
HILOS_DESCARGA = 3
REINTENTOS = 6

BOROUGHS = ["BRONX", "BROOKLYN", "MANHATTAN", "QUEENS", "STATEN ISLAND"]
CANALES = ["PHONE", "ONLINE", "MOBILE", "OTHER"]

SEMILLA = 311
