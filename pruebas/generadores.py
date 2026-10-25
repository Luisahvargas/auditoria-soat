"""Generadores de documentos FICTICIOS para las pruebas.

Todo lo que se genera aquí es inventado y lleva la marca "DOCUMENTO FICTICIO DE PRUEBA".
"""

import io

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

MARCA = "DOCUMENTO FICTICIO DE PRUEBA"
SOLO_IMAGEN = "<<solo-imagen>>"  # Página con dibujos pero sin texto (simula un escaneo)


def pdf_con_paginas(paginas: list[str | None]) -> bytes:
    """Crea un PDF: cada elemento es el texto de una página.

    None = página en blanco; SOLO_IMAGEN = página con figuras y sin texto.
    """
    salida = io.BytesIO()
    lienzo = canvas.Canvas(salida, pagesize=letter)
    _, alto = letter
    for contenido in paginas:
        if contenido == SOLO_IMAGEN:
            lienzo.setFillGray(0.5)
            for i in range(8):
                lienzo.rect(60 + i * 50, 300 + (i % 3) * 40, 40, 120, fill=1, stroke=0)
        elif contenido:
            texto = lienzo.beginText(50, alto - 50)
            texto.setFont("Helvetica", 10)
            texto.textLine(MARCA)
            for linea in contenido.splitlines():
                texto.textLine(linea)
            lienzo.drawText(texto)
        lienzo.showPage()
    lienzo.save()
    return salida.getvalue()


def pdf_con_texto() -> bytes:
    return pdf_con_paginas(
        [
            "HISTORIA CLINICA\nPaciente: Paciente Ficticio Uno\nMotivo de consulta: dolor ficticio en rodilla derecha\nPagina 1 de 2",
            "EVOLUCION\nNota de evolucion del paciente ficticio, sin cambios relevantes.\nPagina 2 de 2",
        ]
    )


def pdf_con_pagina_en_blanco_e_imagen() -> bytes:
    return pdf_con_paginas(
        [
            "EPICRISIS\nResumen de egreso del paciente ficticio con texto suficiente para leerse.",
            None,
            SOLO_IMAGEN,
        ]
    )


def pdf_concatenado() -> bytes:
    """Varios documentos distintos dentro de un mismo PDF."""
    return pdf_con_paginas(
        [
            "FORMULARIO UNICO DE RECLAMACION FURIPS\nDatos del accidente ficticio\nFecha del accidente: 10/01/2025",
            "FACTURA ELECTRONICA DE VENTA No. FE-0001\nValor total ficticio: 100000",
            "INFORME RADIOLOGICO\nRadiografia de rodilla derecha: sin hallazgos ficticios.",
            "EPICRISIS\nResumen de egreso ficticio. Fecha de egreso: 12/01/2025",
        ]
    )
