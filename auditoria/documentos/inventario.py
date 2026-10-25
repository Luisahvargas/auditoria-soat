"""Inventario documental: carga de archivos a una auditoría y lectura de sus páginas.

Reglas: no modificar originales, no perder la numeración de páginas, tratar el texto
como contenido no confiable y no enviar nada a servicios externos.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from auditoria import catalogos
from auditoria.auditorias.servicio import obtener_auditoria, verificar_abierta
from auditoria.config import Configuracion
from auditoria.db.modelos import Documento, Pagina
from auditoria.db.repositorios import RepositorioDocumentos, RepositorioTrazabilidad
from auditoria.documentos import almacenamiento, lector_pdf

EXTENSIONES_PERMITIDAS = ("pdf", "xml", "json")
TAMANO_MAXIMO_MB = 200

# Una página con menos caracteres visibles que esto se considera sin texto útil.
MINIMO_CARACTERES_TEXTO = 40

PATRON_PAGINA_INTERNA = re.compile(r"p[aá]g(?:ina|\.)?\s*(\d{1,4})\s*(?:de|/)\s*(\d{1,4})", re.IGNORECASE)


@dataclass
class ResultadoCarga:
    nombre: str
    resultado: str  # "Cargado", "Duplicado" o "Rechazado"
    mensaje: str
    documento_id: int | None = None


def cargar_archivo(
    sesion: Session, config: Configuracion, auditoria_id: int, usuario_id: int, nombre: str, contenido: bytes
) -> ResultadoCarga:
    """Copia el archivo, lo registra en el inventario y, si es PDF, extrae el texto de cada página.

    No hace commit: quien llama decide.
    """
    verificar_abierta(obtener_auditoria(sesion, auditoria_id))

    extension = Path(nombre).suffix.lower().lstrip(".")
    if extension not in EXTENSIONES_PERMITIDAS:
        return ResultadoCarga(nombre, "Rechazado", f"Tipo de archivo no permitido. Use: {', '.join(EXTENSIONES_PERMITIDAS)}.")
    if not contenido:
        return ResultadoCarga(nombre, "Rechazado", "El archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO_MB * 1024 * 1024:
        return ResultadoCarga(nombre, "Rechazado", f"El archivo supera {TAMANO_MAXIMO_MB} MB.")

    repositorio = RepositorioDocumentos(sesion)
    hash_archivo = almacenamiento.calcular_sha256(contenido)
    existente = repositorio.obtener_por_hash(auditoria_id, hash_archivo)
    if existente:
        return ResultadoCarga(
            nombre, "Duplicado", f"Es idéntico (mismo hash) a '{existente.nombre_original}', ya cargado.", existente.id
        )

    ruta_relativa = almacenamiento.guardar_original(config.ruta_datos, auditoria_id, contenido, extension)
    documento = repositorio.agregar(
        Documento(
            auditoria_id=auditoria_id,
            nombre_original=Path(nombre).name,
            tipo_archivo=extension,
            ruta_relativa=ruta_relativa,
            hash_sha256=hash_archivo,
            tamano_bytes=len(contenido),
            estado=catalogos.PROC_EN_CURSO,
            usuario_carga_id=usuario_id,
        )
    )

    if extension == "pdf":
        procesar_pdf(sesion, config, documento)
    else:
        # Fase 5 pendiente: la estructura del XML y de los RIPS no se inventa.
        documento.estado = catalogos.PROC_PENDIENTE
        documento.mensaje = (
            "Archivo guardado. Su lectura automática está pendiente: el lector de XML/RIPS "
            "se construirá con ejemplos reales anonimizados (Fase 5)."
        )

    # El detalle no incluye el nombre del archivo: podría contener datos personales.
    RepositorioTrazabilidad(sesion).registrar(
        usuario_id, "documento_cargado", f"documento_id={documento.id}; tipo={extension}", auditoria_id
    )
    return ResultadoCarga(nombre, "Cargado", documento.mensaje or documento.estado, documento.id)


def procesar_pdf(sesion: Session, config: Configuracion, documento: Documento) -> None:
    """Extrae el texto de cada página y marca las que requieren OCR o análisis visual."""
    ruta = almacenamiento.ruta_absoluta(config.ruta_datos, documento.ruta_relativa)
    documento.paginas.clear()
    sesion.flush()
    try:
        for leida in lector_pdf.leer_paginas(ruta):
            documento.paginas.append(_crear_pagina(leida.numero, leida.texto))
    except lector_pdf.ErrorLecturaPDF as error:
        documento.paginas.clear()
        documento.numero_paginas = None
        documento.estado = catalogos.PROC_ERROR
        documento.mensaje = str(error)
        sesion.flush()
        return

    documento.numero_paginas = len(documento.paginas)
    sesion.flush()

    # Fase 6: OCR opcional y clasificación preliminar (si los módulos están disponibles).
    from auditoria.documentos import clasificador, ocr

    ocr.aplicar_ocr_documento(config, documento)
    clasificador.clasificar_documento(documento)

    sin_texto = [p.numero for p in documento.paginas if p.requiere_analisis_visual]
    if documento.numero_paginas == 0:
        documento.estado = catalogos.PROC_ERROR
        documento.mensaje = "El PDF no tiene páginas."
    elif sin_texto:
        documento.estado = catalogos.PROC_REQUIERE_REVISION
        documento.mensaje = (
            f"{len(sin_texto)} de {documento.numero_paginas} páginas sin texto suficiente "
            f"(requieren OCR o análisis visual): {_rangos(sin_texto)}."
        )
    else:
        documento.estado = catalogos.PROC_PROCESADO
        documento.mensaje = f"{documento.numero_paginas} páginas con texto."
    sesion.flush()


def _crear_pagina(numero: int, texto: str) -> Pagina:
    caracteres = contar_caracteres(texto)
    interna = PATRON_PAGINA_INTERNA.search(texto)
    return Pagina(
        numero=numero,
        texto=texto,
        caracteres=caracteres,
        metodo_texto="Texto PDF",
        requiere_analisis_visual=caracteres < MINIMO_CARACTERES_TEXTO,
        pagina_interna=f"{interna.group(1)} de {interna.group(2)}" if interna else None,
    )


def contar_caracteres(texto: str) -> int:
    """Caracteres visibles (sin espacios ni saltos de línea)."""
    return len(re.sub(r"\s", "", texto or ""))


def _rangos(numeros: list[int]) -> str:
    """[1,2,3,7] -> '1-3, 7'"""
    partes, inicio = [], None
    for i, n in enumerate(numeros):
        if inicio is None:
            inicio = n
        if i + 1 == len(numeros) or numeros[i + 1] != n + 1:
            partes.append(str(inicio) if inicio == n else f"{inicio}-{n}")
            inicio = None
    return ", ".join(partes)


def listar_documentos(sesion: Session, auditoria_id: int, con_paginas: bool = False) -> list[Documento]:
    return RepositorioDocumentos(sesion).listar_por_auditoria(auditoria_id, con_paginas)


def obtener_imagen_pagina(config: Configuracion, documento: Documento, numero: int, ancho_px: int = 900) -> bytes:
    """Imagen de una página. Se genera solo cuando se pide y se guarda en disco para reusarla."""
    ruta_imagen = almacenamiento.ruta_miniatura(config.ruta_datos, documento.hash_sha256, numero, ancho_px)
    if ruta_imagen.exists():
        return ruta_imagen.read_bytes()
    imagen = lector_pdf.renderizar_pagina(
        almacenamiento.ruta_absoluta(config.ruta_datos, documento.ruta_relativa), numero, ancho_px
    )
    ruta_imagen.parent.mkdir(parents=True, exist_ok=True)
    ruta_imagen.write_bytes(imagen)
    return imagen
