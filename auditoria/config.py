"""Configuración central del sistema.

Lee los valores desde el archivo .env (o variables de entorno). Nunca se escriben
claves ni rutas sensibles en el código.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Carpeta raíz del proyecto (donde están app.py y CLAUDE.md).
RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
RUTA_CONFIGURACION = RAIZ_PROYECTO / "configuracion"

MOTORES_OCR_VALIDOS = ("ninguno", "tesseract")


@dataclass(frozen=True)
class Configuracion:
    """Valores de configuración ya validados."""

    motor_ocr: str = "ninguno"
    ruta_tesseract: str = ""


def cargar_configuracion(archivo_env: Path | None = None) -> Configuracion:
    """Carga la configuración desde .env y variables de entorno (sin OCR por defecto)."""
    load_dotenv(archivo_env or RAIZ_PROYECTO / ".env", override=False)

    motor_ocr = os.getenv("OCR_MOTOR", "ninguno").strip().lower() or "ninguno"
    if motor_ocr not in MOTORES_OCR_VALIDOS:
        raise ValueError(f"OCR_MOTOR='{motor_ocr}' no es válido. Opciones: {', '.join(MOTORES_OCR_VALIDOS)}")

    return Configuracion(motor_ocr=motor_ocr, ruta_tesseract=os.getenv("RUTA_TESSERACT", "").strip())
