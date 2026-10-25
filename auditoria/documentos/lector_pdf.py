"""Única puerta de entrada a PyMuPDF.

Ningún otro módulo debe importar pymupdf directamente, para poder reemplazarlo.
Las páginas se numeran SIEMPRE desde 1, igual que en el archivo original.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pymupdf


class ErrorLecturaPDF(Exception):
    """El PDF no se puede abrir o leer (dañado, protegido con contraseña, etc.)."""


@dataclass(frozen=True)
class PaginaLeida:
    numero: int  # Página del archivo, desde 1
    texto: str


def _abrir(ruta: Path) -> pymupdf.Document:
    try:
        documento = pymupdf.open(ruta)
    except Exception as error:  # PyMuPDF lanza varios tipos según el daño del archivo
        raise ErrorLecturaPDF(f"No se pudo abrir el PDF: {error}") from error
    if not documento.is_pdf:
        documento.close()
        raise ErrorLecturaPDF("El archivo no es un PDF válido.")
    if documento.needs_pass:
        documento.close()
        raise ErrorLecturaPDF("El PDF está protegido con contraseña.")
    return documento


def contar_paginas(ruta: Path) -> int:
    with _abrir(ruta) as documento:
        return documento.page_count


def leer_paginas(ruta: Path) -> Iterator[PaginaLeida]:
    """Recorre las páginas una por una (sin cargar todo el PDF en memoria)."""
    with _abrir(ruta) as documento:
        for indice in range(documento.page_count):
            try:
                texto = documento[indice].get_text("text", sort=True)
            except Exception as error:
                raise ErrorLecturaPDF(f"Error leyendo la página {indice + 1}: {error}") from error
            yield PaginaLeida(numero=indice + 1, texto=texto or "")


def renderizar_pagina(ruta: Path, numero: int, ancho_px: int = 900) -> bytes:
    """Imagen PNG de una página (para la vista de documentos y el OCR)."""
    with _abrir(ruta) as documento:
        if not 1 <= numero <= documento.page_count:
            raise ErrorLecturaPDF(f"La página {numero} no existe (el archivo tiene {documento.page_count}).")
        pagina = documento[numero - 1]
        escala = ancho_px / max(pagina.rect.width, 1)
        imagen = pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=False)
        return imagen.tobytes("png")
