"""Copia de los archivos originales a la carpeta de datos con su hash SHA-256.

Los originales nunca se modifican: se guardan con el hash como nombre y en modo
solo lectura. El nombre original del archivo queda en la base de datos.
"""

import hashlib
import os
import stat
from pathlib import Path


class ErrorAlmacenamiento(Exception):
    """Ruta inválida o problema al guardar un archivo."""


def calcular_sha256(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def guardar_original(ruta_datos: Path, auditoria_id: int, contenido: bytes, extension: str) -> str:
    """Guarda una copia exacta del archivo y devuelve su ruta relativa a la carpeta de datos."""
    hash_archivo = calcular_sha256(contenido)
    ruta_relativa = Path("originales") / str(auditoria_id) / f"{hash_archivo}.{extension}"
    destino = ruta_datos / ruta_relativa
    destino.parent.mkdir(parents=True, exist_ok=True)

    if not destino.exists():
        destino.write_bytes(contenido)
        os.chmod(destino, stat.S_IREAD)  # Solo lectura: protege el original

    if calcular_sha256(destino.read_bytes()) != hash_archivo:
        raise ErrorAlmacenamiento("La copia guardada no coincide con el original (hash distinto).")
    return ruta_relativa.as_posix()


def ruta_absoluta(ruta_datos: Path, ruta_relativa: str) -> Path:
    """Convierte una ruta guardada en la base a ruta real, sin permitir salir de la carpeta de datos."""
    base = ruta_datos.resolve()
    ruta = (base / ruta_relativa).resolve()
    if base not in ruta.parents:
        raise ErrorAlmacenamiento("Ruta de archivo fuera de la carpeta de datos.")
    return ruta


def ruta_miniatura(ruta_datos: Path, hash_archivo: str, numero_pagina: int, ancho_px: int) -> Path:
    return ruta_datos / "miniaturas" / hash_archivo / f"p{numero_pagina:04d}_{ancho_px}.png"
