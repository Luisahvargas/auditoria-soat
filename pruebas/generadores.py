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


VALORES_CUENTA = {
    "nombre": "Paciente Ficticio Uno",
    "id_furips": "1.234.567",
    "id_factura": "1234567",
    "id_urgencias": "1234567",
    "nacimiento_furips": "15/05/1990",
    "nacimiento_urgencias": "15/05/1990",
    "edad_urgencias": "34",
    "accidente_furips": "10/01/2025",
    "accidente_epicrisis": "10/01/2025",
    "placa_furips": "ABC123",
    "placa_poliza": "ABC123",
    "poliza_furips": "1234567890",
    "poliza_soporte": "1234567890",
    "factura_furips": "FE-1001",
    "factura": "FE-1001",
    "ingreso": "10/01/2025",
    "egreso": "12/01/2025",
    "lado_urgencias": "derecha",
    "lado_informe": "derecha",
    "lado_cirugia": "derecha",
    "material_cirugia": "placa bloqueada y 6 tornillos",
    "propietario_furips": "9.876.543",
    "propietario_poliza": "9876543",
}


def paginas_cuenta_ficticia(**cambios) -> list[str]:
    """Textos de una cuenta SOAT FICTICIA. Los parámetros permiten introducir discrepancias."""
    v = {**VALORES_CUENTA, **cambios}
    return [
        # 1. FURIPS
        "FORMULARIO UNICO DE RECLAMACION FURIPS\n"
        f"Nombre de la victima: {v['nombre']}\n"
        f"C.C. {v['id_furips']}\n"
        f"Fecha de nacimiento: {v['nacimiento_furips']}\n"
        f"Fecha del accidente: {v['accidente_furips']}\n"
        "Hora del accidente: 14:30\n"
        "Municipio del accidente: Ciudad Ficticia\n"
        "Zona: urbana\n"
        "Condicion de la victima: peaton\n"
        f"Placa: {v['placa_furips']}\n"
        f"Poliza SOAT No. {v['poliza_furips']}\n"
        f"Factura No. {v['factura_furips']}\n"
        "Propietario: Propietario Ficticio\n"
        f"Documento del propietario C.C. {v['propietario_furips']}\n"
        "Conductor: Conductor Ficticio\n"
        "Documento del conductor C.C. 5.555.555",
        # 2. Factura
        f"FACTURA ELECTRONICA DE VENTA No. {v['factura']}\n"
        "Fecha de expedicion: 15/01/2025\n"
        "NIT 900123456-1\n"
        f"Paciente: {v['nombre']}\n"
        f"Identificacion: {v['id_factura']}\n"
        "Servicios ficticios: consulta de urgencias, radiografia, osteosintesis\n"
        "Valor total: 1000000",
        # 3. Urgencias
        "ATENCION INICIAL DE URGENCIAS\n"
        "Triage II\n"
        f"Fecha de ingreso: {v['ingreso']}\n"
        f"Paciente: {v['nombre']}\n"
        f"Identificacion: {v['id_urgencias']}\n"
        f"Fecha de nacimiento: {v['nacimiento_urgencias']}\n"
        f"Edad: {v['edad_urgencias']} anos\n"
        "Sexo: Masculino\n"
        f"Motivo de consulta: dolor en rodilla {v['lado_urgencias']} tras accidente de transito\n"
        "Diagnostico: S82.1 fractura de tibia\n"
        f"Se solicita: radiografia de rodilla {v['lado_urgencias']}",
        # 4. Informe radiológico
        "INFORME RADIOLOGICO\n"
        f"Radiografia de rodilla {v['lado_informe']}, proyecciones AP y lateral\n"
        "Hallazgos: trazo de fractura ficticio en tibia proximal",
        # 5. Descripción quirúrgica
        "DESCRIPCION QUIRURGICA\n"
        "Cirujano: Medico Ficticio\n"
        "Anestesiologo: Medico Ficticio Dos\n"
        f"Procedimiento: osteosintesis de tibia {v['lado_cirugia']}\n"
        f"Se utiliza {v['material_cirugia']}\n"
        "Firma: Medico Ficticio Registro medico 00000",
        # 6. Material de osteosíntesis
        "REMISION DE MATERIAL DE OSTEOSINTESIS\n"
        "Placa bloqueada de tibia, cantidad 1\n"
        "Tornillos de bloqueo, cantidad 6",
        # 7. Póliza
        "POLIZA SOAT - SEGURO OBLIGATORIO\n"
        f"Poliza No. {v['poliza_soporte']}\n"
        f"Placa del vehiculo: {v['placa_poliza']}\n"
        "Vigencia desde: 01/06/2024 hasta: 31/05/2025\n"
        f"Propietario: Propietario Ficticio C.C. {v['propietario_poliza']}",
        # 8. Epicrisis
        "EPICRISIS\n"
        f"Fecha de ingreso: {v['ingreso']}\n"
        f"Fecha de egreso: {v['egreso']}\n"
        f"Fecha del accidente: {v['accidente_epicrisis']}\n"
        "Diagnostico de egreso: S82.1\n"
        "Condicion de salida: estable",
    ]


def cuenta_ficticia(**cambios) -> bytes:
    return pdf_con_paginas(paginas_cuenta_ficticia(**cambios))


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
