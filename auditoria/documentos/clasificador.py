"""Clasificación de folios (configuracion/tipos_documento.yaml).

1. Título del documento en las primeras líneas del folio.
2. Sin título: el folio continúa el documento anterior (lo decide quien llama).
3. Sin título ni folio anterior: palabras clave.
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
MAXIMO_PALABRAS_TITULO = 10


@dataclass(frozen=True)
class TipoDocumental:
    nombre: str
    titulos: tuple[re.Pattern, ...]
    fuertes: tuple[re.Pattern, ...]
    apoyo: tuple[re.Pattern, ...]


@dataclass(frozen=True)
class CatalogoTipos:
    version: str
    puntaje_minimo: int
    lineas_titulo: int
    tipo_por_defecto: str
    tipos: tuple[TipoDocumental, ...]


def _patron(palabra: str) -> re.Pattern:
    """Palabra o frase completa, tolerante a espacios múltiples."""
    partes = [re.escape(p) for p in normalizar(str(palabra)).split()]
    return re.compile(r"\b" + r"\s+".join(partes) + r"\b")


@lru_cache(maxsize=4)
def cargar_tipos(ruta: Path = RUTA_TIPOS) -> CatalogoTipos:
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    tipos = tuple(
        TipoDocumental(
            nombre=t["nombre"],
            titulos=tuple(_patron(p) for p in t.get("titulos", [])),
            fuertes=tuple(_patron(p) for p in t.get("fuertes", [])),
            apoyo=tuple(_patron(p) for p in t.get("apoyo", [])),
        )
        for t in datos["tipos"]
    )
    return CatalogoTipos(
        version=str(datos.get("version", "")),
        puntaje_minimo=int(datos.get("puntaje_minimo", 3)),
        lineas_titulo=int(datos.get("lineas_titulo", 30)),
        tipo_por_defecto=datos.get("tipo_por_defecto", "Otros"),
        tipos=tipos,
    )


def tipo_por_titulo(texto: str) -> str | None:
    """Tipo según el primer título reconocido en las primeras líneas, o None."""
    catalogo = cargar_tipos()
    lineas = [normalizar(l) for l in (texto or "").splitlines() if l.strip()][: catalogo.lineas_titulo]
    for linea in lineas:
        # Un título está al inicio de la línea o en una línea corta (no dentro de un párrafo).
        corta = len(linea.split()) <= MAXIMO_PALABRAS_TITULO
        mejor, posicion = None, len(linea) + 1
        for tipo in catalogo.tipos:
            for patron in tipo.titulos:
                m = patron.search(linea)
                if m and (m.start() == 0 or corta) and m.start() < posicion:
                    mejor, posicion = tipo.nombre, m.start()
        if mejor:
            return mejor
    return None


def tipo_por_palabras(texto: str) -> str:
    catalogo = cargar_tipos()
    normalizado = normalizar(texto)
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


def clasificar_texto(texto: str, tipo_anterior: str | None = None) -> str | None:
    """Tipo documental de un folio. Sin texto devuelve None."""
    if not normalizar(texto):
        return None
    return tipo_por_titulo(texto) or tipo_anterior or tipo_por_palabras(texto)
