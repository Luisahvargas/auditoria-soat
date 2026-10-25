"""Pruebas de carga y lectura de PDF con documentos ficticios generados por código."""

import hashlib
import os

import pytest

from auditoria import catalogos
from auditoria.auditorias import servicio as servicio_auditorias
from auditoria.db.repositorios import RepositorioTrazabilidad
from auditoria.documentos import almacenamiento, inventario, lector_pdf
from pruebas import generadores


def _cargar(sesion, config, ids, nombre, contenido):
    usuario_id, auditoria_id = ids
    resultado = inventario.cargar_archivo(sesion, config, auditoria_id, usuario_id, nombre, contenido)
    sesion.commit()
    return resultado


def test_pdf_con_texto_se_lee_por_pagina(sesion, config_temporal, usuario_y_auditoria):
    contenido = generadores.pdf_con_texto()
    resultado = _cargar(sesion, config_temporal, usuario_y_auditoria, "historia.pdf", contenido)

    assert resultado.resultado == "Cargado"
    documento = inventario.listar_documentos(sesion, usuario_y_auditoria[1], con_paginas=True)[0]
    assert documento.estado == catalogos.PROC_PROCESADO
    assert documento.numero_paginas == 2
    assert [p.numero for p in documento.paginas] == [1, 2]
    assert "HISTORIA CLINICA" in documento.paginas[0].texto
    assert "EVOLUCION" in documento.paginas[1].texto
    # Página interna ("Pagina 2 de 2") distinta de la página del archivo.
    assert documento.paginas[1].pagina_interna == "2 de 2"


def test_original_se_copia_sin_modificar_y_con_hash(sesion, config_temporal, usuario_y_auditoria):
    contenido = generadores.pdf_con_texto()
    _cargar(sesion, config_temporal, usuario_y_auditoria, "historia.pdf", contenido)
    documento = inventario.listar_documentos(sesion, usuario_y_auditoria[1])[0]

    copia = almacenamiento.ruta_absoluta(config_temporal.ruta_datos, documento.ruta_relativa)
    assert copia.read_bytes() == contenido
    assert documento.hash_sha256 == hashlib.sha256(contenido).hexdigest()
    assert not os.access(copia, os.W_OK)  # Queda en solo lectura


def test_pagina_en_blanco_e_imagen_requieren_analisis_visual(sesion, config_temporal, usuario_y_auditoria):
    _cargar(sesion, config_temporal, usuario_y_auditoria, "mixto.pdf", generadores.pdf_con_pagina_en_blanco_e_imagen())
    documento = inventario.listar_documentos(sesion, usuario_y_auditoria[1], con_paginas=True)[0]

    assert documento.estado == catalogos.PROC_REQUIERE_REVISION
    assert [p.requiere_analisis_visual for p in documento.paginas] == [False, True, True]
    assert "2-3" in documento.mensaje


def test_pdf_concatenado_conserva_numeracion(sesion, config_temporal, usuario_y_auditoria):
    _cargar(sesion, config_temporal, usuario_y_auditoria, "cuenta.pdf", generadores.pdf_concatenado())
    documento = inventario.listar_documentos(sesion, usuario_y_auditoria[1], con_paginas=True)[0]

    assert documento.numero_paginas == 4
    assert "FURIPS" in documento.paginas[0].texto
    assert "FACTURA" in documento.paginas[1].texto
    assert "EPICRISIS" in documento.paginas[3].texto


def test_duplicado_se_detecta_por_hash(sesion, config_temporal, usuario_y_auditoria):
    contenido = generadores.pdf_con_texto()
    _cargar(sesion, config_temporal, usuario_y_auditoria, "a.pdf", contenido)
    segundo = _cargar(sesion, config_temporal, usuario_y_auditoria, "copia_con_otro_nombre.pdf", contenido)

    assert segundo.resultado == "Duplicado"
    assert len(inventario.listar_documentos(sesion, usuario_y_auditoria[1])) == 1


@pytest.mark.parametrize(
    "nombre, contenido, mensaje",
    [("virus.exe", b"MZ", "no permitido"), ("vacio.pdf", b"", "vacío")],
)
def test_archivos_rechazados(sesion, config_temporal, usuario_y_auditoria, nombre, contenido, mensaje):
    resultado = _cargar(sesion, config_temporal, usuario_y_auditoria, nombre, contenido)
    assert resultado.resultado == "Rechazado"
    assert mensaje in resultado.mensaje


def test_pdf_danado_queda_en_error_sin_detener(sesion, config_temporal, usuario_y_auditoria):
    resultado = _cargar(sesion, config_temporal, usuario_y_auditoria, "danado.pdf", b"%PDF-1.4 esto no es un pdf real")
    documento = inventario.listar_documentos(sesion, usuario_y_auditoria[1])[0]

    assert resultado.resultado == "Cargado"
    assert documento.estado == catalogos.PROC_ERROR
    assert documento.mensaje


def test_xml_y_json_quedan_pendientes_sin_inventar_estructura(sesion, config_temporal, usuario_y_auditoria):
    _cargar(sesion, config_temporal, usuario_y_auditoria, "factura.xml", b"<ficticio/>")
    _cargar(sesion, config_temporal, usuario_y_auditoria, "rips.json", b'{"ficticio": true}')
    documentos = inventario.listar_documentos(sesion, usuario_y_auditoria[1])

    assert {d.tipo_archivo for d in documentos} == {"xml", "json"}
    assert all(d.estado == catalogos.PROC_PENDIENTE for d in documentos)


def test_imagen_de_pagina_se_genera_y_se_reutiliza(sesion, config_temporal, usuario_y_auditoria):
    _cargar(sesion, config_temporal, usuario_y_auditoria, "historia.pdf", generadores.pdf_con_texto())
    documento = inventario.listar_documentos(sesion, usuario_y_auditoria[1])[0]

    imagen = inventario.obtener_imagen_pagina(config_temporal, documento, 1, 300)
    assert imagen.startswith(b"\x89PNG")
    assert almacenamiento.ruta_miniatura(config_temporal.ruta_datos, documento.hash_sha256, 1, 300).exists()
    with pytest.raises(lector_pdf.ErrorLecturaPDF):
        inventario.obtener_imagen_pagina(config_temporal, documento, 99, 300)


def test_trazabilidad_no_guarda_nombre_de_archivo(sesion, config_temporal, usuario_y_auditoria):
    _cargar(sesion, config_temporal, usuario_y_auditoria, "Paciente Ficticio Uno.pdf", generadores.pdf_con_texto())
    registros = RepositorioTrazabilidad(sesion).listar_por_auditoria(usuario_y_auditoria[1])

    cargas = [r for r in registros if r.accion == "documento_cargado"]
    assert len(cargas) == 1
    assert "Paciente" not in cargas[0].detalle


def test_no_se_carga_en_auditoria_finalizada(sesion, config_temporal, usuario_y_auditoria):
    auditoria = servicio_auditorias.obtener_auditoria(sesion, usuario_y_auditoria[1])
    auditoria.estado = catalogos.AUDITORIA_FINALIZADA
    sesion.commit()
    with pytest.raises(servicio_auditorias.ErrorAuditoria):
        _cargar(sesion, config_temporal, usuario_y_auditoria, "a.pdf", generadores.pdf_con_texto())


def test_ruta_fuera_de_datos_se_rechaza(config_temporal):
    with pytest.raises(almacenamiento.ErrorAlmacenamiento):
        almacenamiento.ruta_absoluta(config_temporal.ruta_datos, "../../windows/system32/x")
