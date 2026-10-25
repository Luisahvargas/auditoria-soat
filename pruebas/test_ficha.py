"""Pruebas de extracción y ficha maestra con una cuenta FICTICIA."""

from datetime import date

import pytest

from auditoria import catalogos
from auditoria.documentos import inventario
from auditoria.extraccion import ficha
from auditoria.texto import calcular_edad, leer_fecha
from pruebas import generadores


def _preparar(sesion, config, ids, **cambios):
    usuario_id, auditoria_id = ids
    inventario.cargar_archivo(sesion, config, auditoria_id, usuario_id, "cuenta.pdf", generadores.cuenta_ficticia(**cambios))
    ficha.extraer_auditoria(sesion, auditoria_id, usuario_id)
    sesion.commit()
    return ficha.construir_ficha(sesion, auditoria_id)


def _campo(ficha_construida, campo_id):
    return next(e for estados in ficha_construida.values() for e in estados if e.campo.id == campo_id)


# ---------------- Fechas y edad ----------------


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("15/05/1990", date(1990, 5, 15)),
        ("5-3-2025", date(2025, 3, 5)),
        ("2025-03-05", date(2025, 3, 5)),
        ("5 de marzo de 2025", date(2025, 3, 5)),
        ("31/02/2025", None),  # Fecha imposible
        ("sin fecha", None),
        ("", None),
    ],
)
def test_lectura_de_fechas(texto, esperado):
    assert leer_fecha(texto) == esperado


@pytest.mark.parametrize(
    "nacimiento, referencia, esperado",
    [
        (date(1990, 5, 15), date(2025, 1, 10), 34),  # Aún no cumplía años
        (date(1990, 1, 10), date(2025, 1, 10), 35),  # Cumplía ese día
        (date(2026, 1, 1), date(2025, 1, 10), None),  # Nacimiento posterior
        (None, date(2025, 1, 10), None),
    ],
)
def test_edad_con_fecha_del_accidente(nacimiento, referencia, esperado):
    assert calcular_edad(nacimiento, referencia) == esperado


# ---------------- Extracción ----------------


def test_cuenta_coherente_no_tiene_discrepancias(sesion, config_temporal, usuario_y_auditoria):
    resultado = _preparar(sesion, config_temporal, usuario_y_auditoria)

    identificacion = _campo(resultado, "paciente.numero_identificacion")
    # "1.234.567" del FURIPS y "1234567" de la factura y urgencias son el mismo valor.
    assert len(identificacion.valores) == 1 and not identificacion.discrepancia
    assert len(identificacion.valores[0].datos) == 3
    assert _campo(resultado, "accidente.placa").valores[0].normalizado == "ABC123"
    assert _campo(resultado, "administrativo.numero_factura").valores[0].normalizado == "FE1001"
    edad = ficha.edad_al_accidente(resultado)
    assert edad.valor == 34


def test_cada_dato_guarda_archivo_pagina_evidencia_y_metodo(sesion, config_temporal, usuario_y_auditoria):
    resultado = _preparar(sesion, config_temporal, usuario_y_auditoria)
    datos = _campo(resultado, "paciente.fecha_nacimiento").valores[0].datos

    assert {d.numero_pagina for d in datos} == {1, 3}  # FURIPS y urgencias
    assert all(d.documento_id and d.evidencia and d.metodo == "Texto PDF" for d in datos)
    assert all(d.estado_validacion == catalogos.VALIDACION_PENDIENTE for d in datos)


def test_identificacion_distinta_conserva_ambos_valores(sesion, config_temporal, usuario_y_auditoria):
    resultado = _preparar(sesion, config_temporal, usuario_y_auditoria, id_factura="7654321")
    identificacion = _campo(resultado, "paciente.numero_identificacion")

    assert identificacion.discrepancia
    assert {v.normalizado for v in identificacion.valores} == {"1234567", "7654321"}


def test_cedulas_de_conductor_y_propietario_no_se_toman_como_del_paciente(sesion, config_temporal, usuario_y_auditoria):
    resultado = _preparar(sesion, config_temporal, usuario_y_auditoria)
    valores = {v.normalizado for v in _campo(resultado, "paciente.numero_identificacion").valores}
    assert "5555555" not in valores and "9876543" not in valores
    assert _campo(resultado, "administrativo.conductor_identificacion").valores[0].normalizado == "5555555"


