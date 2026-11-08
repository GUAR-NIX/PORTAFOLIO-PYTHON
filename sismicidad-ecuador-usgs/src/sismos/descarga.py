"""
Descarga reanudable de los tres catálogos y de las capas para los mapas.

1. Ecuador ampliado, M>=2,5, 1970–2025 (una consulta por año).
2. Mundo, M>=5, 1973–2025 (una consulta por año, ~1 700 eventos cada una): de aquí salen las zonas
   del Cinturón de Fuego. Se pide el mundo entero y se recorta en local para no hacer 13 descargas
   que se solapan.
3. Ecuador ampliado, M>=6, 1900–2025 (bloques de 25 años): línea base empírica para los periodos de retorno.

Cada respuesta queda en caché en ``data/raw/usgs/``; volver a correr el script solo pide lo que falta.
Al final se une cada catálogo en un Parquet crudo (``data/raw/union_*.parquet``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from . import config
from .cliente_usgs import ClienteUSGS

CATALOGOS = {
    "ecuador_m2.5": dict(anio_inicio=config.ANIO_INICIO_ECUADOR, region=config.ECUADOR,
                         mag_min=config.MAG_MIN_ECUADOR, paso_anios=1),
    "mundo_m5": dict(anio_inicio=config.ANIO_INICIO_GLOBAL, region=None,
                     mag_min=config.MAG_MIN_GLOBAL, paso_anios=1),
    "ecuador_m6_historico": dict(anio_inicio=config.ANIO_INICIO_HISTORICO, region=config.ECUADOR,
                                 mag_min=config.MAG_MIN_HISTORICO, paso_anios=25),
}

CAPAS = {"placas_pb2002.json": config.URL_PLACAS,
         "costas_ne50m.geojson": config.URL_COSTAS,
         "fronteras_ne50m.geojson": config.URL_FRONTERAS}


def union_cruda(etiqueta: str) -> Path:
    return config.CRUDOS / f"union_{etiqueta}.parquet"


def descargar_catalogos(cliente: ClienteUSGS | None = None, anio_fin: int = config.ANIO_FIN) -> pd.DataFrame:
    cliente = cliente or ClienteUSGS()
    resumen = []
    for etiqueta, p in CATALOGOS.items():
        print(f"Catálogo {etiqueta} ({p['anio_inicio']}–{anio_fin}, M>={p['mag_min']})")
        tabla = cliente.descargar_anios(etiqueta, p["anio_inicio"], anio_fin, p["region"], p["mag_min"],
                                        paso_anios=p["paso_anios"])
        destino = union_cruda(etiqueta)
        tabla.to_parquet(destino, index=False)
        resumen.append({"catalogo": etiqueta, "eventos": len(tabla), "archivo": destino.name,
                        "mb": round(destino.stat().st_size / 1e6, 2)})
        print(f"  → {len(tabla):,} eventos en {destino.name}")
    log = pd.DataFrame(cliente.log)
    resumen = pd.DataFrame(resumen)
    resumen["llamadas_red_esta_corrida"] = cliente.llamadas_red
    resumen["consultas_en_cache"] = int((log["origen"] == "cache").sum()) if len(log) else 0
    resumen["fecha"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return resumen


def descargar_capas(forzar: bool = False) -> list[Path]:
    """Límites de placas (Bird, 2003) y costas/fronteras de Natural Earth. Opcionales: si fallan, los
    mapas se dibujan sin ellas."""
    rutas = []
    for nombre, url in CAPAS.items():
        destino = config.CRUDOS / "capas" / nombre
        if destino.exists() and not forzar:
            rutas.append(destino)
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            destino.write_bytes(r.content)
            rutas.append(destino)
            print(f"  capa {nombre}: {len(r.content) / 1e6:.1f} MB")
        except requests.RequestException as e:
            print(f"  aviso: no se pudo bajar {nombre} ({e}); el mapa irá sin esa capa")
    return rutas


def descargar_todo() -> pd.DataFrame:
    config.CRUDOS.mkdir(parents=True, exist_ok=True)
    config.REPORTES.mkdir(parents=True, exist_ok=True)
    resumen = descargar_catalogos()
    descargar_capas()
    resumen.to_csv(config.REPORTES / "log_descarga.csv", index=False)
    return resumen
