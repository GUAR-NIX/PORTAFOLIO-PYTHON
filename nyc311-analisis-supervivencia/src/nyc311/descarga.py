"""Descarga reanudable del 311 de Nueva York desde la API Socrata de NYC Open Data.

Estrategia:
* Un mes de `created_date` por tarea y páginas de `TAMANO_PAGINA` filas ordenadas por `unique_key`
  (`$order` estable: sin él, `$offset` puede repetir o saltar filas).
* Cada página se guarda como Parquet en `data/raw/paginas/AAAA-MM/pagina_00000.parquet` con escritura
  atómica (archivo temporal + renombrado). Si la PC se apaga, al relanzar se saltan las páginas ya
  guardadas y los meses marcados con `_completo.json`.
* Reintentos con espera exponencial ante errores de red, 429 (límite de peticiones) y 5xx.
* La **fecha de corte** (instante que define la censura) se fija la primera vez en el manifiesto y no
  cambia al reanudar: es la fecha más reciente de `created_date` publicada, no el reloj local, porque
  el dataset se actualiza una vez al día y un cierre posterior a esa actualización todavía no existe en la API.

Uso:
    python -m nyc311.descarga              # descarga lo que falte y consolida en data/raw/nyc311_crudo.parquet
    python -m nyc311.descarga --solo-consolidar
"""

from __future__ import annotations

import argparse
import io
import json
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
import requests

from nyc311.config import (
    ARCHIVO_CRUDO,
    ARCHIVO_MANIFIESTO,
    COLUMNAS,
    DIR_PAGINAS,
    HILOS_DESCARGA,
    MES_FIN,
    MES_INICIO,
    REINTENTOS,
    TAMANO_PAGINA,
    URL_API,
)

CODIGOS_REINTENTABLES = {429, 500, 502, 503, 504}
AGENTE = "nyc311-supervivencia/1.0 (proyecto de portafolio; datos abiertos)"


class Sesion(Protocol):
    """Lo mínimo que se usa de `requests.Session` (permite inyectar respuestas grabadas en las pruebas)."""

    def get(self, url: str, params: dict[str, Any] | None = ..., timeout: float = ...) -> Any: ...


def meses_de_ventana(inicio: str = MES_INICIO, fin: str = MES_FIN) -> list[str]:
    """Lista de meses 'AAAA-MM' entre `inicio` y `fin`, ambos incluidos."""
    return [p.strftime("%Y-%m") for p in pd.period_range(inicio, fin, freq="M")]


def filtro_mes(mes: str) -> str:
    """Cláusula `$where` SoQL para las solicitudes creadas en un mes (intervalo semiabierto)."""
    periodo = pd.Period(mes, freq="M")
    desde = periodo.start_time.strftime("%Y-%m-%dT00:00:00")
    hasta = (periodo + 1).start_time.strftime("%Y-%m-%dT00:00:00")
    return f"created_date >= '{desde}' AND created_date < '{hasta}'"


def parametros_pagina(mes: str, offset: int, limite: int = TAMANO_PAGINA) -> dict[str, str]:
    """Parámetros SoQL de una página: columnas filtradas, mes, orden estable y paginación."""
    return {
        "$select": ",".join(COLUMNAS),
        "$where": filtro_mes(mes),
        "$order": "unique_key",
        "$limit": str(limite),
        "$offset": str(offset),
    }


def obtener_con_reintentos(
    sesion: Sesion,
    url: str,
    params: dict[str, str],
    reintentos: int = REINTENTOS,
    espera_base: float = 2.0,
    dormir: Callable[[float], None] = time.sleep,
) -> str:
    """GET con reintentos y espera exponencial (2, 4, 8… s). Devuelve el cuerpo de la respuesta."""
    ultimo_error: Exception | None = None
    for intento in range(reintentos):
        try:
            resp = sesion.get(url, params=params, timeout=180)
            if resp.status_code in CODIGOS_REINTENTABLES:
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp.text
        except (requests.RequestException, ConnectionError, TimeoutError) as error:
            ultimo_error = error
            if intento < reintentos - 1:
                dormir(espera_base * 2**intento)
    raise RuntimeError(f"Fallaron {reintentos} intentos para {params.get('$where')} offset {params.get('$offset')}") from ultimo_error


def leer_csv_pagina(texto: str) -> pa.Table:
    """CSV de Socrata → tabla Arrow con todas las columnas como texto (vacío = nulo).

    Se guarda el texto tal cual: el tipado y la validación son trabajo de `limpieza.py`.
    """
    tabla = pacsv.read_csv(
        io.BytesIO(texto.encode("utf-8")),
        convert_options=pacsv.ConvertOptions(
            column_types={c: pa.string() for c in COLUMNAS},
            strings_can_be_null=True,
            null_values=[""],
        ),
    )
    # Socrata omite del CSV una columna pedida si todas sus filas son nulas: se completa
    for col in COLUMNAS:
        if col not in tabla.column_names:
            tabla = tabla.append_column(col, pa.nulls(tabla.num_rows, pa.string()))
    return tabla.select(COLUMNAS)


def _escribir_atomico(tabla: pa.Table, destino: Path) -> None:
    temporal = destino.with_suffix(".tmp")
    pq.write_table(tabla, temporal, compression="zstd")
    temporal.replace(destino)


