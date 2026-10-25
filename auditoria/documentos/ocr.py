"""Interfaz de OCR opcional (sin OCR / Tesseract). Nunca obligatorio para arrancar. (Fase 6)"""


def aplicar_ocr_documento(config, documento) -> None:
    """Sin OCR: las páginas sin texto quedan marcadas para análisis visual."""
