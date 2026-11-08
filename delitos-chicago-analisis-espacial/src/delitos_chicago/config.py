from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DATOS = RAIZ / "data"
RAW = DATOS / "raw"
PROCESADOS = DATOS / "procesados"
REFERENCIA = DATOS / "referencia"
REPORTES = RAIZ / "reports"
FIGURAS = REPORTES / "figures"
MUESTRA = DATOS / "muestra"

for carpeta in (RAW, PROCESADOS, REFERENCIA, REPORTES, FIGURAS, MUESTRA):
    carpeta.mkdir(parents=True, exist_ok=True)

# Ventana común para el análisis espacial (Gi*, tasas y rankings): años completos alrededor del censo 2020
ANIOS_ESPACIALES = list(range(2019, 2026))
# Comparación de composición del delito antes y después de la pandemia
ANIO_CAMBIO_INI, ANIO_CAMBIO_FIN = 2019, 2024
