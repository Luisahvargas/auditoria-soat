"""Cuentas que llegan en documentos separados (p. ej. La Previsora).

Los archivos se llaman PREFIJO_NIT_FACTURA.pdf. Se agrupan por factura y cada factura se
audita solo con sus documentos (configuracion/soportes.yaml).
"""

import re
from dataclasses import dataclass
from functools import lru_cache

import yaml

from auditoria.config import RUTA_CONFIGURACION


@dataclass(frozen=True)
class Soporte:
    nombre: str
    prefijo: str
    nit: str
    factura: str
    contenido: bytes


@lru_cache(maxsize=2)
def configuracion_soportes() -> dict:
    return yaml.safe_load((RUTA_CONFIGURACION / "soportes.yaml").read_text(encoding="utf-8"))


def describir_prefijo(prefijo: str) -> str:
    datos = configuracion_soportes()["prefijos"].get(prefijo.upper())
    return datos["nombre"] if datos else "Documento sin descripción"


def tipo_del_prefijo(prefijo: str) -> str | None:
    datos = configuracion_soportes()["prefijos"].get(prefijo.upper())
    return datos["tipo"] if datos else None


def leer_nombre(nombre: str) -> tuple[str, str, str] | None:
    """'FEV_900385628_MDF65863.pdf' -> ('FEV', '900385628', 'MDF65863'); None si no sigue el formato."""
    m = re.match(configuracion_soportes()["patron_nombre"], nombre.strip(), re.IGNORECASE)
    if not m:
        return None
    return m.group("prefijo").upper(), m.group("nit"), m.group("factura").upper()


def agrupar_por_factura(archivos: list[tuple[str, bytes]]) -> tuple[dict[str, list[Soporte]], list[str]]:
    """Agrupa los archivos por número de factura. Devuelve (grupos, nombres que no siguen el formato)."""
    grupos: dict[str, list[Soporte]] = {}
    no_reconocidos = []
    for nombre, contenido in archivos:
        partes = leer_nombre(nombre)
        if not partes:
            no_reconocidos.append(nombre)
            continue
        prefijo, nit, factura = partes
        grupos.setdefault(factura, []).append(Soporte(nombre, prefijo, nit, factura, contenido))
    orden = {p: i for i, p in enumerate(configuracion_soportes()["prefijos"])}
    for soportes in grupos.values():
        soportes.sort(key=lambda s: (orden.get(s.prefijo, 99), s.nombre))
    return dict(sorted(grupos.items())), no_reconocidos


def documentos_faltantes(grupos: dict[str, list[Soporte]]) -> dict[str, list[str]]:
    """Prefijos que llegaron para alguna factura pero no para esta (p. ej. falta el EPI de una factura)."""
    todos = {s.prefijo for soportes in grupos.values() for s in soportes}
    return {factura: sorted(todos - {s.prefijo for s in soportes}) for factura, soportes in grupos.items()}


def repetidos(soportes: list[Soporte]) -> list[str]:
    """Prefijos que llegaron más de una vez para la misma factura."""
    conteo: dict[str, int] = {}
    for s in soportes:
        conteo[s.prefijo] = conteo.get(s.prefijo, 0) + 1
    return sorted(p for p, n in conteo.items() if n > 1)


def auditar_factura(soportes: list[Soporte], config):
    """Audita una factura con sus documentos. Devuelve (cuenta, puntos, texto) como auditar()."""
    from auditoria.revision import auditar

    return auditar(
        [(s.nombre, s.contenido) for s in soportes],
        config,
        tipos_por_archivo={s.nombre: tipo_del_prefijo(s.prefijo) for s in soportes},
        etiquetas={s.nombre: s.prefijo for s in soportes},
        factura_esperada=soportes[0].factura if soportes else None,
    )
