"""Descarga el 311 de Nueva York (oct-2024 a sep-2026) desde NYC Open Data y lo consolida en Parquet.

Es reanudable: si se corta, vuelve a ejecutarlo y solo bajará las páginas que falten.

    python descargar_datos.py
"""

from nyc311.descarga import main

if __name__ == "__main__":
    main()
