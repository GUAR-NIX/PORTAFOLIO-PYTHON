"""
Descarga los datos crudos desde las fuentes oficiales a data/raw/ (caché).

    python descargar_datos.py            # reutiliza lo que ya esté descargado
    python descargar_datos.py --forzar   # vuelve a bajar todo
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from desarrollo_co2 import descarga  # noqa: E402

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--forzar", action="store_true", help="ignora la caché y descarga de nuevo")
    args = p.parse_args()
    for fila in descarga.descargar_todo(forzar=args.forzar):
        print(f"{fila['fuente']:<38} {fila['archivo']:<32} {fila['kb']:>9,.1f} KB  {fila['segundos']:>6.2f} s")
