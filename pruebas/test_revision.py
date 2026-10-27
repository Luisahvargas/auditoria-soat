"""Pruebas de la revisión de cuentas con cuentas FICTICIAS generadas por código."""

from dataclasses import replace

import pytest

from auditoria.config import Configuracion
from auditoria.documentos import ocr
from auditoria.revision import auditar
from auditoria.revision.puntos import CORRECTO, ERROR, FALTA, NO_APLICA, REVISAR
from pruebas import generadores

CONFIG = Configuracion()


def _resultados(**cambios) -> dict:
    cuenta, puntos, texto = auditar([("cuenta.pdf", generadores.cuenta_ficticia(**cambios))], CONFIG)
    return {p.nombre: p for p in puntos}


def test_cuenta_coherente_no_tiene_errores():
    resultados = _resultados()
    errores = [p for p in resultados.values() if p.resultado == ERROR]
    assert errores == []
    for nombre in ("Teléfono", "Fecha de nacimiento", "Fecha del evento", "Dirección del evento", "Zona (rural/urbana)",
                   "Edad (calculada a la fecha del evento)", "Calidad del accidentado", "Relato de los hechos",
                   "Número de factura (FURIPS vs. factura)", "Cobro de urgencia", "Estancia",
                   "Número de póliza (FURIPS, póliza y RUNT)", "Fecha del evento dentro de la vigencia",
                   "Placa (los documentos SOAT son del vehículo del evento)", "Todos los folios son del mismo paciente",
                   "Sexo en todos los folios", "Lateralidad", "Material de osteosíntesis descrito en el informe quirúrgico",
                   "Ayudas diagnósticas justificadas", "Exámenes radiológicos: informe e interpretación",
                   "Médicos de los informes con firma/registro"):
        assert resultados[nombre].resultado == CORRECTO, (nombre, resultados[nombre].detalle)


@pytest.mark.parametrize(
    "punto, cambios",
    [
        ("Teléfono", {"telefono_admision": "3109999999"}),
        ("Fecha de nacimiento", {"nacimiento_admision": "15/05/1991"}),
        ("Fecha del evento", {"evento_admision": "11/01/2025"}),
        ("Dirección del evento", {"direccion_admision": "Carrera 45 # 8-12"}),
        ("Zona (rural/urbana)", {"zona_admision": "rural"}),
        ("Edad (calculada a la fecha del evento)", {"edad_admision": "40"}),
        ("Calidad del accidentado", {"calidad_admision": "conductor"}),
        ("Relato de los hechos", {"relato_admision": "Paciente conductor de motocicleta que cae de su vehiculo"}),
        ("Número de factura (FURIPS vs. factura)", {"factura": "FE-2002"}),
        ("Cobro de urgencia", {"con_urgencias": False}),
        ("Estancia", {"dias_factura": "8"}),
        ("Número de póliza (FURIPS, póliza y RUNT)", {"poliza_runt": "9999999999"}),
        ("Vigencia hasta (FURIPS, póliza y RUNT)", {"vigencia_hasta_runt": "31/12/2024"}),
        ("Fecha del evento dentro de la vigencia", {"evento_furips": "10/07/2025", "evento_admision": "10/07/2025"}),
        ("Placa (los documentos SOAT son del vehículo del evento)", {"placa_poliza": "XYZ987"}),
        ("Propietario: identificación", {"propietario_runt": "1111111"}),
        ("Todos los folios son del mismo paciente", {"id_admision": "7654321"}),
        ("Todos los folios son del mismo paciente", {"nombre_factura": "Persona Totalmente Distinta"}),
        ("Sexo en todos los folios", {"sexo_epicrisis": "F"}),
        ("Lateralidad", {"lado_informe": "izquierda"}),
        ("Material de osteosíntesis descrito en el informe quirúrgico", {"material_cirugia": "clavo endomedular"}),
    ],
)
def test_cada_punto_detecta_su_error(punto, cambios):
    resultado = _resultados(**cambios)[punto]
    assert resultado.resultado == ERROR, (punto, resultado.detalle)
    assert resultado.folios, "El error debe indicar el folio"


@pytest.mark.parametrize(
    "punto, cambios, esperado",
    [
        ("Ayudas diagnósticas justificadas", {"orden_rx": False, "con_urgencias": False}, FALTA),
        ("Exámenes radiológicos: informe e interpretación", {"interpretacion": "Proyecciones AP y lateral"}, REVISAR),
        ("Médicos de los informes con firma/registro", {"firma_informe": "Dr. Medico Radiologo Ficticio"}, REVISAR),
        ("Médicos de los informes con firma/registro", {"firma_informe": "Informe sin autor"}, FALTA),
        ("Orden de medicamentos ambulatorios firmada por el paciente", {"orden_ambulatoria": False}, FALTA),
        ("Orden de medicamentos ambulatorios firmada por el paciente", {}, REVISAR),
        ("Estancia", {"con_evolucion": False}, FALTA),
        ("Cobro de urgencia", {"cobro_urgencia": False}, REVISAR),
    ],
)
def test_faltantes_y_puntos_para_revisar(punto, cambios, esperado):
    resultado = _resultados(**cambios)[punto]
    assert resultado.resultado == esperado, (punto, resultado.detalle)


