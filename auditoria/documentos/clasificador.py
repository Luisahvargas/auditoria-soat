"""Clasificación preliminar de páginas por palabras clave (configuracion/tipos_documento.yaml).

La clasificación automática es solo una PROPUESTA: nunca se confirma sola. El auditor
puede corregirla y queda registrado quién y cuándo.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from auditoria import catalogos
from auditoria.auditorias.servicio import obtener_auditoria, verificar_abierta
from auditoria.config import RAIZ_PROYECTO
from auditoria.db.modelos import Documento, Pagina, ahora
from auditoria.db.repositorios import RepositorioDocumentos, RepositorioTrazabilidad
from auditoria.texto import normalizar

RUTA_TIPOS = RAIZ_PROYECTO / "configuracion" / "tipos_documento.yaml"
PESO_FUERTE = 3
PESO_APOYO = 1


class ErrorClasificacion(ValueError):
    """Tipo documental inválido o página inexistente."""


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

    @property
    def nombres(self) -> list[str]:
        return [t.nombre for t in self.tipos] + [self.tipo_por_defecto]


@dataclass
class Seccion:
    """Grupo de páginas consecutivas de un mismo tipo dentro de un archivo."""

    tipo: str
    pagina_inicio: int
    pagina_fin: int
    paginas: list[int] = field(default_factory=list)
    dudosa: bool = False
    motivos: list[str] = field(default_factory=list)


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


def clasificar_texto(texto: str, catalogo: CatalogoTipos | None = None) -> tuple[str | None, str | None, dict[str, int]]:
    """Propone (tipo, confianza, puntajes). Sin texto devuelve (None, None, {})."""
    catalogo = catalogo or cargar_tipos()
    normalizado = normalizar(texto)
    if not normalizado:
        return None, None, {}

    puntajes = {}
    for tipo in catalogo.tipos:
        puntos = sum(PESO_FUERTE for p in tipo.fuertes if p.search(normalizado))
        puntos += sum(PESO_APOYO for p in tipo.apoyo if p.search(normalizado))
        if puntos:
            puntajes[tipo.nombre] = puntos

    ordenados = sorted(puntajes.items(), key=lambda par: par[1], reverse=True)
    if not ordenados or ordenados[0][1] < catalogo.puntaje_minimo:
        return catalogo.tipo_por_defecto, "baja", puntajes

    mejor, puntos = ordenados[0]
    segundo = ordenados[1][1] if len(ordenados) > 1 else 0
    if puntos >= 6 and puntos - segundo >= 3:
        confianza = "alta"
    elif puntos - segundo >= 2:
        confianza = "media"
    else:
        confianza = "baja"
    return mejor, confianza, puntajes


def clasificar_documento(documento: Documento) -> None:
    """Propone el tipo de cada página que el auditor no haya clasificado aún."""
    catalogo = cargar_tipos()
    for pagina in documento.paginas:
        if pagina.tipo_confirmado:
            continue
        if pagina.requiere_analisis_visual:
            pagina.tipo_propuesto, pagina.confianza_clasificacion = None, None
            continue
        pagina.tipo_propuesto, pagina.confianza_clasificacion, _ = clasificar_texto(pagina.texto, catalogo)


def confirmar_clasificacion(sesion: Session, pagina_id: int, tipo: str, usuario_id: int) -> Pagina:
    """El auditor confirma o corrige el tipo de una página. No hace commit."""
    pagina = _pagina_editable(sesion, pagina_id)
    if tipo not in cargar_tipos().nombres:
        raise ErrorClasificacion(f"Tipo documental desconocido: {tipo}")
    anterior = pagina.tipo_efectivo
    pagina.tipo_confirmado = tipo
    pagina.usuario_clasificacion_id = usuario_id
    pagina.fecha_clasificacion = ahora()
    RepositorioTrazabilidad(sesion).registrar(
        usuario_id,
        "clasificacion_corregida" if anterior != tipo else "clasificacion_confirmada",
        f"pagina_id={pagina.id}; anterior={anterior}; nuevo={tipo}",
        pagina.documento.auditoria_id,
    )
    return pagina


def confirmar_seccion(sesion: Session, documento_id: int, paginas: list[int], tipo: str, usuario_id: int) -> None:
    """Confirma el mismo tipo para varias páginas de un archivo. No hace commit."""
    repositorio = RepositorioDocumentos(sesion)
    for numero in paginas:
        pagina = repositorio.obtener_pagina_por_numero(documento_id, numero)
        if pagina is None:
            raise ErrorClasificacion(f"La página {numero} no existe.")
        confirmar_clasificacion(sesion, pagina.id, tipo, usuario_id)


def marcar_legibilidad(sesion: Session, pagina_id: int, legibilidad: str, usuario_id: int) -> Pagina:
    """El auditor indica si una página es legible o ilegible. No hace commit."""
    if legibilidad not in (catalogos.LEGIBLE, catalogos.NO_LEGIBLE, catalogos.LEGIBILIDAD_SIN_EVALUAR):
        raise ErrorClasificacion(f"Valor de legibilidad inválido: {legibilidad}")
    pagina = _pagina_editable(sesion, pagina_id)
    pagina.legibilidad = legibilidad
    RepositorioTrazabilidad(sesion).registrar(
        usuario_id, "legibilidad_marcada", f"pagina_id={pagina.id}; valor={legibilidad}", pagina.documento.auditoria_id
    )
    return pagina


def _pagina_editable(sesion: Session, pagina_id: int) -> Pagina:
    pagina = RepositorioDocumentos(sesion).obtener_pagina(pagina_id)
    if pagina is None:
        raise ErrorClasificacion("La página no existe.")
    verificar_abierta(obtener_auditoria(sesion, pagina.documento.auditoria_id))
    return pagina


def agrupar_secciones(paginas: list[Pagina]) -> list[Seccion]:
    """Agrupa páginas consecutivas de un mismo archivo con el mismo tipo.

    Una sección se marca como dudosa si empieza o termina en una página con
    clasificación automática de confianza baja, o si limita con una página sin texto.
    """
    secciones: list[Seccion] = []
    for pagina in sorted(paginas, key=lambda p: p.numero):
        tipo = pagina.tipo_efectivo or "Sin clasificar (sin texto)"
        if secciones and secciones[-1].tipo == tipo and secciones[-1].pagina_fin == pagina.numero - 1:
            secciones[-1].pagina_fin = pagina.numero
            secciones[-1].paginas.append(pagina.numero)
        else:
            secciones.append(Seccion(tipo, pagina.numero, pagina.numero, [pagina.numero]))

    por_numero = {p.numero: p for p in paginas}
    for indice, seccion in enumerate(secciones):
        for extremo in {seccion.pagina_inicio, seccion.pagina_fin}:
            pagina = por_numero[extremo]
            if not pagina.tipo_confirmado and pagina.confianza_clasificacion == "baja":
                seccion.motivos.append(f"La página {extremo} tiene clasificación de confianza baja.")
        vecinas = [secciones[i] for i in (indice - 1, indice + 1) if 0 <= i < len(secciones)]
        if seccion.tipo != "Sin clasificar (sin texto)" and any(v.tipo == "Sin clasificar (sin texto)" for v in vecinas):
            seccion.motivos.append("Limita con páginas sin texto: el inicio o el final de la sección es incierto.")
        if seccion.tipo == "Sin clasificar (sin texto)":
            seccion.motivos.append("Páginas sin texto: requieren OCR o análisis visual para clasificarse.")
        seccion.dudosa = bool(seccion.motivos)
    return secciones


def reclasificar_auditoria(sesion: Session, auditoria_id: int, usuario_id: int) -> int:
    """Vuelve a proponer tipos (p. ej. tras editar el YAML). Respeta lo confirmado por el auditor."""
    verificar_abierta(obtener_auditoria(sesion, auditoria_id))
    cargar_tipos.cache_clear()
    documentos = RepositorioDocumentos(sesion).listar_por_auditoria(auditoria_id, con_paginas=True)
    for documento in documentos:
        clasificar_documento(documento)
    RepositorioTrazabilidad(sesion).registrar(usuario_id, "reclasificacion_automatica", auditoria_id=auditoria_id)
    return sum(len(d.paginas) for d in documentos)
