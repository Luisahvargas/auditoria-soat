"""Interfaz de OCR opcional: "ninguno" (por defecto) o "tesseract".

El OCR nunca es obligatorio. Si Tesseract no está instalado (o no tiene el idioma
español), la app sigue funcionando y las páginas sin texto quedan marcadas como
"pendiente de análisis visual". Tesseract se ejecuta localmente: no envía nada fuera.
"""

import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from auditoria.config import Configuracion

RUTAS_HABITUALES_WINDOWS = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)
ANCHO_OCR_PX = 2000  # Resolución suficiente para OCR sin consumir demasiada memoria
TIEMPO_MAXIMO_SEGUNDOS = 120


@dataclass(frozen=True)
class EstadoOCR:
    disponible: bool
    motor: str
    mensaje: str
    ejecutable: str = ""


def estado_ocr(config: Configuracion) -> EstadoOCR:
    if config.motor_ocr != "tesseract":
        return EstadoOCR(False, "ninguno", "OCR desactivado: las páginas sin texto quedan pendientes de análisis visual.")
    return _detectar_tesseract(config.ruta_tesseract)


@lru_cache(maxsize=4)
def _detectar_tesseract(ruta_configurada: str) -> EstadoOCR:
    candidatos = [ruta_configurada] if ruta_configurada else []
    candidatos += [shutil.which("tesseract") or ""] + [str(r) for r in RUTAS_HABITUALES_WINDOWS]
    ejecutable = next((c for c in candidatos if c and Path(c).exists()), "")
    if not ejecutable:
        return EstadoOCR(False, "tesseract", "Tesseract no está instalado: las páginas sin texto quedan pendientes de análisis visual.")
    try:
        salida = subprocess.run(
            [ejecutable, "--list-langs"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError) as error:
        return EstadoOCR(False, "tesseract", f"No se pudo ejecutar Tesseract: {error}")
    idiomas = (salida.stdout + salida.stderr).split()
    if "spa" not in idiomas:
        return EstadoOCR(False, "tesseract", "Tesseract está instalado pero sin el idioma español (spa).", ejecutable)
    return EstadoOCR(True, "tesseract", "Tesseract disponible con idioma español.", ejecutable)


def ocr_imagen(estado: EstadoOCR, imagen_png: bytes) -> str:
    """Texto reconocido en una imagen PNG. Lanza RuntimeError si Tesseract falla."""
    resultado = subprocess.run(
        [estado.ejecutable, "stdin", "stdout", "-l", "spa"],
        input=imagen_png,
        capture_output=True,
        timeout=TIEMPO_MAXIMO_SEGUNDOS,
        check=False,
    )
    if resultado.returncode != 0:
        raise RuntimeError(resultado.stderr.decode("utf-8", errors="replace")[:300])
    return resultado.stdout.decode("utf-8", errors="replace")


def aplicar_ocr_documento(config: Configuracion, documento) -> int:
    """Aplica OCR a las páginas sin texto de un documento. Devuelve cuántas páginas se procesaron.

    Sin OCR disponible no hace nada (las páginas siguen marcadas para análisis visual).
    """
    estado = estado_ocr(config)
    if not estado.disponible:
        for pagina in documento.paginas:
            if pagina.requiere_analisis_visual:
                pagina.metodo_texto = "Sin texto"
        return 0

    from auditoria.documentos import almacenamiento, lector_pdf
    from auditoria.documentos.inventario import MINIMO_CARACTERES_TEXTO, contar_caracteres

    ruta = almacenamiento.ruta_absoluta(config.ruta_datos, documento.ruta_relativa)
    procesadas = 0
    for pagina in documento.paginas:
        if not pagina.requiere_analisis_visual:
            continue
        try:
            texto = ocr_imagen(estado, lector_pdf.renderizar_pagina(ruta, pagina.numero, ANCHO_OCR_PX))
        except (RuntimeError, OSError, subprocess.SubprocessError, lector_pdf.ErrorLecturaPDF):
            pagina.metodo_texto = "Sin texto"
            continue
        procesadas += 1
        pagina.texto = texto
        pagina.caracteres = contar_caracteres(texto)
        pagina.metodo_texto = "OCR"
        pagina.requiere_analisis_visual = pagina.caracteres < MINIMO_CARACTERES_TEXTO
    return procesadas
