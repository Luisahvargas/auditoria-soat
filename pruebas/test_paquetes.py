"""Pruebas de cuentas por documentos separados (formato La Previsora) con documentos FICTICIOS."""

from auditoria.config import Configuracion
from auditoria.revision.paquetes import agrupar_por_factura, auditar_factura, documentos_faltantes, leer_nombre, repetidos
from pruebas import generadores

PAGINAS = generadores.paginas_cuenta_ficticia(factura="FIC100", factura_furips="FIC100")
FURIPS, FACTURA, EPICRISIS = PAGINAS[0], PAGINAS[2], PAGINAS[-2]


def _pdf(texto):
    return generadores.pdf_con_paginas([texto])


def test_leer_nombre():
    assert leer_nombre("FEV_900385628_MDF65863.pdf") == ("FEV", "900385628", "MDF65863")
    assert leer_nombre("furips_900385628_mdf65863.PDF") == ("FURIPS", "900385628", "MDF65863")
    assert leer_nombre("EPI_900385628_MDF65863 (1).pdf") == ("EPI", "900385628", "MDF65863")
    assert leer_nombre("cuenta completa.pdf") is None


def test_agrupa_por_factura_y_detecta_faltantes():
    archivos = [
        ("FEV_900000001_FIC100.pdf", b"a"), ("EPI_900000001_FIC100.pdf", b"b"), ("FURIPS_900000001_FIC100.pdf", b"c"),
        ("FEV_900000001_FIC200.pdf", b"d"), ("FURIPS_900000001_FIC200.pdf", b"e"),
        ("otro archivo.pdf", b"f"),
    ]
    grupos, no_reconocidos = agrupar_por_factura(archivos)
    assert list(grupos) == ["FIC100", "FIC200"]
    assert [s.prefijo for s in grupos["FIC100"]] == ["FURIPS", "FEV", "EPI"]  # Orden de soportes.yaml
    assert no_reconocidos == ["otro archivo.pdf"]
    assert documentos_faltantes(grupos) == {"FIC100": [], "FIC200": ["EPI"]}


def test_repetidos():
    grupos, _ = agrupar_por_factura([("FEV_1_A.pdf", b"a"), ("FEV_1_A (1).pdf", b"b"), ("FEV_1_A.pdf", b"c")])
    assert repetidos(grupos["A"]) == ["FEV"]


def test_auditar_factura_usa_solo_sus_documentos_y_cita_por_prefijo():
    archivos = [
        ("FURIPS_900000001_FIC100.pdf", _pdf(FURIPS)),
        ("FEV_900000001_FIC100.pdf", _pdf(FACTURA)),
        ("EPI_900000001_FIC100.pdf", _pdf(EPICRISIS)),
    ]
    grupos, _ = agrupar_por_factura(archivos)
    cuenta, puntos, texto = auditar_factura(grupos["FIC100"], Configuracion())
    resultados = {p.nombre: p for p in puntos}

    assert resultados["Número de factura del nombre de los archivos"].resultado == "Correcto"
    assert resultados["Número de factura (FURIPS vs. factura)"].resultado == "Correcto"
    assert {cuenta.ubicacion(f) for f in cuenta.folios} == {"FURIPS folio 1", "FEV folio 1", "EPI folio 1"}


def test_factura_del_nombre_distinta_a_la_del_documento():
    archivos = [("FURIPS_900000001_FIC999.pdf", _pdf(FURIPS)), ("FEV_900000001_FIC999.pdf", _pdf(FACTURA))]
    grupos, _ = agrupar_por_factura(archivos)
    _, puntos, _ = auditar_factura(grupos["FIC999"], Configuracion())
    punto = next(p for p in puntos if p.nombre == "Número de factura del nombre de los archivos")
    assert punto.resultado == "Error"
    assert "FIC999" in punto.detalle and "FIC100" in punto.detalle


def test_prefijo_ayuda_a_clasificar_documento_sin_titulo():
    sin_titulo = "Texto ficticio de un resumen de egreso sin encabezado reconocible\nFecha de egreso: 12/01/2025"
    grupos, _ = agrupar_por_factura([("EPI_900000001_FIC100.pdf", _pdf(sin_titulo))])
    cuenta, _, _ = auditar_factura(grupos["FIC100"], Configuracion())
    assert cuenta.folios[0].tipo == "Epicrisis"