def descargar_mes(
    mes: str,
    sesion: Sesion,
    dir_paginas: Path = DIR_PAGINAS,
    tamano: int = TAMANO_PAGINA,
    url: str = URL_API,
    dormir: Callable[[float], None] = time.sleep,
) -> int:
    """Descarga (o reanuda) todas las páginas de un mes. Devuelve el número de filas del mes."""
    carpeta = dir_paginas / mes
    marca = carpeta / "_completo.json"
    if marca.exists():
        return int(json.loads(marca.read_text(encoding="utf-8"))["filas"])
    carpeta.mkdir(parents=True, exist_ok=True)

    filas, pagina = 0, 0
    while True:
        ruta = carpeta / f"pagina_{pagina:05d}.parquet"
        if ruta.exists():
            n = pq.read_metadata(ruta).num_rows  # página guardada en una ejecución anterior
        else:
            texto = obtener_con_reintentos(sesion, url, parametros_pagina(mes, pagina * tamano, tamano), dormir=dormir)
            tabla = leer_csv_pagina(texto)
            n = tabla.num_rows
            _escribir_atomico(tabla, ruta)
        filas += n
        pagina += 1
        if n < tamano:
            break

    marca.write_text(
        json.dumps({"mes": mes, "filas": filas, "paginas": pagina,
                    "terminado": datetime.now(timezone.utc).isoformat(timespec="seconds")}, indent=2),
        encoding="utf-8",
    )
    return filas


def consultar_fecha_corte(sesion: Sesion, url: str = URL_API) -> str:
    """Fecha de creación más reciente publicada en la API (hora local de Nueva York, sin zona)."""
    texto = obtener_con_reintentos(sesion, url, {"$select": "max(created_date) AS maximo"})
    valor = pacsv.read_csv(io.BytesIO(texto.encode("utf-8"))).column("maximo")[0].as_py()
    return pd.Timestamp(valor).strftime("%Y-%m-%dT%H:%M:%S")


def cargar_o_crear_manifiesto(sesion: Sesion, meses: list[str], archivo: Path = ARCHIVO_MANIFIESTO) -> dict[str, Any]:
    """El manifiesto fija la fecha de corte la primera vez; las reanudaciones la reutilizan."""
    if archivo.exists():
        return json.loads(archivo.read_text(encoding="utf-8"))
    manifiesto = {
        "fuente": URL_API,
        "columnas": COLUMNAS,
        "mes_inicio": meses[0],
        "mes_fin": meses[-1],
        "fecha_corte": consultar_fecha_corte(sesion),
        "inicio_descarga_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifiesto


def _nueva_sesion() -> requests.Session:
    sesion = requests.Session()
    sesion.headers["User-Agent"] = AGENTE
    return sesion


def descargar(meses: Iterable[str] | None = None, hilos: int = HILOS_DESCARGA) -> dict[str, int]:
    """Descarga los meses en paralelo (un hilo por mes, cada uno con su sesión HTTP)."""
    meses = list(meses or meses_de_ventana())
    manifiesto = cargar_o_crear_manifiesto(_nueva_sesion(), meses)
    print(f"Fecha de corte (censura): {manifiesto['fecha_corte']}")
    filas: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=hilos) as pool:
        futuros = {pool.submit(descargar_mes, mes, _nueva_sesion()): mes for mes in meses}
        for futuro in as_completed(futuros):
            mes = futuros[futuro]
            filas[mes] = futuro.result()
            print(f"  {mes}: {filas[mes]:>9,} filas  ({len(filas)}/{len(meses)} meses)", flush=True)
    return dict(sorted(filas.items()))


def consolidar(meses: Iterable[str] | None = None, dir_paginas: Path = DIR_PAGINAS, destino: Path = ARCHIVO_CRUDO) -> int:
    """Une todas las páginas en un solo Parquet crudo (texto con diccionario en las columnas categóricas)."""
    meses = list(meses or meses_de_ventana())
    faltan = [m for m in meses if not (dir_paginas / m / "_completo.json").exists()]
    if faltan:
        raise RuntimeError(f"Meses sin terminar: {faltan}. Ejecuta primero la descarga.")
    tablas = [pq.read_table(r) for m in meses for r in sorted((dir_paginas / m).glob("pagina_*.parquet"))]
    tabla = pa.concat_tables(tablas)
    categoricas = ["agency", "complaint_type", "descriptor", "status", "incident_zip", "borough", "open_data_channel_type"]
    for col in categoricas:
        i = tabla.column_names.index(col)
        tabla = tabla.set_column(i, col, tabla.column(col).dictionary_encode())
    destino.parent.mkdir(parents=True, exist_ok=True)
    _escribir_atomico(tabla, destino)
    return tabla.num_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--solo-consolidar", action="store_true")
    parser.add_argument("--hilos", type=int, default=HILOS_DESCARGA)
    args = parser.parse_args()
    if not args.solo_consolidar:
        filas = descargar(hilos=args.hilos)
        print(f"Total descargado: {sum(filas.values()):,} filas")
    n = consolidar()
    print(f"Consolidado: {n:,} filas -> {ARCHIVO_CRUDO.relative_to(ARCHIVO_CRUDO.parents[2])}")


if __name__ == "__main__":
    main()
