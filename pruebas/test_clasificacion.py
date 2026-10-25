"""Pruebas de clasificación documental y OCR opcional (documentos ficticios)."""

from dataclasses import replace

import pytest

from auditoria import catalogos
from auditoria.db.repositorios import RepositorioTrazabilidad
from auditoria.documentos import clasificador, inventario, ocr
from pruebas import generadores


def _cargar(sesion, config, ids, contenido, nombre="cuenta.pdf"):
    usuario_id, auditoria_id = ids
    inventario.cargar_archivo(sesion, config, auditoria_id, usuario_id, nombre, contenido)
    sesion.commit()
    return inventario.listar_documentos(sesion, auditoria_id, con_paginas=True)[-1]


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("FORMULARIO UNICO DE RECLAMACION FURIPS datos del accidente de transito", "FURIPS"),
        ("FACTURA ELECTRÓNICA DE VENTA CUFE 123 valor total", "Factura"),
        ("EPICRISIS resumen de egreso condición de salida", "Epicrisis"),
        ("DESCRIPCIÓN QUIRÚRGICA cirujano anestesiólogo incisión", "Descripción quirúrgica"),
        ("Informe radiológico: radiografía de rodilla, proyecciones AP y lateral", "Informes radiológicos"),
    ],
)
def test_clasificacion_por_palabras_clave(texto, esperado):
    tipo, confianza, _ = clasificador.clasificar_texto(texto)
    assert tipo == esperado
    assert confianza in ("alta", "media", "baja")


def test_texto_sin_coincidencias_se_propone_otros_con_confianza_baja():
    tipo, confianza, _ = clasificador.clasificar_texto("Texto ficticio sin relación con ningún tipo documental.")
    assert (tipo, confianza) == ("Otros", "baja")


def test_pagina_sin_texto_no_se_clasifica():
    assert clasificador.clasificar_texto("") == (None, None, {})


def test_carga_propone_tipos_sin_confirmarlos(sesion, config_temporal, usuario_y_auditoria):
    documento = _cargar(sesion, config_temporal, usuario_y_auditoria, generadores.pdf_concatenado())
    tipos = [p.tipo_propuesto for p in documento.paginas]

    assert tipos == ["FURIPS", "Factura", "Informes radiológicos", "Epicrisis"]
    assert all(p.tipo_confirmado is None for p in documento.paginas)  # Nunca se confirma solo


def test_auditor_corrige_clasificacion_y_queda_trazabilidad(sesion, config_temporal, usuario_y_auditoria):
    usuario_id, auditoria_id = usuario_y_auditoria
    documento = _cargar(sesion, config_temporal, usuario_y_auditoria, generadores.pdf_concatenado())
    pagina = documento.paginas[0]

    clasificador.confirmar_clasificacion(sesion, pagina.id, "Historia clínica", usuario_id)
    sesion.commit()

    assert pagina.tipo_confirmado == "Historia clínica"
    assert pagina.tipo_propuesto == "FURIPS"  # La propuesta original se conserva
    assert pagina.usuario_clasificacion_id == usuario_id and pagina.fecha_clasificacion
    acciones = [r.accion for r in RepositorioTrazabilidad(sesion).listar_por_auditoria(auditoria_id)]
    assert "clasificacion_corregida" in acciones


def test_tipo_desconocido_se_rechaza(sesion, config_temporal, usuario_y_auditoria):
    documento = _cargar(sesion, config_temporal, usuario_y_auditoria, generadores.pdf_concatenado())
    with pytest.raises(clasificador.ErrorClasificacion):
        clasificador.confirmar_clasificacion(sesion, documento.paginas[0].id, "Tipo inventado", usuario_y_auditoria[0])


