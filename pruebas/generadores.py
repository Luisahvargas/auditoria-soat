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


VALORES_CUENTA = {
    "nombre": "Paciente Ficticio Uno",
    "nombre_factura": None,  # None = el mismo nombre del paciente
    "id_furips": "1.234.567",
    "id_admision": "1234567",
    "telefono_furips": "3001234567",
    "telefono_admision": "3001234567",
    "nacimiento_furips": "15/05/1990",
    "nacimiento_admision": "15/05/1990",
    "edad_admision": "34",
    "sexo_admision": "Masculino",
    "sexo_epicrisis": "M",
    "evento_furips": "10/01/2025",
    "evento_admision": "10/01/2025",
    "direccion_furips": "Calle 10 # 20-30",
    "direccion_admision": "Cl 10 No 20 30",
    "zona_furips": "urbana",
    "zona_admision": "urbana",
    "calidad_furips": "peaton",
    "calidad_admision": "peaton",
    "relato_furips": "Peaton atropellado por motocicleta al cruzar la via",
    "relato_admision": "Paciente peaton quien es atropellado por motocicleta",
    "factura_furips": "FE-1001",
    "factura": "FE-1001",
    "cobro_urgencia": True,
    "con_urgencias": True,
    "dias_factura": "2",
    "ingreso": "10/01/2025",
    "egreso": "12/01/2025",
    "con_evolucion": True,
    "poliza_furips": "1234567890",
    "poliza_soporte": "1234567890",
    "poliza_runt": "1234567890",
    "vigencia_desde": "01/06/2024",
    "vigencia_hasta": "31/05/2025",
    "vigencia_hasta_runt": "31/05/2025",
    "placa_furips": "ABC123",
    "placa_poliza": "ABC123",
    "placa_runt": "ABC123",
    "propietario_furips": "9.876.543",
    "propietario_runt": "9876543",
    "conductor_furips": "5.555.555",
    "lado_urgencias": "derecha",
    "lado_informe": "derecha",
    "lado_cirugia": "derecha",
    "interpretacion": "Hallazgos: trazo de fractura ficticio en tibia proximal",
    "orden_rx": True,
    "material_cirugia": "placa bloqueada y 6 tornillos",
    "firma_informe": "Dr. Medico Radiologo Ficticio Registro medico 11111",
    "orden_ambulatoria": True,
}


