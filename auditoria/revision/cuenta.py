"""Lectura de una cuenta: folios con su tipo documental y los datos encontrados en cada uno.

Todo se hace en memoria; no se guarda ninguna copia de los documentos.
El texto de los documentos es contenido no confiable: solo se buscan patrones.
"""

import re
from dataclasses import dataclass, field

from auditoria.config import Configuracion
from auditoria.documentos import clasificador, lector_pdf, ocr
from auditoria.extraccion.extractor import cargar_definicion, extraer_de_texto, normalizar_valor
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

    @property
    def varios_archivos(self) -> bool:
        return len({f.archivo for f in self.folios}) > 1

    def ubicacion(self, folio: Folio) -> str:
        """'folio 3' o 'cuenta.pdf folio 3' si hay varios archivos."""
        return f"{folio.archivo} folio {folio.numero}" if self.varios_archivos else f"folio {folio.numero}"

    def folios_de(self, tipos) -> list[Folio]:
        return [f for f in self.folios if f.tipo in tipos]

    def datos_de(self, campo: str, tipos=None) -> list[Dato]:
        return [d for d in self.datos if d.campo == campo and (tipos is None or d.folio.tipo in tipos)]

    def folios_sin_texto(self) -> list[Folio]:
        return [f for f in self.folios if f.sin_texto]


def _contar_caracteres(texto: str) -> int:
    return len(re.sub(r"\s", "", texto or ""))


def leer_cuenta(archivos: list[tuple[str, bytes]], config: Configuracion) -> Cuenta:
    """Lee los PDF de la cuenta (nombre, contenido), clasifica cada folio y extrae sus datos."""
    cuenta = Cuenta()
    estado = ocr.estado_ocr(config)
    cuenta.mensaje_ocr = estado.mensaje
    definicion = cargar_definicion()

    for nombre, contenido in archivos:
        try:
            paginas = list(lector_pdf.leer_paginas(contenido))
        except lector_pdf.ErrorLecturaPDF as error:
            cuenta.errores_lectura.append(f"{nombre}: {error}")
            continue
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
            folio = Folio(nombre, pagina.numero, texto, clasificador.clasificar_texto(texto) if texto else None, metodo)
            cuenta.folios.append(folio)
            for coincidencia in extraer_de_texto(texto, definicion):
                tipo_campo = definicion.campo(coincidencia.campo_id).tipo
                cuenta.datos.append(
                    Dato(
                        coincidencia.campo_id,
                        coincidencia.valor,
                        normalizar_valor(tipo_campo, coincidencia.valor),
                        folio,
                        coincidencia.evidencia,
                    )
                )
    return cuenta
