"""
Descarga los datos crudos desde las fuentes oficiales a data/raw/ (caché).

    python descargar_datos.py            # reutiliza lo que ya esté descargado (se puede cortar y reanudar)
    python descargar_datos.py --forzar   # vuelve a bajar todo

ERA5 horario 1980–2024 (7 variables × 30 puntos, ~1.000 archivos .om leídos por rangos): 20–40 minutos.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import pandas as pd  # noqa: E402

from clima_ecuador import config, descarga  # noqa: E402

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--forzar", action="store_true", help="ignora la caché y descarga de nuevo")
    args = p.parse_args()
    log = descarga.descargar_todo(forzar=args.forzar, avisar=lambda m: print(m, flush=True))
    for fila in log:
        print(f"{fila['fuente']:<36} {fila['archivo']:<36} {fila['segundos']:>8.1f} s")
    config.REPORTES.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(log).to_csv(config.REPORTES / "log_descarga.csv", index=False)
