"""Pruebas de cuentas en varios documentos de UNA factura (formato La Previsora), con documentos FICTICIOS."""

from auditoria.config import Configuracion
from auditoria.revision.paquetes import auditar_documentos, etiqueta, leer_nombre, tipo_sugerido
from pruebas import generadores

PAGINAS = generadores.paginas_cuenta_ficticia(factura="FIC100", factura_furips="FIC100")
FURIPS, FACTURA, EPICRISIS = PAGINAS[0], PAGINAS[2], PAGINAS[-2]
MISMA_FACTURA = "Todos los documentos son de la misma factura"


def _pdf(texto):
    return generadores.pdf_con_paginas([texto])


def _puntos(archivos):
    cuenta, puntos, _ = auditar_documentos(archivos, Configuracion())
    return cuenta, {p.nombre: p for p in puntos}


def test_nombres_con_y_sin_formato():
    assert leer_nombre("FEV_900385628_MDF65863.pdf") == ("FEV", "900385628", "MDF65863")
    assert leer_nombre("furips_900385628_mdf65863 (1).PDF") == ("FURIPS", "900385628", "MDF65863")
    assert leer_nombre("osteosintesis paciente.pdf") is None
    assert tipo_sugerido("EPI_900385628_MDF65863.pdf") == "Epicrisis"
    assert tipo_sugerido("osteosintesis paciente.pdf") is None
    assert etiqueta("FEV_900385628_MDF65863.pdf") == "FEV"
    assert etiqueta("Remision material osteosintesis.pdf") == "Remision material osteosintesis"


def test_documentos_con_cualquier_nombre_de_la_misma_factura():
    archivos = [
        ("FURIPS_900000001_FIC100.pdf", _pdf(FURIPS)),
        ("FEV_900000001_FIC100.pdf", _pdf(FACTURA)),
        ("epicrisis del paciente.pdf", _pdf(EPICRISIS + "\nPaciente: Paciente Ficticio Uno")),
        ("material osteosintesis.pdf", _pdf("REMISION DE MATERIAL DE OSTEOSINTESIS\nPaciente: Paciente Ficticio Uno\nIdentificacion: 1234567\nPlaca bloqueada, cantidad 1")),
    ]
    cuenta, puntos = _puntos(archivos)
    assert puntos[MISMA_FACTURA].resultado == "Correcto"
    assert "4 documento(s) corresponden a la factura FIC100" in puntos[MISMA_FACTURA].detalle, puntos[MISMA_FACTURA].detalle
    assert {cuenta.ubicacion(f) for f in cuenta.folios} == {
        "FURIPS folio 1", "FEV folio 1", "epicrisis del paciente folio 1", "material osteosintesis folio 1"}


def test_documento_de_otra_factura_por_contenido():
    otra = generadores.paginas_cuenta_ficticia(factura="FIC200")[2]
    archivos = [("furips.pdf", _pdf(FURIPS)), ("factura.pdf", _pdf(FACTURA)), ("factura otra.pdf", _pdf(otra))]
    _, puntos = _puntos(archivos)
    punto = puntos[MISMA_FACTURA]
    assert punto.resultado == "Error"
    assert "FIC100" in punto.detalle and "FIC200" in punto.detalle and "factura otra" in punto.detalle


def test_documento_de_otra_factura_por_nombre():
    archivos = [
        ("FURIPS_900000001_FIC100.pdf", _pdf(FURIPS)),
        ("FEV_900000001_FIC100.pdf", _pdf(FACTURA)),
        ("EPI_900000001_FIC300.pdf", _pdf(EPICRISIS)),  # Epicrisis de otra factura (el contenido no trae número)
    ]
    _, puntos = _puntos(archivos)
    punto = puntos[MISMA_FACTURA]
    assert punto.resultado == "Error"
    assert "el nombre del archivo dice FIC300" in punto.detalle


def test_documento_sin_factura_ni_paciente_queda_para_revisar():
    archivos = [("furips.pdf", _pdf(FURIPS)), ("factura.pdf", _pdf(FACTURA)), ("acta de reunion.pdf", _pdf("ACTA DE REUNION FICTICIA\nTemas varios sin datos de pacientes ni facturas"))]
    _, puntos = _puntos(archivos)
    punto = puntos[MISMA_FACTURA]
    assert punto.resultado == "Revisar"
    assert "acta de reunion" in punto.detalle


def test_prefijo_ayuda_a_clasificar_documento_sin_titulo():
    sin_titulo = "Texto ficticio de un resumen de egreso sin encabezado reconocible\nFecha de egreso: 12/01/2025"
    cuenta, _ = _puntos([("EPI_900000001_FIC100.pdf", _pdf(sin_titulo))])
    assert cuenta.folios[0].tipo == "Epicrisis"


def test_etiquetas_repetidas_usan_el_nombre_completo():
    cuenta, _ = _puntos([("FEV_1_FIC100.pdf", _pdf(FACTURA)), ("FEV_1_FIC100 (1).pdf", _pdf(FACTURA))])
    assert set(cuenta.etiquetas.values()) == {"FEV_1_FIC100.pdf", "FEV_1_FIC100 (1).pdf"}
