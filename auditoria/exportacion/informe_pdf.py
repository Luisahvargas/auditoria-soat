"""Informe PDF de auditoría (ReportLab).

Diferencia siempre: resultado de regla automática, sugerencia de IA y conclusión del auditor.
No redacta glosas ni marca la cuenta como rechazada.
"""

import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from auditoria import catalogos
from auditoria.exportacion.excel import AVISO
from auditoria.exportacion.resumen import FilaHallazgo, ResumenAuditoria

ESTILOS = getSampleStyleSheet()
NORMAL = ParagraphStyle("normal_es", parent=ESTILOS["BodyText"], fontSize=9, leading=12)
PEQUENO = ParagraphStyle("pequeno_es", parent=NORMAL, fontSize=8, leading=10)
TITULO = ParagraphStyle("titulo_es", parent=ESTILOS["Title"], fontSize=16)
SUBTITULO = ParagraphStyle("subtitulo_es", parent=ESTILOS["Heading2"], fontSize=12, spaceBefore=10)
SECCION = ParagraphStyle("seccion_es", parent=ESTILOS["Heading3"], fontSize=10, spaceBefore=8)
ENCABEZADO_TABLA = ParagraphStyle("encabezado_es", parent=PEQUENO, textColor=colors.white)
AVISO_ESTILO =ParagraphStyle("aviso_es", parent=NORMAL, textColor=colors.HexColor("#7A4B00"), alignment=TA_CENTER)


def _p(texto, estilo=NORMAL) -> Paragraph:
    """Párrafo con el texto escapado (el contenido de los documentos nunca se interpreta)."""
    return Paragraph(escape(str(texto or "")).replace("\n", "<br/>"), estilo)


def _tabla(filas: list[list], anchos: list[float]) -> Table:
    """Tabla con la primera fila como encabezado (texto blanco en negrita)."""
    encabezado = [Paragraph(f"<b>{escape(str(c))}</b>", ENCABEZADO_TABLA) for c in filas[0]]
    cuerpo = [[_p(c, PEQUENO) for c in fila] for fila in filas[1:]]
    tabla = Table([encabezado, *cuerpo], colWidths=anchos, repeatRows=1)
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return tabla


def _hallazgo(h: FilaHallazgo) -> list:
    bloque = [
        _p(f"[{h.id}] {h.titulo}", SECCION),
        _p(
            f"Origen: {h.origen}{'  ·  Regla ' + h.regla if h.regla else ''}  ·  Estado: {h.estado_final}"
            f"{' (original: ' + h.estado_resultado + ')' if h.estado_final != h.estado_resultado else ''}  ·  Severidad: {h.severidad}"
        ),
        _p(f"Revisión del auditor: {h.revision}" + (f" — {h.revisor}, {h.fecha_revision:%Y-%m-%d %H:%M}" if h.fecha_revision else "")),
    ]
    if h.comentario:
        bloque.append(_p(f"Comentario del auditor: {h.comentario}"))
    bloque.append(_p(h.explicacion))
    if h.referencia_normativa:
        bloque.append(_p(f"Referencia normativa: {h.referencia_normativa}", PEQUENO))
    if h.evidencias:
        bloque.append(
            _tabla(
                [["Archivo", "Página", "Evidencia"]]
                + [[e.get("archivo"), e.get("pagina") or "-", e.get("texto")] for e in h.evidencias],
                [4.5 * cm, 1.5 * cm, 11.5 * cm],
            )
        )
    return [KeepTogether(bloque[:3]), *bloque[3:], Spacer(1, 6)]


