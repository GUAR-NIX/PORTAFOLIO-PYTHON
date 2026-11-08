"""Baja los catálogos del USGS y las capas de los mapas (reanudable: lo que ya está en caché no se repite).

Uso:  python descargar_datos.py        (~3–5 min la primera vez, ~110 consultas con 1 s de pausa)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from sismos.descarga import descargar_todo  # noqa: E402

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(descargar_todo().to_string(index=False))
