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
    ruta_tessdata: str = ""  # Carpeta con spa.traineddata (si no está en la instalación de Tesseract)


# Carpeta por defecto del idioma español descargado para Tesseract (no requiere administrador).
TESSDATA_USUARIO = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "auditoria_soat" / "tessdata"


def cargar_configuracion(archivo_env: Path | None = None) -> Configuracion:
    """Carga la configuración desde .env y variables de entorno (sin OCR por defecto)."""
    load_dotenv(archivo_env or RAIZ_PROYECTO / ".env", override=False)

    motor_ocr = os.getenv("OCR_MOTOR", "ninguno").strip().lower() or "ninguno"
    if motor_ocr not in MOTORES_OCR_VALIDOS:
        raise ValueError(f"OCR_MOTOR='{motor_ocr}' no es válido. Opciones: {', '.join(MOTORES_OCR_VALIDOS)}")

    ruta_tessdata = os.getenv("RUTA_TESSDATA", "").strip()
    if not ruta_tessdata and (TESSDATA_USUARIO / "spa.traineddata").exists():
        ruta_tessdata = str(TESSDATA_USUARIO)

    return Configuracion(
        motor_ocr=motor_ocr,
        ruta_tesseract=os.getenv("RUTA_TESSERACT", "").strip(),
        ruta_tessdata=ruta_tessdata,
    )
