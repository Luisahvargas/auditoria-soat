"""Verifica que el entorno tenga todo lo necesario para ejecutar la aplicación.

Uso:  .\\.venv\\Scripts\\python.exe scripts\\verificar_entorno.py
"""

import importlib
import sys
from importlib import metadata
from pathlib import Path

# Permite importar el paquete 'auditoria' al ejecutar el script directamente.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# (nombre del paquete instalado, nombre del módulo a importar)
DEPENDENCIAS = [
    ("streamlit", "streamlit"),
    ("pymupdf", "pymupdf"),
    ("python-dotenv", "dotenv"),
    ("PyYAML", "yaml"),
    ("pytest", "pytest"),
    ("reportlab", "reportlab"),
]


def verificar() -> bool:
    todo_bien = True

    version = sys.version_info
    python_ok = version[:2] in ((3, 11), (3, 12))
    todo_bien &= python_ok
    print(f"[{'OK' if python_ok else 'ERROR'}] Python {version.major}.{version.minor}.{version.micro} (se requiere 3.11 o 3.12)")

    for paquete, modulo in DEPENDENCIAS:
        try:
            importlib.import_module(modulo)
            print(f"[OK] {paquete} {metadata.version(paquete)}")
        except Exception as error:  # noqa: BLE001 - se informa cualquier fallo de importación
            todo_bien = False
            print(f"[ERROR] {paquete}: {error}")

    try:
        from auditoria.config import cargar_configuracion
        from auditoria.documentos.ocr import estado_ocr

        print(f"[OPCIONAL] OCR: {estado_ocr(cargar_configuracion()).mensaje}")
    except Exception as error:  # noqa: BLE001
        todo_bien = False
        print(f"[ERROR] Configuración: {error}")

    print("\nResultado:", "entorno listo." if todo_bien else "hay problemas que corregir.")
    return todo_bien


if __name__ == "__main__":
    sys.exit(0 if verificar() else 1)
