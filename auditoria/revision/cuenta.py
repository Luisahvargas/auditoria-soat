"""Lectura de una cuenta: folios con su tipo documental y los datos encontrados en cada uno.

Todo se hace en memoria; no se guarda ninguna copia de los documentos.
El texto de los documentos es contenido no confiable: solo se buscan patrones.
"""

import re
from dataclasses import dataclass, field

from auditoria.config import Configuracion
from auditoria.documentos import clasificador, lector_pdf, ocr
from auditoria.extraccion.extractor import cargar_definicion, extraer_de_texto, normalizar_valor
from auditoria.revision import formularios
from auditoria.texto import quitar_tildes

# Un folio con menos caracteres visibles que esto se considera sin texto útil (escaneado).
MINIMO_CARACTERES_TEXTO = 40


@dataclass
class Folio:
    archivo: str
    numero: int  # Folio = página del archivo PDF, desde 1
    texto: str
    tipo: str | None
    metodo: str  # "Texto PDF", "OCR" o "Sin texto"

    @property
    def sin_texto(self) -> bool:
        return self.tipo is None

    @property
    def texto_normalizado(self) -> str:
        """Minúsculas y sin tildes (para buscar palabras)."""
        return quitar_tildes(self.texto).lower()


@dataclass
class Dato:
    campo: str
    valor: str
    normalizado: str
    folio: Folio
    evidencia: str


@dataclass
class Cuenta:
    folios: list[Folio] = field(default_factory=list)
    datos: list[Dato] = field(default_factory=list)
    errores_lectura: list[str] = field(default_factory=list)
    mensaje_ocr: str = ""
    etiquetas: dict[str, str] = field(default_factory=dict)  # Nombre corto de cada archivo (p. ej. "FEV")

    @property
    def archivos(self) -> list[str]:
        return list(dict.fromkeys(f.archivo for f in self.folios))

    @property
    def varios_archivos(self) -> bool:
        return len({f.archivo for f in self.folios}) > 1

    def ubicacion(self, folio: Folio) -> str:
        """'folio 3', 'cuenta.pdf folio 3' si hay varios archivos, o 'FEV folio 3' si el archivo tiene etiqueta."""
        if folio.archivo in self.etiquetas:
            return f"{self.etiquetas[folio.archivo]} folio {folio.numero}"
        return f"{folio.archivo} folio {folio.numero}" if self.varios_archivos else f"folio {folio.numero}"

    def folios_de(self, tipos) -> list[Folio]:
        return [f for f in self.folios if f.tipo in tipos]

    def datos_de(self, campo: str, tipos=None) -> list[Dato]:
        return [d for d in self.datos if d.campo == campo and (tipos is None or d.folio.tipo in tipos)]

    def folios_sin_texto(self) -> list[Folio]:
        return [f for f in self.folios if f.sin_texto]


def _contar_caracteres(texto: str) -> int:
    return len(re.sub(r"\s", "", texto or ""))


def leer_cuenta(
    archivos: list[tuple[str, bytes]],
    config: Configuracion,
    tipos_por_archivo: dict[str, str | None] | None = None,
    etiquetas: dict[str, str] | None = None,
) -> Cuenta:
    """Lee los PDF de la cuenta (nombre, contenido), clasifica cada folio y extrae sus datos.

    tipos_por_archivo: tipo sugerido por el nombre del archivo; se usa si el primer folio no trae título.
    """
    cuenta = Cuenta(etiquetas=dict(etiquetas or {}))
    tipos_por_archivo = tipos_por_archivo or {}
    estado = ocr.estado_ocr(config)
    cuenta.mensaje_ocr = estado.mensaje
    definicion = cargar_definicion()

    for nombre, contenido in archivos:
        try:
            paginas = list(lector_pdf.leer_paginas(contenido))
        except lector_pdf.ErrorLecturaPDF as error:
            cuenta.errores_lectura.append(f"{nombre}: {error}")
            continue
        tipo_anterior = tipos_por_archivo.get(nombre)
        for pagina in paginas:
            texto, metodo = pagina.texto, "Texto PDF"
            if _contar_caracteres(texto) < MINIMO_CARACTERES_TEXTO:
                texto, metodo = "", "Sin texto"
                if estado.disponible:
                    try:
                        reconocido = ocr.ocr_imagen(estado, lector_pdf.renderizar_pagina(contenido, pagina.numero))
                    except (RuntimeError, OSError, lector_pdf.ErrorLecturaPDF):
                        reconocido = ""
                    if _contar_caracteres(reconocido) >= MINIMO_CARACTERES_TEXTO:
                        texto, metodo = reconocido, "OCR"
            tipo = clasificador.clasificar_texto(texto, tipo_anterior) if texto else None
            tipo_anterior = tipo or tipo_anterior
            folio = Folio(nombre, pagina.numero, texto, tipo, metodo)
            cuenta.folios.append(folio)
            for campo, valor, evidencia in _datos_del_folio(folio, definicion):
                cuenta.datos.append(Dato(campo, valor, normalizar_valor(definicion.campo(campo).tipo, valor), folio, evidencia))
    return cuenta


def _datos_del_folio(folio: Folio, definicion) -> list[tuple[str, str, str]]:
    """Datos de un folio: lector propio del formulario y/o patrones generales."""
    if not folio.texto:
        return []
    lector = formularios.LECTORES.get(folio.tipo)
    propios = lector(folio.texto) if lector else []
    if propios and folio.tipo in ("FURIPS", "SIRAS"):
        return propios  # Formularios oficiales: solo su lector (las etiquetas se repiten por sección)
    generales = [(c.campo_id, c.valor, c.evidencia) for c in extraer_de_texto(folio.texto, definicion)]
    if folio.tipo in formularios.SIN_DATOS_GENERALES_DEL_PACIENTE:
        generales = [g for g in generales if not g[0].startswith("paciente.")]
    ya = {(c, normalizar_valor(definicion.campo(c).tipo, v)) for c, v, _ in propios}
    return propios + [g for g in generales if (g[0], normalizar_valor(definicion.campo(g[0]).tipo, g[1])) not in ya]
