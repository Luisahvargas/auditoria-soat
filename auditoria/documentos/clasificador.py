"""Clasificación de folios por palabras clave (configuracion/tipos_documento.yaml).

Es una clasificación preliminar: sirve para saber qué folio es el FURIPS, cuál la
factura, cuál la hoja de admisión, etc. Si se equivoca, se ajustan las palabras clave
en el YAML sin reprogramar.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from auditoria.config import RUTA_CONFIGURACION
from auditoria.texto import normalizar

RUTA_TIPOS = RUTA_CONFIGURACION / "tipos_documento.yaml"
PESO_FUERTE = 3
PESO_APOYO = 1


@dataclass(frozen=True)
class TipoDocumental:
    nombre: str
    fuertes: tuple[re.Pattern, ...]
    apoyo: tuple[re.Pattern, ...]


@dataclass(frozen=True)
class CatalogoTipos:
    version: str
    puntaje_minimo: int
    tipo_por_defecto: str
    tipos: tuple[TipoDocumental, ...]


def _patron(palabra: str) -> re.Pattern:
    return re.compile(r"\b" + re.escape(normalizar(str(palabra))) + r"\b")


@lru_cache(maxsize=4)
def cargar_tipos(ruta: Path = RUTA_TIPOS) -> CatalogoTipos:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    tipos = tuple(
        TipoDocumental(
            nombre=t["nombre"],
            fuertes=tuple(_patron(p) for p in t.get("fuertes", [])),
            apoyo=tuple(_patron(p) for p in t.get("apoyo", [])),
        )
        for t in datos["tipos"]
    )
    return CatalogoTipos(
        version=str(datos.get("version", "")),
        puntaje_minimo=int(datos.get("puntaje_minimo", 3)),
        tipo_por_defecto=datos.get("tipo_por_defecto", "Otros"),
        tipos=tipos,
    )


def clasificar_texto(texto: str) -> str | None:
    """Tipo documental propuesto para un folio. Sin texto devuelve None."""
    catalogo = cargar_tipos()
    normalizado = normalizar(texto)
    if not normalizado:
        return None
    puntajes = {}
    for tipo in catalogo.tipos:
        puntos = sum(PESO_FUERTE for p in tipo.fuertes if p.search(normalizado))
        puntos += sum(PESO_APOYO for p in tipo.apoyo if p.search(normalizado))
        if puntos:
            puntajes[tipo.nombre] = puntos
    if not puntajes:
        return catalogo.tipo_por_defecto
    mejor, puntos = max(puntajes.items(), key=lambda par: par[1])
    return mejor if puntos >= catalogo.puntaje_minimo else catalogo.tipo_por_defecto
