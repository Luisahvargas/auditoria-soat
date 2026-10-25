"""Contexto de una auditoría para las reglas: documentos, páginas y ficha, ya cargados.

Las reglas trabajan solo con este contexto (no consultan la base de datos), lo que
permite probarlas de forma aislada.
"""

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from auditoria.db.modelos import DatoFicha, Documento, Pagina
from auditoria.db.repositorios import RepositorioDocumentos
from auditoria.extraccion import ficha as servicio_ficha
from auditoria.texto import fragmento, normalizar


@dataclass
class Evidencia:
    archivo: str
    texto: str
    documento_id: int | None = None
    pagina: int | None = None

    def como_dict(self) -> dict:
        return {"archivo": self.archivo, "documento_id": self.documento_id, "pagina": self.pagina, "texto": self.texto}


@dataclass
class Resultado:
    """Lo que devuelve una verificación. El motor lo convierte en Hallazgo."""

    estado: str
    explicacion: str
    evidencias: list[Evidencia] = field(default_factory=list)
    detalle: str = ""  # Complemento del título (p. ej. el campo o la región evaluada)


@dataclass
class ContextoAuditoria:
    auditoria_id: int
    documentos: list[Documento]
    paginas: list[Pagina]
    ficha: dict[str, list[servicio_ficha.EstadoCampo]]

    @classmethod
    def desde_base(cls, sesion: Session, auditoria_id: int) -> "ContextoAuditoria":
        repositorio = RepositorioDocumentos(sesion)
        return cls(
            auditoria_id=auditoria_id,
            documentos=repositorio.listar_por_auditoria(auditoria_id),
            paginas=repositorio.listar_paginas_por_auditoria(auditoria_id),
            ficha=servicio_ficha.construir_ficha(sesion, auditoria_id),
        )

    # ---------- Ficha ----------
    def campo(self, campo_id: str) -> servicio_ficha.EstadoCampo:
        for estados in self.ficha.values():
            for estado in estados:
                if estado.campo.id == campo_id:
                    return estado
        raise KeyError(campo_id)

    def todos_los_campos(self) -> list[servicio_ficha.EstadoCampo]:
        return [e for estados in self.ficha.values() for e in estados]

    def evidencia_dato(self, dato: DatoFicha) -> Evidencia:
        nombre = self.nombre_documento(dato.documento_id) if dato.documento_id else f"(dato {dato.metodo.lower()})"
        texto = dato.evidencia or f"Valor registrado: {dato.valor_efectivo}"
        return Evidencia(nombre, texto, dato.documento_id, dato.numero_pagina)

    # ---------- Documentos y páginas ----------
    def nombre_documento(self, documento_id: int) -> str:
        return next((d.nombre_original for d in self.documentos if d.id == documento_id), "(archivo desconocido)")

    def paginas_con_texto(self) -> list[Pagina]:
        return [p for p in self.paginas if p.texto and not p.requiere_analisis_visual]

    def paginas_de_tipo(self, tipos: list[str] | tuple[str, ...]) -> list[Pagina]:
        return [p for p in self.paginas if p.tipo_efectivo in tipos]

    def evidencia_pagina(self, pagina: Pagina, inicio: int = 0, fin: int = 0, texto: str | None = None) -> Evidencia:
        if texto is None:
            texto = fragmento(pagina.texto, inicio, fin) if fin else " ".join(pagina.texto.split())[:200]
        return Evidencia(pagina.documento.nombre_original, texto, pagina.documento_id, pagina.numero)

    def buscar(self, paginas: list[Pagina], palabras: list[str]) -> list[tuple[Pagina, re.Match]]:
        """Coincidencias de cualquiera de las palabras (sin tildes, palabra completa) en las páginas."""
        patron = re.compile(r"\b(?:" + "|".join(re.escape(normalizar(p)) for p in palabras) + r")\b")
        encontradas = []
        for pagina in paginas:
            texto = normalizar_conservando_longitud(pagina.texto)
            encontradas.extend((pagina, m) for m in patron.finditer(texto))
        return encontradas

    def documentos_estructurados(self) -> list[Documento]:
        return [d for d in self.documentos if d.tipo_archivo in ("xml", "json")]


def normalizar_conservando_longitud(texto: str) -> str:
    """Minúsculas y sin tildes, conservando posiciones para recortar evidencias del original."""
    from auditoria.texto import quitar_tildes

    sin_tildes = quitar_tildes(texto or "").lower()
    return sin_tildes if len(sin_tildes) == len(texto or "") else (texto or "").lower()