def test_fecha_de_nacimiento_discrepante_deja_edad_no_evaluable(sesion, config_temporal, usuario_y_auditoria):
    resultado = _preparar(sesion, config_temporal, usuario_y_auditoria, nacimiento_urgencias="15/05/1991")
    edad = ficha.edad_al_accidente(resultado)
    assert edad.valor is None
    assert catalogos.NO_EVALUABLE in edad.explicacion


def test_campos_vacios_cuando_no_hay_documentos(sesion, usuario_y_auditoria):
    resultado = ficha.construir_ficha(sesion, usuario_y_auditoria[1])
    assert all(e.sin_dato for estados in resultado.values() for e in estados)
    assert ficha.edad_al_accidente(resultado).valor is None


# ---------------- Acciones del auditor ----------------


def test_correccion_conserva_valor_original(sesion, config_temporal, usuario_y_auditoria):
    usuario_id, auditoria_id = usuario_y_auditoria
    resultado = _preparar(sesion, config_temporal, usuario_y_auditoria, id_factura="7654321")
    dato = next(
        d for v in _campo(resultado, "paciente.numero_identificacion").valores for d in v.datos if d.valor == "7654321"
    )
    ficha.corregir_dato(sesion, dato.id, "1234567", usuario_id)
    sesion.commit()

    assert dato.valor == "7654321" and dato.valor_corregido == "1234567"
    assert dato.estado_validacion == catalogos.VALIDACION_CORREGIDO and dato.usuario_validacion_id == usuario_id
    nueva = ficha.construir_ficha(sesion, auditoria_id)
    assert not _campo(nueva, "paciente.numero_identificacion").discrepancia


def test_reextraer_no_borra_lo_revisado(sesion, config_temporal, usuario_y_auditoria):
    usuario_id, auditoria_id = usuario_y_auditoria
    resultado = _preparar(sesion, config_temporal, usuario_y_auditoria)
    dato = _campo(resultado, "accidente.fecha").valores[0].datos[0]
    ficha.validar_dato(sesion, dato.id, usuario_id)
    sesion.commit()

    ficha.extraer_auditoria(sesion, auditoria_id, usuario_id)
    sesion.commit()
    datos = [d for v in _campo(ficha.construir_ficha(sesion, auditoria_id), "accidente.fecha").valores for d in v.datos]
    assert len(datos) == 2  # FURIPS y epicrisis, sin duplicados
    assert any(d.id == dato.id and d.estado_validacion == catalogos.VALIDACION_VALIDADO for d in datos)


def test_descartar_dato_lo_excluye_de_la_ficha(sesion, config_temporal, usuario_y_auditoria):
    usuario_id, auditoria_id = usuario_y_auditoria
    resultado = _preparar(sesion, config_temporal, usuario_y_auditoria, placa_poliza="XYZ987")
    placa = _campo(resultado, "accidente.placa")
    assert placa.discrepancia
    dato = next(d for v in placa.valores for d in v.datos if d.valor == "XYZ987")
    ficha.descartar_dato(sesion, dato.id, usuario_id)
    sesion.commit()
    assert not _campo(ficha.construir_ficha(sesion, auditoria_id), "accidente.placa").discrepancia


def test_dato_manual_valida_documento_y_pagina(sesion, config_temporal, usuario_y_auditoria):
    usuario_id, auditoria_id = usuario_y_auditoria
    _preparar(sesion, config_temporal, usuario_y_auditoria)
    documento = inventario.listar_documentos(sesion, auditoria_id)[0]

    dato = ficha.agregar_dato_manual(sesion, auditoria_id, "accidente.direccion", "Calle ficticia 1", usuario_id, documento.id, 1)
    assert dato.metodo == "Manual" and dato.estado_validacion == catalogos.VALIDACION_VALIDADO
    with pytest.raises(ficha.ErrorFicha):
        ficha.agregar_dato_manual(sesion, auditoria_id, "accidente.direccion", "x", usuario_id, documento.id, 99)
    with pytest.raises(ficha.ErrorFicha):
        ficha.agregar_dato_manual(sesion, auditoria_id, "campo.inventado", "x", usuario_id)
    with pytest.raises(ficha.ErrorFicha):
        ficha.agregar_dato_manual(sesion, auditoria_id, "accidente.direccion", "   ", usuario_id)