def test_dato_ausente_es_falta_y_no_error():
    """No se inventa: si un dato no está, se dice que falta, no que está mal."""
    paginas = generadores.paginas_cuenta_ficticia()
    paginas[1] = paginas[1].replace("Telefono: 3001234567\n", "")
    _, puntos, _ = auditar([("cuenta.pdf", generadores.pdf_con_paginas(paginas))], CONFIG)
    telefono = next(p for p in puntos if p.nombre == "Teléfono")
    assert telefono.resultado == FALTA and "hoja de admisión" in telefono.detalle


def test_folios_escaneados_se_informan_como_no_revisados():
    cuenta, _, texto = auditar([("escaneo.pdf", generadores.pdf_con_pagina_escaneada())], CONFIG)
    assert [f.numero for f in cuenta.folios_sin_texto()] == [3]  # La imagen sin texto
    assert [f.numero for f in cuenta.folios_en_blanco()] == [2]  # La hoja en blanco se informa aparte
    assert "1 folio(s) escaneados no se pudieron leer y no fueron revisados: folio 3" in texto
    assert "Folios en blanco (sin contenido): folio 2." in texto


def test_ocr_simulado_lee_folios_escaneados(monkeypatch):
    monkeypatch.setattr(ocr, "estado_ocr", lambda _c: ocr.EstadoOCR(True, "simulado", "tesseract"))
    monkeypatch.setattr(ocr, "ocr_imagen", lambda _e, _png: "INFORME RADIOLOGICO radiografia de rodilla, texto reconocido ficticio")
    cuenta, _, _ = auditar([("escaneo.pdf", generadores.pdf_con_pagina_escaneada())], replace(CONFIG, motor_ocr="tesseract"))
    assert not cuenta.folios_sin_texto()
    assert [f.metodo for f in cuenta.folios] == ["Texto PDF", "En blanco", "OCR"]  # La hoja en blanco no pasa por OCR


def test_diferencia_que_solo_viene_del_ocr_queda_para_revisar(monkeypatch):
    """Un folio escaneado mal leído por OCR no debe producir un error, sino 'Revisar'."""
    monkeypatch.setattr(ocr, "estado_ocr", lambda _c: ocr.EstadoOCR(True, "simulado", "tesseract"))
    monkeypatch.setattr(ocr, "ocr_imagen", lambda _e, _png: "RECUENTO DE MATERIAL\nPaciente: Paciente Ficticio Uno\nEdad: 2 anos\nSexo: F")
    paginas = generadores.paginas_cuenta_ficticia() + [generadores.SOLO_IMAGEN]
    _, puntos, _ = auditar([("cuenta.pdf", generadores.pdf_con_paginas(paginas))], replace(CONFIG, motor_ocr="tesseract"))
    resultados = {p.nombre: p for p in puntos}
    for nombre in ("Edad (calculada a la fecha del evento)", "Sexo en todos los folios"):
        assert resultados[nombre].resultado == REVISAR, (nombre, resultados[nombre].detalle)
        assert "OCR" in resultados[nombre].detalle


def test_lectura_de_la_cuenta_avisa_documentos_no_reconocidos():
    _, _, texto = auditar([("x.pdf", generadores.pdf_con_paginas(["HOJA DE ADMISION\nPaciente: Paciente Ficticio Uno"]))], CONFIG)
    lectura = texto.split("LECTURA DE LA CUENTA")[1]
    assert "Documentos reconocidos: Hoja de admisión (1)" in lectura
    assert "No se reconoció FURIPS" in lectura
    assert "No se reconoció Factura" in lectura


def test_varios_archivos_indican_archivo_y_folio():
    paginas = generadores.paginas_cuenta_ficticia(factura="FE-2002")
    archivos = [("furips.pdf", generadores.pdf_con_paginas(paginas[:1])), ("soportes.pdf", generadores.pdf_con_paginas(paginas[1:]))]
    _, puntos, texto = auditar(archivos, CONFIG)
    factura = next(p for p in puntos if p.nombre == "Número de factura (FURIPS vs. factura)")
    assert factura.resultado == ERROR
    assert "furips.pdf folio 1" in factura.folios and "soportes.pdf folio 2" in factura.folios


def test_pdf_danado_no_detiene_la_revision():
    cuenta, puntos, texto = auditar([("danado.pdf", b"%PDF-1.4 no es un pdf"), ("cuenta.pdf", generadores.cuenta_ficticia())], CONFIG)
    assert cuenta.errores_lectura and "danado.pdf" in cuenta.errores_lectura[0]
    assert "no se pudo leer danado.pdf" in texto
    assert puntos


def test_texto_para_copiar_lista_primero_los_errores():
    _, _, texto = auditar([("cuenta.pdf", generadores.cuenta_ficticia(factura="FE-2002", lado_informe="izquierda"))], CONFIG)
    assert texto.startswith("AUDITORÍA DE CUENTA SOAT")
    assert "Resultado: 2 error(es)" in texto
    assert texto.index("ERRORES ENCONTRADOS") < texto.index("SIN ERRORES")
    seccion_errores = texto.split("ERRORES ENCONTRADOS")[1].split("\n\n")[0]
    assert "Número de factura" in seccion_errores and "Lateralidad" in seccion_errores


def test_sin_material_ni_estudios_es_no_aplica():
    _, puntos, _ = auditar([("x.pdf", generadores.pdf_con_paginas(["HOJA DE ADMISION\nPaciente: Paciente Ficticio Uno\nSexo: F"]))], CONFIG)
    resultados = {p.nombre: p.resultado for p in puntos}
    assert resultados["Material de osteosíntesis descrito en el informe quirúrgico"] == NO_APLICA
    assert resultados["Exámenes radiológicos: informe e interpretación"] == NO_APLICA
