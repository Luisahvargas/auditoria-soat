"""Cuentas que llegan en varios documentos (p. ej. La Previsora).

Se suben todos los documentos de UNA factura, con cualquier nombre. Si el nombre sigue el
formato PREFIJO_NIT_FACTURA.pdf (FEV, EPI, FURIPS...), el prefijo solo sirve como pista para
clasificar los folios y para citarlos de forma corta (configuracion/soportes.yaml).
"""

import re
from functools import lru_cache

import yaml

from auditoria.config import RUTA_CONFIGURACION


@lru_cache(maxsize=2)
def configuracion_soportes() -> dict:
    return yaml.safe_load((RUTA_CONFIGURACION / "soportes.yaml").read_text(encoding="utf-8"))


def leer_nombre(nombre: str) -> tuple[str, str, str] | None:
    """'FEV_900385628_MDF65863.pdf' -> ('FEV', '900385628', 'MDF65863'); None si no sigue el formato."""
    m = re.match(configuracion_soportes()["patron_nombre"], nombre.strip(), re.IGNORECASE)
    if not m:
        return None
    return m.group("prefijo").upper(), m.group("nit"), m.group("factura").upper()


def describir_prefijo(prefijo: str) -> str:
    datos = configuracion_soportes()["prefijos"].get(prefijo.upper())
    return datos["nombre"] if datos else ""


def tipo_sugerido(nombre: str) -> str | None:
    """Tipo documental que sugiere el nombre del archivo (si sigue el formato y el prefijo es conocido)."""
    partes = leer_nombre(nombre)
    if not partes:
        return None
    datos = configuracion_soportes()["prefijos"].get(partes[0])
    return datos["tipo"] if datos else None


def etiqueta(nombre: str) -> str:
    """Nombre corto para citar folios: el prefijo (FEV, EPI...) o el nombre del archivo recortado."""
    partes = leer_nombre(nombre)
    if partes:
        return partes[0]
    base = re.sub(r"\.pdf$", "", nombre, flags=re.IGNORECASE)
    return base if len(base) <= 40 else base[:37] + "…"


def auditar_documentos(archivos: list[tuple[str, bytes]], config):
    """Audita todos los documentos de una factura. Devuelve (cuenta, puntos, texto) como auditar()."""
    from auditoria.revision import auditar

    nombres = [n for n, _ in archivos]
    cortas = {n: etiqueta(n) for n in nombres}
    # Si dos archivos quedan con la misma etiqueta, se usa el nombre completo para no confundirlos.
    repetidas = {e for e in cortas.values() if list(cortas.values()).count(e) > 1}
    etiquetas = {n: (n if e in repetidas else e) for n, e in cortas.items()}
    return auditar(archivos, config, tipos_por_archivo={n: tipo_sugerido(n) for n in nombres}, etiquetas=etiquetas)