def paginas_cuenta_ficticia(**cambios) -> list[str]:
    """Textos de una cuenta SOAT FICTICIA. Los parámetros permiten introducir errores."""
    v = {**VALORES_CUENTA, **cambios}
    paginas = [
        # 1. FURIPS
        "FORMULARIO UNICO DE RECLAMACION FURIPS\n"
        f"Nombre de la victima: {v['nombre']}\n"
        f"C.C. {v['id_furips']}\n"
        f"Telefono: {v['telefono_furips']}\n"
        f"Fecha de nacimiento: {v['nacimiento_furips']}\n"
        f"Fecha del accidente: {v['evento_furips']}\n"
        f"Direccion del accidente: {v['direccion_furips']}\n"
        f"Zona: {v['zona_furips']}\n"
        f"Condicion de la victima: {v['calidad_furips']}\n"
        f"Relato del accidente: {v['relato_furips']}\n"
        f"Placa: {v['placa_furips']}\n"
        f"Poliza SOAT No. {v['poliza_furips']}\n"
        f"Vigencia desde: {v['vigencia_desde']} hasta: {v['vigencia_hasta']}\n"
        f"Factura No. {v['factura_furips']}\n"
        "Propietario: Propietario Ficticio\n"
        f"Documento del propietario C.C. {v['propietario_furips']}\n"
        "Conductor: Conductor Ficticio\n"
        f"Documento del conductor C.C. {v['conductor_furips']}",
        # 2. Hoja de admisión
        "HOJA DE ADMISION\n"
        f"Paciente: {v['nombre']}\n"
        f"Identificacion: {v['id_admision']}\n"
        f"Telefono: {v['telefono_admision']}\n"
        f"Fecha de nacimiento: {v['nacimiento_admision']}\n"
        f"Edad: {v['edad_admision']} anos\n"
        f"Sexo: {v['sexo_admision']}\n"
        f"Fecha del accidente: {v['evento_admision']}\n"
        f"Lugar del accidente: {v['direccion_admision']}\n"
        f"Zona: {v['zona_admision']}\n"
        f"Calidad: {v['calidad_admision']}\n"
        f"Fecha de ingreso: {v['ingreso']}\n"
        f"Enfermedad actual: {v['relato_admision']}",
        # 3. Factura
        f"FACTURA ELECTRONICA DE VENTA No. {v['factura']}\n"
        "Fecha de expedicion: 15/01/2025\n"
        "NIT 900123456-1\n"
        f"Paciente: {v['nombre_factura'] or v['nombre']}\n"
        + ("Consulta de urgencias 1\n" if v["cobro_urgencia"] else "")
        + f"Estancia hospitalaria {v['dias_factura']} dias\n"
        "Radiografia de rodilla 1\n"
        "Material de osteosintesis 1\n"
        "Valor total: 1000000",
    ]
    if v["con_urgencias"]:
        paginas.append(
            "ATENCION INICIAL DE URGENCIAS\n"
            "Triage II\n"
            f"Motivo de consulta: dolor en rodilla {v['lado_urgencias']} tras accidente de transito\n"
            "Diagnostico: S82.1 fractura de tibia\n"
            + (f"Se solicita: radiografia de rodilla {v['lado_urgencias']}\n" if v["orden_rx"] else "")
            + "Medico tratante: Dr. Urgenciologo Ficticio"
        )
    paginas += [
        # Informe radiológico
        "INFORME RADIOLOGICO\n"
        f"Radiografia de rodilla {v['lado_informe']}, proyecciones AP y lateral\n"
        f"{v['interpretacion']}\n"
        f"{v['firma_informe']}",
        # Descripción quirúrgica
        "DESCRIPCION QUIRURGICA\n"
        "Cirujano: Dr. Cirujano Ficticio\n"
        "Anestesiologo: Dr. Anestesiologo Ficticio\n"
        f"Procedimiento: osteosintesis de tibia {v['lado_cirugia']}\n"
        f"Se utiliza {v['material_cirugia']}\n"
        "Firma: Registro medico 22222",
        # Material
        "REMISION DE MATERIAL DE OSTEOSINTESIS\n"
        "Placa bloqueada de tibia, cantidad 1\n"
        "Tornillos de bloqueo, cantidad 6",
        # Póliza
        "POLIZA SOAT - SEGURO OBLIGATORIO\n"
        f"Poliza No. {v['poliza_soporte']}\n"
        f"Placa del vehiculo: {v['placa_poliza']}\n"
        f"Vigencia desde: {v['vigencia_desde']} hasta: {v['vigencia_hasta']}",
        # RUNT
        "CONSULTA RUNT - REGISTRO UNICO NACIONAL DE TRANSITO\n"
        f"Placa: {v['placa_runt']}\n"
        f"Poliza SOAT No. {v['poliza_runt']}\n"
        f"Vigencia desde: {v['vigencia_desde']} hasta: {v['vigencia_hasta_runt']}\n"
        f"Documento del propietario C.C. {v['propietario_runt']}",
    ]
    if v["con_evolucion"]:
        paginas.append(
            "NOTA DE EVOLUCION\nSubjetivo: paciente estable. Objetivo: sin cambios. Analisis y plan: continuar manejo.\n"
            "Medico: Dr. Ortopedista Ficticio Registro medico 33333"
        )
    paginas.append(
        "EPICRISIS\n"
        f"Fecha de ingreso: {v['ingreso']}\n"
        f"Fecha de egreso: {v['egreso']}\n"
        f"Sexo: {v['sexo_epicrisis']}\n"
        "Diagnostico de egreso: S82.1\n"
        "Condicion de salida: estable\n"
        "Medico tratante: Dr. Ortopedista Ficticio Registro medico 33333"
    )
    if v["orden_ambulatoria"]:
        paginas.append(
            "FORMULA MEDICA - MEDICAMENTOS AMBULATORIOS\n"
            "Acetaminofen 500 mg cada 8 horas por 5 dias\n"
            "Firma del paciente: ____________________"
        )
    return paginas


def cuenta_ficticia(**cambios) -> bytes:
    return pdf_con_paginas(paginas_cuenta_ficticia(**cambios))


def pdf_con_pagina_escaneada() -> bytes:
    return pdf_con_paginas(["EPICRISIS\nResumen de egreso ficticio con texto suficiente para leerse.", None, SOLO_IMAGEN])
