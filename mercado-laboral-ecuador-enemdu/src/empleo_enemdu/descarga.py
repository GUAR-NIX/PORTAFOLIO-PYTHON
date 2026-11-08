"""Descarga de microdatos, tabulados, diccionario y sintaxis oficial del INEC (ENEMDU)."""

from __future__ import annotations

import hashlib
import os
import ssl
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from empleo_enemdu.config import DIR_RAW, SHA256_ESPERADO, URLS_INEC_2025

# Variable de entorno para elegir los certificados raíz si el contexto por defecto no valida el sitio del INEC:
# `certifi` (paquete de certificados de Mozilla) o la ruta a un archivo .pem.
VAR_CERTIFICADOS = "ENEMDU_CERTIFICADOS"


class ErrorIntegridad(Exception):
    """El archivo descargado no coincide con el SHA-256 esperado (docs/fuentes.md)."""


def crear_contexto_tls(certificados: str | None = None) -> ssl.SSLContext:
    """Contexto TLS **con verificación del certificado y del nombre del servidor**.

    Por defecto usa los certificados del sistema. Si el certificado del INEC no se valida (cadena incompleta
    en el servidor, por ejemplo), la alternativa es explícita: ``certificados="certifi"`` o la ruta a un
    paquete .pem, o la variable de entorno ``ENEMDU_CERTIFICADOS``. Nunca se desactiva la verificación.
    """
    certificados = certificados or os.environ.get(VAR_CERTIFICADOS) or None
    if certificados is None:
        return ssl.create_default_context()
    if certificados.lower() == "certifi":
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    if not Path(certificados).is_file():
        raise FileNotFoundError(f"No existe el paquete de certificados: {certificados}")
    return ssl.create_default_context(cafile=certificados)


def verificar_sha256(ruta: Path, esperado: str) -> str:
    """Comprueba el SHA-256 de un archivo en disco; lanza ErrorIntegridad si no coincide."""
    obtenido = calcular_sha256(ruta)
    if obtenido != esperado.lower():
        raise ErrorIntegridad(
            f"SHA-256 de {ruta.name} no coincide: esperado {esperado}, obtenido {obtenido}. "
            "Si el INEC republicó el archivo, revisa docs/fuentes.md y actualiza SHA256_ESPERADO."
        )
    return obtenido


def calcular_sha256(ruta: Path) -> str:
    """Calcula el resumen SHA-256 de un archivo en disco."""
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def descargar_archivo(
    url: str,
    destino: Path,
    *,
    forzar: bool = False,
    reintentos: int = 4,
    espera_inicial: float = 2.0,
    timeout: int = 120,
    sha256_esperado: str | None = None,
    certificados: str | None = None,
) -> dict[str, Any]:
    """Descarga un archivo con TLS verificado, escritura atómica, caché en disco y reintentos.

    El SHA-256 se compara con el de ``docs/fuentes.md`` (``SHA256_ESPERADO``) **antes** de guardar el archivo;
    si no coincide (o si no hay hash conocido) la descarga se aborta con ``ErrorIntegridad`` y no queda nada
    en disco. El archivo que ya está en caché también se verifica.
    """
    esperado = sha256_esperado or SHA256_ESPERADO.get(destino.name)
    if not esperado:
        raise ErrorIntegridad(f"No hay SHA-256 esperado para {destino.name}; añádelo a SHA256_ESPERADO.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and destino.stat().st_size > 0 and not forzar:
        return {
            "archivo": destino.name,
            "url": url,
            "bytes": destino.stat().st_size,
            "sha256": verificar_sha256(destino, esperado),
            "desde_cache": True,
        }

    ctx = crear_contexto_tls(certificados)
    ultimo_error: Exception | None = None
    for intento in range(1, reintentos + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "PYTHON_06_empleo_enemdu/1.0"
                    )
                },
            )
            temporal = destino.with_suffix(destino.suffix + ".tmp")
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
                contenido = resp.read()
            if not contenido:
                raise RuntimeError(f"Respuesta vacía desde {url}")
            obtenido = hashlib.sha256(contenido).hexdigest()
            if obtenido != esperado.lower():
                raise ErrorIntegridad(
                    f"SHA-256 de {destino.name} no coincide: esperado {esperado}, obtenido {obtenido}. "
                    "Descarga abortada; si el INEC republicó el archivo, revisa docs/fuentes.md."
                )
            temporal.write_bytes(contenido)
            temporal.replace(destino)
            return {
                "archivo": destino.name,
                "url": url,
                "bytes": destino.stat().st_size,
                "sha256": obtenido,
                "desde_cache": False,
            }
        except ErrorIntegridad:
            raise
        except (urllib.error.URLError, TimeoutError, RuntimeError, OSError) as exc:
            if isinstance(getattr(exc, "reason", exc), ssl.SSLCertVerificationError):
                raise RuntimeError(
                    f"El certificado TLS de {url} no se pudo verificar ({exc}). No se desactiva la verificación: "
                    f"usa los certificados de certifi con `--certificados certifi` o {VAR_CERTIFICADOS}=certifi "
                    "(o la ruta a un paquete .pem). El SHA-256 de la descarga se comprobará de todos modos."
                ) from exc
            ultimo_error = exc
            if intento < reintentos:
                time.sleep(espera_inicial * (2 ** (intento - 1)))
    raise RuntimeError(f"No se pudo descargar {url} tras {reintentos} intentos: {ultimo_error}")


def extraer_zip(ruta_zip: Path, destino_dir: Path) -> list[str]:
    """Extrae un archivo ZIP preservando los nombres de archivo."""
    destino_dir.mkdir(parents=True, exist_ok=True)
    extraidos: list[str] = []
    with zipfile.ZipFile(ruta_zip, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            zf.extract(info, destino_dir)
            extraidos.append(info.filename)
    return extraidos


def descargar_todo(
    dir_raw: Path = DIR_RAW,
    *,
    forzar: bool = False,
    certificados: str | None = None,
) -> dict[str, Any]:
    """Descarga (con TLS y SHA-256 verificados) y descomprime los 4 paquetes oficiales de la ENEMDU Anual 2025 del INEC."""
    dir_raw.mkdir(parents=True, exist_ok=True)
    registro: dict[str, Any] = {}

    nombres_zip = {
        "microdatos_csv": "2_BDD_DATOS_ABIERTOS_ENEMDU_2025_CSV.zip",
        "tabulados_csv": "ENEMDU_Tabulados_anual_2025-CSV.zip",
        "diccionario_variables": "Diccionario_de_variables.zip",
        "sintaxis_spss": "Sintaxis_anual_2025.zip",
    }

    for clave, url in URLS_INEC_2025.items():
        ruta_zip = dir_raw / nombres_zip[clave]
        info_descarga = descargar_archivo(url, ruta_zip, forzar=forzar, certificados=certificados)
        subcarpeta = dir_raw / clave if clave != "microdatos_csv" else dir_raw
        archivos = extraer_zip(ruta_zip, subcarpeta)
        info_descarga["extraidos"] = archivos
        registro[clave] = info_descarga

    return registro
