"""Única puerta de entrada a PyMuPDF.

Ningún otro módulo debe importar pymupdf directamente, para poder reemplazarlo.
Las páginas (folios) se numeran SIEMPRE desde 1, igual que en el archivo original.
Los PDF se leen en memoria: el original nunca se modifica ni se copia.
"""

from collections.abc import Iterator
from dataclasses import dataclass

import pymupdf


class ErrorLecturaPDF(Exception):
    """El PDF no se puede abrir o leer (dañado, protegido con contraseña, etc.)."""


@dataclass(frozen=True)
class PaginaLeida:
    numero: int  # Folio del archivo, desde 1
    texto: str


def _abrir(contenido: bytes) -> pymupdf.Document:
    try:
        documento = pymupdf.open(stream=contenido, filetype="pdf")
    except Exception as error:  # PyMuPDF lanza varios tipos según el daño del archivo
        raise ErrorLecturaPDF(f"No se pudo abrir el PDF: {error}") from error
    if documento.needs_pass:
        documento.close()
        raise ErrorLecturaPDF("El PDF está protegido con contraseña.")
    return documento


def leer_paginas(contenido: bytes) -> Iterator[PaginaLeida]:
    """Recorre las páginas una por una."""
    with _abrir(contenido) as documento:
        for indice in range(documento.page_count):
            try:
                texto = documento[indice].get_text("text", sort=True)
            except Exception as error:
                raise ErrorLecturaPDF(f"Error leyendo el folio {indice + 1}: {error}") from error
            yield PaginaLeida(numero=indice + 1, texto=texto or "")


def porcentaje_en_blanco(contenido: bytes, numero: int) -> float:
    """Porcentaje de píxeles casi blancos de una página (100 = hoja en blanco)."""
    with _abrir(contenido) as documento:
        pagina = documento[numero - 1]
        imagen = pagina.get_pixmap(matrix=pymupdf.Matrix(0.3, 0.3), colorspace=pymupdf.csGRAY, alpha=False)
        muestras = imagen.samples
        claros = sum(1 for valor in muestras if valor > 240)
        return 100 * claros / max(len(muestras), 1)


def renderizar_pagina(contenido: bytes, numero: int, ancho_px: int = 2000) -> bytes:
    """Imagen PNG de una página (para el OCR)."""
    with _abrir(contenido) as documento:
        if not 1 <= numero <= documento.page_count:
            raise ErrorLecturaPDF(f"El folio {numero} no existe (el archivo tiene {documento.page_count}).")
        pagina = documento[numero - 1]
        escala = ancho_px / max(pagina.rect.width, 1)
        return pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=False).tobytes("png")
