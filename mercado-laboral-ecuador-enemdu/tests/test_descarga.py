"""Descarga segura: TLS verificado y SHA-256 comprobado contra docs/fuentes.md (sin red)."""

from __future__ import annotations

import hashlib
import io
import ssl
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from empleo_enemdu import descarga
from empleo_enemdu.config import RAIZ, SHA256_ESPERADO
from empleo_enemdu.descarga import ErrorIntegridad, crear_contexto_tls, descargar_archivo, verificar_sha256

CONTENIDO = b"contenido de prueba del INEC"
SHA = hashlib.sha256(CONTENIDO).hexdigest()
URL = "https://www.ecuadorencifras.gob.ec/documentos/prueba.zip"


class _Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def servidor(monkeypatch):
    """Sustituye urlopen por una respuesta fija y cuenta las llamadas y los contextos TLS usados."""
    estado = {"llamadas": 0, "contextos": [], "cuerpo": CONTENIDO}

    def falso_urlopen(req, context=None, timeout=None):
        estado["llamadas"] += 1
        estado["contextos"].append(context)
        return _Respuesta(estado["cuerpo"])

    monkeypatch.setattr(urllib.request, "urlopen", falso_urlopen)
    monkeypatch.setattr(descarga.time, "sleep", lambda *_: None)
    return estado


def test_descarga_correcta_guarda_el_archivo_y_devuelve_el_hash(tmp_path: Path, servidor) -> None:
    destino = tmp_path / "prueba.zip"
    info = descargar_archivo(URL, destino, sha256_esperado=SHA)
    assert destino.read_bytes() == CONTENIDO
    assert info["sha256"] == SHA and info["desde_cache"] is False


def test_hash_distinto_aborta_y_no_deja_archivo(tmp_path: Path, servidor) -> None:
    servidor["cuerpo"] = b"contenido alterado en el camino"
    destino = tmp_path / "prueba.zip"
    with pytest.raises(ErrorIntegridad, match="no coincide"):
        descargar_archivo(URL, destino, sha256_esperado=SHA)
    assert not destino.exists()
    assert not list(tmp_path.glob("*.tmp"))
    assert servidor["llamadas"] == 1  # un fallo de integridad no se reintenta


def test_archivo_en_cache_con_hash_incorrecto_aborta(tmp_path: Path, servidor) -> None:
    destino = tmp_path / "prueba.zip"
    destino.write_bytes(b"corrupto")
    with pytest.raises(ErrorIntegridad):
        descargar_archivo(URL, destino, sha256_esperado=SHA)
    assert servidor["llamadas"] == 0


def test_archivo_en_cache_correcto_no_toca_la_red(tmp_path: Path, servidor) -> None:
    destino = tmp_path / "prueba.zip"
    destino.write_bytes(CONTENIDO)
    info = descargar_archivo(URL, destino, sha256_esperado=SHA)
    assert info["desde_cache"] is True and servidor["llamadas"] == 0


def test_sin_hash_conocido_no_se_descarga(tmp_path: Path, servidor) -> None:
    with pytest.raises(ErrorIntegridad, match="SHA-256 esperado"):
        descargar_archivo(URL, tmp_path / "desconocido.zip")
    assert servidor["llamadas"] == 0


def test_verificar_sha256_acepta_mayusculas_y_rechaza_otro_hash(tmp_path: Path) -> None:
    ruta = tmp_path / "a.bin"
    ruta.write_bytes(CONTENIDO)
    assert verificar_sha256(ruta, SHA.upper()) == SHA
    with pytest.raises(ErrorIntegridad):
        verificar_sha256(ruta, "0" * 64)


def test_contexto_por_defecto_verifica_certificado_y_nombre() -> None:
    ctx = crear_contexto_tls()
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True


def test_descarga_usa_contexto_verificado(tmp_path: Path, servidor) -> None:
    descargar_archivo(URL, tmp_path / "prueba.zip", sha256_esperado=SHA)
    ctx = servidor["contextos"][0]
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True


def test_alternativa_explicita_con_certifi_mantiene_la_verificacion() -> None:
    pytest.importorskip("certifi")
    ctx = crear_contexto_tls("certifi")
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True


def test_paquete_de_certificados_inexistente_falla(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        crear_contexto_tls(str(tmp_path / "no_existe.pem"))


def test_error_de_certificado_no_se_reintenta_y_explica_la_alternativa(tmp_path: Path, monkeypatch) -> None:
    llamadas = []

    def falla(req, context=None, timeout=None):
        llamadas.append(1)
        raise urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed"))

    monkeypatch.setattr(urllib.request, "urlopen", falla)
    with pytest.raises(RuntimeError, match="certifi"):
        descargar_archivo(URL, tmp_path / "prueba.zip", sha256_esperado=SHA)
    assert len(llamadas) == 1


def test_el_codigo_no_desactiva_la_verificacion_tls() -> None:
    fuente = (RAIZ / "src" / "empleo_enemdu" / "descarga.py").read_text(encoding="utf-8")
    assert "_create_unverified_context" not in fuente
    assert "CERT_NONE" not in fuente and "check_hostname = False" not in fuente


def test_hashes_del_codigo_coinciden_con_docs_fuentes() -> None:
    """docs/fuentes.md y SHA256_ESPERADO deben decir lo mismo."""
    texto = (RAIZ / "docs" / "fuentes.md").read_text(encoding="utf-8")
    for nombre, sha in SHA256_ESPERADO.items():
        fila = next((l for l in texto.splitlines() if nombre in l and "|" in l), None)
        assert fila is not None, f"{nombre} no aparece en docs/fuentes.md"
        assert f"`{sha}`" in fila, f"El SHA-256 de {nombre} difiere de docs/fuentes.md"
