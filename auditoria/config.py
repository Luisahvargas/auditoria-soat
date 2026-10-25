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

PROVEEDORES_IA_VALIDOS = ("desactivado", "puente_manual", "anthropic", "ollama")
MOTORES_OCR_VALIDOS = ("ninguno", "tesseract")


@dataclass(frozen=True)
class Configuracion:
    """Valores de configuración ya validados."""

    ruta_datos: Path
    url_base_datos: str
    proveedor_ia: str = "desactivado"
    anthropic_api_key: str = ""
    anthropic_modelo: str = ""
    motor_ocr: str = "ninguno"
    ruta_tesseract: str = ""
    ruta_configuracion: Path = RAIZ_PROYECTO / "configuracion"

    @property
    def ia_anthropic_disponible(self) -> bool:
        """La API solo se considera disponible si hay clave y está seleccionada."""
        return self.proveedor_ia == "anthropic" and bool(self.anthropic_api_key)


def cargar_configuracion(archivo_env: Path | None = None) -> Configuracion:
    """Carga la configuración desde .env y variables de entorno.

    Si no existe .env se usan valores por defecto seguros (sin IA, SQLite local).
    """
    load_dotenv(archivo_env or RAIZ_PROYECTO / ".env", override=False)

    ruta_datos = Path(os.getenv("RUTA_DATOS", "datos") or "datos")
    if not ruta_datos.is_absolute():
        ruta_datos = RAIZ_PROYECTO / ruta_datos

    url_base_datos = os.getenv("URL_BASE_DATOS", "").strip()
    if not url_base_datos:
        url_base_datos = f"sqlite:///{(ruta_datos / 'auditoria.db').as_posix()}"

    proveedor_ia = os.getenv("PROVEEDOR_IA", "desactivado").strip().lower() or "desactivado"
    if proveedor_ia not in PROVEEDORES_IA_VALIDOS:
        raise ValueError(
            f"PROVEEDOR_IA='{proveedor_ia}' no es válido. "
            f"Opciones: {', '.join(PROVEEDORES_IA_VALIDOS)}"
        )

    motor_ocr = os.getenv("OCR_MOTOR", "ninguno").strip().lower() or "ninguno"
    if motor_ocr not in MOTORES_OCR_VALIDOS:
        raise ValueError(f"OCR_MOTOR='{motor_ocr}' no es válido. Opciones: {', '.join(MOTORES_OCR_VALIDOS)}")

    return Configuracion(
        ruta_datos=ruta_datos,
        url_base_datos=url_base_datos,
        proveedor_ia=proveedor_ia,
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        anthropic_modelo=os.getenv("ANTHROPIC_MODELO", "").strip(),
        motor_ocr=motor_ocr,
        ruta_tesseract=os.getenv("RUTA_TESSERACT", "").strip(),
    )


def preparar_carpetas(config: Configuracion) -> None:
    """Crea la carpeta de datos y sus subcarpetas si no existen."""
    for subcarpeta in ("", "originales", "miniaturas"):
        (config.ruta_datos / subcarpeta).mkdir(parents=True, exist_ok=True)
