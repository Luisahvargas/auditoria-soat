"""Pruebas de cantidades cobradas vs. soportes (material de osteosíntesis y medicamentos ambulatorios).
Documentos FICTICIOS con el formato de una factura e informe quirúrgico reales."""

from auditoria.config import Configuracion
from auditoria.revision import auditar
from pruebas import generadores

FACTURA = """FACTURA ELECTRONICA DE VENTA:     FIC1001
                       MATERIAL QX Y/O MATERIAL ESPECIAL
   0030001     CLAVO DE TIBIA 9 X 320MM (ORTOPEDIA)                       1    $3.100.000      $3.100.000
   BBC-10372     TORNILLO BLOQUEADO 3.5MM X 14MM (ORTOPEDIA)              {tornillos}     $560.000      $1.120.000
                                                                          SubTotal            $4.220.000
                                 MEDICAMENTOS
 1111-4 ACETA005 ACETAMINOFEN 325MG+TRAMADOL 37.5MG TABLETA (AMBULATORIO)  {tabletas}     $795      $15.900
"""

CIRUGIA = """INFORME QUIRURGICO
DESCRIPCION QUIRURGICA
SE PASA CLAVO DE TIBIA 9 X 320MM CANTIDAD: 1 Y SE FIJA CON
(TORNILLO BLOQUEADO 3.5MM X 14MM CANTIDAD: 1)
Y 1 DISTAL (TORNILLO BLOQUEADO 3.5MM X 14MM #1)
 MATERIAL
MATERIAL ADICIONAL
CLAVO DE TIBIA 9 X 320MM Cantidad: 1 TORNILLO BLOQUEADO 3.5MM X 14MM Cantidad: {en_lista}
Nombre: CIRUJANO FICTICIO
Especialidad: ORTOPEDISTA
Registro medico: 12345
"""

SALIDA = """ORDEN DE MEDICAMENTOS - SALIDA
Nombre Generico      Concentración   Forma     Via     Frecuencia     Cant.   Letras
ACETAMINOFEN 325MG+TRAMADOL 37.5MG TABLETA      325 MG     TABLETA     ORAL    12 HORA(S)    20    VEINTE
"""


def _puntos(tornillos=2, en_lista=2, tabletas=20):
    paginas = [FACTURA.format(tornillos=tornillos, tabletas=tabletas), CIRUGIA.format(en_lista=en_lista), SALIDA]
    _, puntos, _ = auditar([("ficticia.pdf", generadores.pdf_con_paginas(paginas))], Configuracion())
    return {p.nombre: p for p in puntos}


MATERIAL = "Material de osteosíntesis: cantidades cobradas vs. informe quirúrgico"
AMBULATORIOS = "Medicamentos ambulatorios cobrados vs. orden de salida"


def test_material_coincide():
    assert _puntos()[MATERIAL].resultado == "Correcto"


def test_material_cobrado_de_mas_frente_a_la_lista_del_informe():
    punto = _puntos(tornillos=2, en_lista=1)[MATERIAL]
    assert punto.resultado == "Error"
    assert "se cobran 2 y la lista de material del informe registra 1" in punto.detalle
    assert "el relato de la cirugía menciona 2" in punto.detalle


def test_ambulatorios_coinciden_con_la_orden_de_salida():
    assert _puntos()[AMBULATORIOS].resultado == "Correcto"


def test_ambulatorios_cobrados_de_mas():
    punto = _puntos(tabletas=30)[AMBULATORIOS]
    assert punto.resultado == "Error"
    assert "se cobran 30 y la orden de salida dice 20" in punto.detalle
