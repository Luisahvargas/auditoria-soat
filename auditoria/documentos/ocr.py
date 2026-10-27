"""OCR opcional: "ninguno" o "tesseract".

El OCR nunca es obligatorio. Si Tesseract no está instalado (o no tiene el idioma
español), los folios escaneados se informan como "no se pudieron leer".
Tesseract se ejecuta localmente: no envía nada fuera del equipo.
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
TIEMPO_MAXIMO_SEGUNDOS = 120


@dataclass(frozen=True)
class EstadoOCR:
    disponible: bool
    mensaje: str
    ejecutable: str = ""
    tessdata: str = ""

    def comando(self, *argumentos: str) -> list[str]:
        base = [self.ejecutable]
        if self.tessdata:
            base += ["--tessdata-dir", self.tessdata]
        return base + list(argumentos)


def estado_ocr(config: Configuracion) -> EstadoOCR:
    if config.motor_ocr != "tesseract":
        return EstadoOCR(False, "OCR desactivado: los folios escaneados no se pueden leer.")
    return _detectar_tesseract(config.ruta_tesseract, config.ruta_tessdata)


@lru_cache(maxsize=4)
def _detectar_tesseract(ruta_configurada: str, tessdata: str) -> EstadoOCR:
    candidatos = [ruta_configurada] if ruta_configurada else []
    candidatos += [shutil.which("tesseract") or ""] + [str(r) for r in RUTAS_HABITUALES_WINDOWS]
    ejecutable = next((c for c in candidatos if c and Path(c).exists()), "")
    if not ejecutable:
        return EstadoOCR(False, "Tesseract no está instalado: los folios escaneados no se pueden leer.")
    estado = EstadoOCR(False, "", ejecutable, tessdata)
    try:
        salida = subprocess.run(estado.comando("--list-langs"), capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        return EstadoOCR(False, f"No se pudo ejecutar Tesseract: {error}")
    if "spa" not in (salida.stdout + salida.stderr).split():
        return EstadoOCR(False, "Tesseract está instalado pero sin el idioma español (spa).", ejecutable, tessdata)
    return EstadoOCR(True, "OCR con Tesseract (español) activo.", ejecutable, tessdata)


def ocr_imagen(estado: EstadoOCR, imagen_png: bytes) -> str:
    """Texto reconocido en una imagen PNG. Lanza RuntimeError si Tesseract falla."""
    resultado = subprocess.run(
        estado.comando("stdin", "stdout", "-l", "spa", "--psm", "4"),
        input=imagen_png,
        capture_output=True,
        timeout=TIEMPO_MAXIMO_SEGUNDOS,
        check=False,
    )
    if resultado.returncode != 0:
        raise RuntimeError(resultado.stderr.decode("utf-8", errors="replace")[:300])
    return resultado.stdout.decode("utf-8", errors="replace")