def test_reclasificar_respeta_lo_confirmado(sesion, config_temporal, usuario_y_auditoria):
    usuario_id, auditoria_id = usuario_y_auditoria
    documento = _cargar(sesion, config_temporal, usuario_y_auditoria, generadores.pdf_concatenado())
    clasificador.confirmar_clasificacion(sesion, documento.paginas[1].id, "Otros", usuario_id)
    clasificador.reclasificar_auditoria(sesion, auditoria_id, usuario_id)
    sesion.commit()
    assert documento.paginas[1].tipo_efectivo == "Otros"


def test_secciones_agrupan_paginas_consecutivas_y_marcan_dudosas(sesion, config_temporal, usuario_y_auditoria):
    contenido = generadores.pdf_con_paginas(
        [
            "HISTORIA CLINICA anamnesis antecedentes examen fisico",
            "HISTORIA CLINICA enfermedad actual motivo de consulta",
            None,
            "EPICRISIS resumen de egreso condicion de salida",
        ]
    )
    documento = _cargar(sesion, config_temporal, usuario_y_auditoria, contenido)
    secciones = clasificador.agrupar_secciones(documento.paginas)

    assert [(s.tipo, s.paginas) for s in secciones] == [
        ("Historia clínica", [1, 2]),
        ("Sin clasificar (sin texto)", [3]),
        ("Epicrisis", [4]),
    ]
    assert all(s.dudosa for s in secciones)  # Todas limitan con la página sin texto


def test_marcar_pagina_ilegible(sesion, config_temporal, usuario_y_auditoria):
    documento = _cargar(sesion, config_temporal, usuario_y_auditoria, generadores.pdf_con_texto())
    clasificador.marcar_legibilidad(sesion, documento.paginas[0].id, catalogos.NO_LEGIBLE, usuario_y_auditoria[0])
    sesion.commit()
    assert documento.paginas[0].legibilidad == catalogos.NO_LEGIBLE


def test_sin_ocr_la_app_sigue_y_marca_pendiente(sesion, config_temporal, usuario_y_auditoria):
    documento = _cargar(sesion, config_temporal, usuario_y_auditoria, generadores.pdf_con_pagina_en_blanco_e_imagen())
    assert not ocr.estado_ocr(config_temporal).disponible
    assert [p.metodo_texto for p in documento.paginas] == ["Texto PDF", "Sin texto", "Sin texto"]
    assert documento.estado == catalogos.PROC_REQUIERE_REVISION


def test_tesseract_configurado_pero_no_instalado(config_temporal, monkeypatch):
    monkeypatch.setattr(ocr.shutil, "which", lambda _: None)
    monkeypatch.setattr(ocr, "RUTAS_HABITUALES_WINDOWS", ())
    ocr._detectar_tesseract.cache_clear()
    config = replace(config_temporal, motor_ocr="tesseract", ruta_tesseract="C:/no/existe/tesseract.exe")
    estado = ocr.estado_ocr(config)
    ocr._detectar_tesseract.cache_clear()
    assert not estado.disponible
    assert "no está instalado" in estado.mensaje


def test_ocr_simulado_completa_texto_de_paginas_escaneadas(sesion, config_temporal, usuario_y_auditoria, monkeypatch):
    """Simula Tesseract (sin instalarlo) para comprobar el flujo de OCR."""
    monkeypatch.setattr(ocr, "estado_ocr", lambda _config: ocr.EstadoOCR(True, "tesseract", "simulado", "tesseract"))
    monkeypatch.setattr(
        ocr, "ocr_imagen", lambda _estado, _png: "INFORME RADIOLOGICO texto ficticio reconocido por OCR simulado con radiografia"
    )
    documento = _cargar(sesion, config_temporal, usuario_y_auditoria, generadores.pdf_con_pagina_en_blanco_e_imagen())

    assert [p.metodo_texto for p in documento.paginas] == ["Texto PDF", "OCR", "OCR"]
    assert not any(p.requiere_analisis_visual for p in documento.paginas)
    assert documento.paginas[2].tipo_propuesto == "Informes radiológicos"
    assert documento.estado == catalogos.PROC_PROCESADO