def generar_pdf(resumen: ResumenAuditoria) -> bytes:
    salida = io.BytesIO()
    documento = SimpleDocTemplate(
        salida, pagesize=letter, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
        title=f"Informe de auditoría {resumen.identificador}",
    )
    historia = [_p("Informe de auditoría de cuenta médica SOAT", TITULO), _p(AVISO, AVISO_ESTILO), Spacer(1, 8)]
    if not resumen.finalizada:
        historia.append(_p("BORRADOR: la auditoría no ha sido finalizada por el auditor.", AVISO_ESTILO))

    historia += [
        _p("1. Datos de la auditoría", SUBTITULO),
        _tabla(
            [
                ["Dato", "Valor"],
                ["Auditoría", resumen.identificador],
                ["Descripción", resumen.descripcion],
                ["Estado", resumen.estado],
                ["Perfil de aseguradora", resumen.perfil_aseguradora],
                ["Creada por", f"{resumen.creada_por} — {resumen.fecha_creacion:%Y-%m-%d %H:%M}"],
                ["Finalizada por", f"{resumen.finalizada_por} — {resumen.fecha_finalizacion:%Y-%m-%d %H:%M}" if resumen.fecha_finalizacion else "—"],
                ["Último análisis automático", f"{resumen.ultima_ejecucion} · {resumen.reglas_ejecutadas} reglas"],
                ["Análisis de IA", "Sí: sugerencias revisadas por el auditor" if resumen.hubo_ia else "No se ejecutó análisis de IA"],
                ["Edad a la fecha del accidente", resumen.edad_al_accidente],
                ["Generado", f"{resumen.generado:%Y-%m-%d %H:%M}"],
            ],
            [5 * cm, 12.5 * cm],
        ),
        _p("2. Conclusión del auditor", SUBTITULO),
        _p(resumen.conclusion_auditor or "(Sin conclusión registrada)"),
    ]
    if resumen.observaciones_auditor:
        historia += [_p("Observaciones", SECCION), _p(resumen.observaciones_auditor)]

    historia += [
        _p("3. Resumen de hallazgos que requieren atención", SUBTITULO),
        _tabla(
            [["Origen", "Total", "Pendientes", "Confirmados", "Descartados", "Modificados"]]
            + [
                [
                    origen,
                    resumen.contar(origen),
                    resumen.contar(origen, catalogos.REVISION_PENDIENTE),
                    resumen.contar(origen, catalogos.REVISION_CONFIRMADO),
                    resumen.contar(origen, catalogos.REVISION_DESCARTADO),
                    resumen.contar(origen, catalogos.REVISION_MODIFICADO),
                ]
                for origen in catalogos.ORIGENES
            ],
            [5.5 * cm, 2 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm],
        ),
    ]

    titulos = {
        catalogos.ORIGEN_REGLA: "4. Resultados de reglas automáticas",
        catalogos.ORIGEN_IA: "5. Sugerencias de IA (revisadas por el auditor)",
        catalogos.ORIGEN_AUDITOR: "6. Hallazgos registrados por el auditor",
    }
    for origen, titulo in titulos.items():
        historia.append(_p(titulo, SUBTITULO))
        del_origen = [h for h in resumen.hallazgos_atencion if h.origen == origen]
        if not del_origen:
            historia.append(_p("Ninguno."))
        for h in del_origen:
            historia += _hallazgo(h)

    historia += [
        _p("7. Verificaciones sin hallazgo o no evaluables", SUBTITULO),
        _p(
            "Constancia de lo revisado. «No evaluable» significa que faltó información para aplicar la verificación; "
            "no implica un error."
        ),
        _tabla(
            [["Regla", "Verificación", "Estado"]]
            + [[h.regla, h.titulo, h.estado_final] for h in resumen.hallazgos if not h.requiere_atencion],
            [2.5 * cm, 10.5 * cm, 4.5 * cm],
        ),
        _p("8. Inventario documental", SUBTITULO),
        _tabla(
            [["Archivo", "Tipo", "Estado", "Págs.", "Sin texto", "SHA-256 (inicio)"]]
            + [[d.archivo, d.tipo, d.estado, d.paginas or "-", d.sin_texto, d.hash_sha256[:16]] for d in resumen.documentos],
            [5 * cm, 1.3 * cm, 3.5 * cm, 1.3 * cm, 1.6 * cm, 4.8 * cm],
        ),
        _p("9. Requisitos de cierre", SUBTITULO),
        _tabla(
            [["Requisito", "Cumplido", "Detalle"]]
            + [[r.nombre + ("" if r.obligatorio else " (recomendado)"), "Sí" if r.cumplido else "No", r.detalle] for r in resumen.requisitos],
            [5.5 * cm, 2 * cm, 10 * cm],
        ),
    ]

    def pie(lienzo, doc):
        lienzo.saveState()
        lienzo.setFont("Helvetica", 7)
        lienzo.drawString(2 * cm, 1.2 * cm, f"Auditoría {resumen.identificador} · Documento de apoyo; la decisión es del auditor.")
        lienzo.drawRightString(letter[0] - 2 * cm, 1.2 * cm, f"Página {doc.page}")
        lienzo.restoreState()

    documento.build(historia, onFirstPage=pie, onLaterPages=pie)
    return salida.getvalue()
