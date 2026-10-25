"""Puente manual con IA (sin costo): exporta el prompt y valida/importa la respuesta JSON.

Flujo:
1. La app genera un paquete: prompt exacto + esquema JSON + archivos y páginas a subir.
2. El usuario sube los PDF y el prompt a claude.ai y copia la respuesta JSON.
3. La app valida el JSON contra el esquema y contra los archivos de la auditoría.
4. Si hay cualquier error, se muestran todos y NO se importa nada.
5. Lo importado queda como "Sugerencia de IA – pendiente de revisión humana".

La API (cuando se active) usa exactamente los mismos prompts, esquema e importación.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from auditoria import catalogos
from auditoria.auditorias.servicio import obtener_auditoria, verificar_abierta
from auditoria.db.modelos import Documento, Hallazgo
from auditoria.db.repositorios import RepositorioDocumentos, RepositorioHallazgos, RepositorioTrazabilidad
from auditoria.documentos.inventario import _rangos
from auditoria.ia.esquemas import VERSION_ESQUEMA, RespuestaIA, esquema_json

RUTA_PROMPTS = Path(__file__).parent / "prompts"

PLANTILLAS = {
    "analisis_clinico": ("Análisis clínico", "analisis_clinico_v1.md"),
    "clasificacion_paginas": ("Clasificar páginas", "clasificar_paginas_v1.md"),
    "extraccion_ficha": ("Extraer datos de páginas escaneadas", "extraer_ficha_v1.md"),
}
PLANTILLA_COMUN = "comun_v1.md"


class ErrorImportacionIA(ValueError):
    """La respuesta no se importó. `errores` contiene todos los problemas encontrados."""

    def __init__(self, errores: list[str]):
        super().__init__("; ".join(errores))
        self.errores = errores


@dataclass
class ArchivoPaquete:
    nombre: str
    documento_id: int
    paginas: str  # p. ej. "1-3, 7" o "todas (1-12)"
    motivo: str


@dataclass
class PaqueteIA:
    tipo: str
    nombre_tipo: str
    version_prompt: str
    prompt: str
    esquema: str
    archivos: list[ArchivoPaquete] = field(default_factory=list)

    @property
    def texto_completo(self) -> str:
        """Lo que se pega en claude.ai: prompt + esquema."""
        return f"{self.prompt}\n\nESQUEMA JSON OBLIGATORIO\n{self.esquema}\n"


def _leer_plantilla(nombre: str) -> str:
    return (RUTA_PROMPTS / nombre).read_text(encoding="utf-8").strip()


def _paginas_del_paquete(tipo: str, documento: Documento) -> tuple[list[int], str]:
    """Qué páginas se piden según el tipo de análisis."""
    if tipo == "extraccion_ficha":
        return [p.numero for p in documento.paginas if p.requiere_analisis_visual], "páginas sin texto"
    if tipo == "clasificacion_paginas":
        paginas = [
            p.numero
            for p in documento.paginas
            if not p.tipo_confirmado and (p.requiere_analisis_visual or p.confianza_clasificacion == "baja")
        ]
        return paginas, "sin texto o con clasificación de confianza baja, sin confirmar"
    return [p.numero for p in documento.paginas], "documento completo"


def generar_paquete(sesion: Session, auditoria_id: int, tipo: str) -> PaqueteIA:
    """Arma el prompt exacto y la lista de archivos/páginas. No envía nada a ningún lado."""
    if tipo not in PLANTILLAS:
        raise ValueError(f"Tipo de análisis desconocido: {tipo}")
    auditoria = obtener_auditoria(sesion, auditoria_id)
    nombre_tipo, archivo_plantilla = PLANTILLAS[tipo]

    archivos = []
    for documento in RepositorioDocumentos(sesion).listar_por_auditoria(auditoria_id, con_paginas=True):
        if documento.tipo_archivo != "pdf" or not documento.paginas:
            continue
        paginas, motivo = _paginas_del_paquete(tipo, documento)
        if not paginas:
            continue
        texto_paginas = f"todas (1-{documento.numero_paginas})" if len(paginas) == documento.numero_paginas else _rangos(paginas)
        archivos.append(ArchivoPaquete(documento.nombre_original, documento.id, texto_paginas, motivo))

    lista = "\n".join(f"- «{a.nombre}»: páginas del archivo {a.paginas}" for a in archivos) or "- (ninguno)"
    prompt = (
        _leer_plantilla(PLANTILLA_COMUN)
        + "\n\n"
        + _leer_plantilla(archivo_plantilla)
        + "\n\nARCHIVOS ADJUNTOS Y PÁGINAS A ANALIZAR\n"
        + lista
    )
    for marcador, valor in (
        ("{{VERSION_ESQUEMA}}", VERSION_ESQUEMA),
        ("{{TIPO_ANALISIS}}", tipo),
        ("{{AUDITORIA}}", auditoria.identificador),
    ):
        prompt = prompt.replace(marcador, valor)

    return PaqueteIA(
        tipo=tipo,
        nombre_tipo=nombre_tipo,
        version_prompt=Path(archivo_plantilla).stem,
        prompt=prompt,
        esquema=json.dumps(esquema_json(), ensure_ascii=False, indent=2),
        archivos=archivos,
    )


def _limpiar_texto_json(texto: str) -> str:
    """Quita los bloques ```json ... ``` que suelen venir al copiar desde el chat."""
    texto = (texto or "").strip()
    bloque = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", texto, re.DOTALL)
    return bloque.group(1) if bloque else texto


def validar_respuesta(
    sesion: Session, auditoria_id: int, texto: str, tipo_esperado: str | None = None
) -> RespuestaIA:
    """Valida sintaxis, esquema y referencias a archivos/páginas. Lanza ErrorImportacionIA con TODOS los errores."""
    limpio = _limpiar_texto_json(texto)
    if not limpio:
        raise ErrorImportacionIA(["La respuesta está vacía."])
    try:
        datos = json.loads(limpio)
    except json.JSONDecodeError as error:
        raise ErrorImportacionIA([f"JSON inválido: {error.msg} (línea {error.lineno}, columna {error.colno})."]) from error

    try:
        respuesta = RespuestaIA.model_validate(datos)
    except ValidationError as error:
        errores = [
            f"{'.'.join(str(p) for p in e['loc']) or '(raíz)'}: {e['msg']}" for e in error.errors(include_url=False)
        ]
        raise ErrorImportacionIA(errores) from error

    errores = []
    auditoria = obtener_auditoria(sesion, auditoria_id)
    if respuesta.auditoria != auditoria.identificador:
        errores.append(
            f"auditoria: la respuesta es de «{respuesta.auditoria}», pero la auditoría activa es «{auditoria.identificador}»."
        )
    if tipo_esperado and respuesta.tipo_analisis != tipo_esperado:
        errores.append(f"tipo_analisis: se esperaba «{tipo_esperado}» y llegó «{respuesta.tipo_analisis}».")

    documentos = {d.nombre_original: d for d in RepositorioDocumentos(sesion).listar_por_auditoria(auditoria_id)}
    for i, analisis in enumerate(respuesta.analisis):
        for j, evidencia in enumerate(analisis.evidencias):
            ubicacion = f"analisis.{i}.evidencias.{j}"
            documento = documentos.get(evidencia.archivo)
            if documento is None:
                errores.append(f"{ubicacion}.archivo: «{evidencia.archivo}» no está cargado en esta auditoría.")
            elif not documento.numero_paginas or evidencia.pagina > documento.numero_paginas:
                errores.append(
                    f"{ubicacion}.pagina: la página {evidencia.pagina} no existe en «{evidencia.archivo}» "
                    f"({documento.numero_paginas or 0} páginas)."
                )
    if errores:
        raise ErrorImportacionIA(errores)
    return respuesta


def importar_respuesta(
    sesion: Session,
    auditoria_id: int,
    usuario_id: int,
    texto: str,
    tipo_esperado: str | None = None,
    medio: str = "puente manual",
) -> list[Hallazgo]:
    """Valida y registra la respuesta como sugerencias de IA pendientes de revisión. No hace commit.

    Si hay cualquier error no se agrega nada (importación todo o nada).
    """
    verificar_abierta(obtener_auditoria(sesion, auditoria_id))
    respuesta = validar_respuesta(sesion, auditoria_id, texto, tipo_esperado)
    documentos = {d.nombre_original: d for d in RepositorioDocumentos(sesion).listar_por_auditoria(auditoria_id)}
    nombre_tipo = PLANTILLAS[respuesta.tipo_analisis][0]

    repositorio = RepositorioHallazgos(sesion)
    creados = []
    for analisis in respuesta.analisis:
        evidencias = [
            {
                "archivo": e.archivo,
                "documento_id": documentos[e.archivo].id,
                "pagina": e.pagina,
                "texto": e.texto,
            }
            for e in analisis.evidencias
        ]
        creados.append(
            repositorio.agregar(
                Hallazgo(
                    auditoria_id=auditoria_id,
                    origen=catalogos.ORIGEN_IA,
                    titulo=f"{analisis.pregunta_clinica}"[:255],
                    categoria=f"IA – {nombre_tipo}",
                    severidad=analisis.severidad,
                    estado_resultado=analisis.estado_resultado,
                    explicacion=f"{analisis.conclusion_preliminar}\n\nAcción sugerida para el auditor: {analisis.accion_sugerida}",
                    referencia_normativa=catalogos.PENDIENTE_VALIDACION,
                    evidencias_json=json.dumps(evidencias, ensure_ascii=False),
                    detalle_ia_json=json.dumps(
                        {**analisis.model_dump(), "tipo_analisis": respuesta.tipo_analisis, "medio": medio},
                        ensure_ascii=False,
                    ),
                    estado_revision=catalogos.REVISION_PENDIENTE,
                    usuario_creacion_id=usuario_id,
                )
            )
        )
    RepositorioTrazabilidad(sesion).registrar(
        usuario_id, "ia_importada", f"tipo={respuesta.tipo_analisis}; medio={medio}; elementos={len(creados)}", auditoria_id
    )
    return creados
