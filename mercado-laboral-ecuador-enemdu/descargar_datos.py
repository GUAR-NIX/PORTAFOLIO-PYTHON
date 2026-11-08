"""Script CLI para descargar los microdatos y tabulados oficiales del INEC (ENEMDU 2025)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from empleo_enemdu.config import DIR_RAW
from empleo_enemdu.descarga import descargar_todo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Descarga microdatos, tabulados, diccionario y sintaxis oficial INEC ENEMDU 2025."
    )
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="Fuerza la descarga incluso si los archivos ya existen en data/raw/.",
    )
    parser.add_argument(
        "--certificados",
        metavar="certifi|RUTA.pem",
        help="Solo si el certificado del INEC no se valida con el sistema: usa el paquete certifi o un .pem. "
        "La verificación TLS y la del SHA-256 nunca se desactivan.",
    )
    args = parser.parse_args()

    print("Descargando paquetes oficiales de la ENEMDU Anual 2025 (INEC)...")
    resumen = descargar_todo(DIR_RAW, forzar=args.forzar, certificados=args.certificados)
    for clave, info in resumen.items():
        mb = info["bytes"] / (1024 * 1024)
        origen = "caché" if info["desde_cache"] else "red"
        print(f"  - {clave}: {info['archivo']} ({mb:.2f} MB, {origen}) -> {len(info['extraidos'])} archivos")

    ruta_manifest = DIR_RAW / "manifiesto_descarga.json"
    ruta_manifest.write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Manifiesto guardado en {ruta_manifest}")


if __name__ == "__main__":
    main()
