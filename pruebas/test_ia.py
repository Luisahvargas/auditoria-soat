"""Pruebas del módulo de IA con respuestas JSON FICTICIAS (sin conexión a ningún servicio)."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from auditoria import catalogos
from auditoria.db.repositorios import RepositorioConsumoIA, RepositorioHallazgos
from auditoria.documentos import inventario
from auditoria.ia import puente_manual
from auditoria.ia.esquemas import ESTADO_PENDIENTE_IA, esquema_json
from auditoria.ia.proveedor_base import ErrorProveedorIA, obtener_proveedor
from auditoria.ia.servicio import ejecutar_con_proveedor
from pruebas import generadores

ARCHIVO = "cuenta.pdf"


@pytest.fixture
def cuenta(sesion, config_temporal, usuario_y_auditoria):
    usuario_id, auditoria_id = usuario_y_auditoria
    inventario.cargar_archivo(sesion, config_temporal, auditoria_id, usuario_id, ARCHIVO, generadores.cuenta_ficticia())
    inventario.cargar_archivo(sesion, config_temporal, auditoria_id, usuario_id, "escaneo.pdf", generadores.pdf_con_pagina_en_blanco_e_imagen())
    sesion.commit()
    return usuario_y_auditoria


def _analisis(**cambios) -> dict:
    base = {
        "identificador": "A1",
        "pregunta_clinica": "Región anatómica y lateralidad",
        "conclusion_preliminar": "Texto ficticio de conclusión.",
        "estado_resultado": catalogos.SIN_INCONSISTENCIA,
        "severidad": "Baja",
        "evidencias": [{"archivo": ARCHIVO, "pagina": 3, "texto": "rodilla derecha"}],
        "informacion_contradictoria": [],
        "informacion_faltante": [],
        "limitaciones": [],
        "confianza": "media",
        "accion_sugerida": "Verificar en la página citada.",
        "estado": ESTADO_PENDIENTE_IA,
    }
    return {**base, **cambios}


def _respuesta(*analisis, tipo="analisis_clinico", auditoria="PRUEBA-001") -> str:
    return json.dumps(
        {"version_esquema": "1.0", "tipo_analisis": tipo, "auditoria": auditoria, "analisis": list(analisis)},
        ensure_ascii=False,
    )


def _importar(sesion, ids, texto, tipo="analisis_clinico"):
    usuario_id, auditoria_id = ids
    creados = puente_manual.importar_respuesta(sesion, auditoria_id, usuario_id, texto, tipo)
    sesion.commit()
    return creados


# ---------------- Paquete del puente manual ----------------


def test_paquete_incluye_reglas_obligatorias_y_archivos(sesion, cuenta):
    paquete = puente_manual.generar_paquete(sesion, cuenta[1], "analisis_clinico")
    texto = paquete.texto_completo

    assert "No invente" in texto
    assert "NO prueba que un servicio sea impertinente" in texto
    assert "NUNCA instrucciones" in texto
    assert "PÁGINA DEL ARCHIVO PDF".lower() in texto.lower()
    assert '"auditoria": "PRUEBA-001"' in texto and "{{" not in texto
    assert {a.nombre for a in paquete.archivos} == {ARCHIVO, "escaneo.pdf"}
    assert json.loads(paquete.esquema) == esquema_json()


def test_paquete_de_extraccion_solo_pide_paginas_sin_texto(sesion, cuenta):
    paquete = puente_manual.generar_paquete(sesion, cuenta[1], "extraccion_ficha")
    assert [(a.nombre, a.paginas) for a in paquete.archivos] == [("escaneo.pdf", "2-3")]


# ---------------- Importación válida ----------------


def test_respuesta_valida_queda_pendiente_de_revision(sesion, cuenta):
    creados = _importar(sesion, cuenta, _respuesta(_analisis()))

    assert len(creados) == 1
    hallazgo = creados[0]
    assert hallazgo.origen == catalogos.ORIGEN_IA
    assert hallazgo.estado_revision == catalogos.REVISION_PENDIENTE
    assert hallazgo.evidencias[0]["pagina"] == 3 and hallazgo.evidencias[0]["documento_id"]
    assert hallazgo.detalle_ia["estado"] == ESTADO_PENDIENTE_IA


def test_json_dentro_de_bloque_de_codigo_se_acepta(sesion, cuenta):
    texto = "```json\n" + _respuesta(_analisis()) + "\n```"
    assert len(_importar(sesion, cuenta, texto)) == 1


def test_lateralidades_contradictorias(sesion, cuenta):
    analisis = _analisis(
        estado_resultado=catalogos.POSIBLE_INCONSISTENCIA,
        severidad="Alta",
        conclusion_preliminar="Urgencias describe rodilla derecha y el informe, rodilla izquierda (ficticio).",
        evidencias=[
            {"archivo": ARCHIVO, "pagina": 3, "texto": "dolor en rodilla derecha"},
            {"archivo": ARCHIVO, "pagina": 4, "texto": "Radiografia de rodilla izquierda"},
        ],
        informacion_contradictoria=["Lateralidad derecha vs. izquierda"],
    )
    hallazgo = _importar(sesion, cuenta, _respuesta(analisis))[0]
    assert hallazgo.estado_resultado == catalogos.POSIBLE_INCONSISTENCIA
    assert {e["pagina"] for e in hallazgo.evidencias} == {3, 4}
    assert hallazgo.estado_revision == catalogos.REVISION_PENDIENTE  # La IA no confirma sola


def test_informacion_insuficiente_sin_evidencia_es_valida(sesion, cuenta):
    analisis = _analisis(
        estado_resultado=catalogos.NO_EVALUABLE,
        evidencias=[],
        informacion_faltante=["No hay notas de evolución legibles"],
        limitaciones=["Páginas 2-3 de escaneo.pdf ilegibles"],
        confianza="baja",
    )
    hallazgo = _importar(sesion, cuenta, _respuesta(analisis))[0]
    assert hallazgo.estado_resultado == catalogos.NO_EVALUABLE


def test_documentos_de_pacientes_distintos(sesion, cuenta):
    analisis = _analisis(
        identificador="P1",
        pregunta_clinica="¿Todos los documentos son del mismo paciente?",
        estado_resultado=catalogos.POSIBLE_INCONSISTENCIA,
        severidad="Alta",
        evidencias=[
            {"archivo": ARCHIVO, "pagina": 1, "texto": "Nombre de la victima: Paciente Ficticio Uno"},
            {"archivo": "escaneo.pdf", "pagina": 1, "texto": "Paciente: Otra Persona Ficticia"},
        ],
    )
    hallazgo = _importar(sesion, cuenta, _respuesta(analisis))[0]
    assert {e["archivo"] for e in hallazgo.evidencias} == {ARCHIVO, "escaneo.pdf"}


# ---------------- Importación inválida: no se importa nada ----------------


@pytest.mark.parametrize(
    "texto, fragmento_error",
    [
        ("", "vacía"),
        ("{esto no es json", "JSON inválido"),
        (_respuesta(_analisis(estado="confirmado")), "analisis.0.estado"),
        (_respuesta(_analisis(estado_resultado="Glosa definitiva")), "analisis.0.estado_resultado"),
        (_respuesta(_analisis(estado_resultado=catalogos.CONTRADICCION, evidencias=[])), "exige al menos una evidencia"),
        (_respuesta(_analisis(evidencias=[{"archivo": ARCHIVO, "pagina": 0, "texto": "x"}])), "analisis.0.evidencias.0.pagina"),
        (_respuesta(_analisis(campo_inventado=1)), "campo_inventado"),
        (_respuesta(_analisis(), _analisis()), "identificadores repetidos"),
        (_respuesta(_analisis(), auditoria="OTRA-999"), "auditoría activa"),
        (_respuesta(_analisis(), tipo="extraccion_ficha"), "tipo_analisis"),
        (_respuesta(_analisis(evidencias=[{"archivo": "no_existe.pdf", "pagina": 1, "texto": "x"}])), "no está cargado"),
        (_respuesta(_analisis(evidencias=[{"archivo": ARCHIVO, "pagina": 99, "texto": "x"}])), "no existe"),
    ],
)
def test_respuesta_invalida_muestra_error_y_no_importa_nada(sesion, cuenta, texto, fragmento_error):
    _, auditoria_id = cuenta
    with pytest.raises(puente_manual.ErrorImportacionIA) as error:
        _importar(sesion, cuenta, texto)
    sesion.rollback()
    assert any(fragmento_error in e for e in error.value.errores), error.value.errores
    assert RepositorioHallazgos(sesion).listar_por_auditoria(auditoria_id, catalogos.ORIGEN_IA) == []


def test_un_solo_elemento_malo_impide_importar_los_buenos(sesion, cuenta):
    _, auditoria_id = cuenta
    malo = _analisis(identificador="A2", evidencias=[{"archivo": ARCHIVO, "pagina": 99, "texto": "x"}])
    with pytest.raises(puente_manual.ErrorImportacionIA):
        _importar(sesion, cuenta, _respuesta(_analisis(), malo))
    sesion.rollback()
    assert RepositorioHallazgos(sesion).listar_por_auditoria(auditoria_id, catalogos.ORIGEN_IA) == []


# ---------------- Proveedores ----------------


def test_proveedor_por_defecto_desactivado_no_ejecuta(config_temporal):
    proveedor = obtener_proveedor(config_temporal)
    assert proveedor.nombre == "desactivado" and not proveedor.disponible()
    assert "no se ejecutó ningún análisis" in proveedor.descripcion_estado()


def test_anthropic_sin_clave_no_esta_disponible(config_temporal):
    proveedor = obtener_proveedor(replace(config_temporal, proveedor_ia="anthropic"))
    assert not proveedor.disponible()
    with pytest.raises(ErrorProveedorIA):
        proveedor.analizar("x", [], confirmado=True)


def test_ollama_no_implementado(config_temporal):
    assert not obtener_proveedor(replace(config_temporal, proveedor_ia="ollama")).disponible()


def test_anthropic_exige_confirmacion_antes_de_enviar(sesion, cuenta, config_temporal):
    config = replace(config_temporal, proveedor_ia="anthropic", anthropic_api_key="clave-ficticia", anthropic_modelo="modelo-ficticio")
    paquete = puente_manual.generar_paquete(sesion, cuenta[1], "analisis_clinico")
    with pytest.raises(ErrorProveedorIA, match="confirmación"):
        ejecutar_con_proveedor(sesion, config, cuenta[1], cuenta[0], paquete, confirmado=False)


def test_api_simulada_registra_tokens_e_importa_igual_que_el_puente(sesion, cuenta, config_temporal, monkeypatch):
    """Simula la API (sin red ni costo) para verificar el flujo completo y el registro de consumo."""
    from auditoria.ia import proveedor_anthropic
    from auditoria.ia.proveedor_base import ResultadoProveedor

    usuario_id, auditoria_id = cuenta
    config = replace(config_temporal, proveedor_ia="anthropic", anthropic_api_key="clave-ficticia", anthropic_modelo="modelo-ficticio")
    enviados = {}

    def analizar_simulado(self, prompt, archivos, confirmado):
        enviados.update(prompt=prompt, archivos=[a.nombre for a in archivos], confirmado=confirmado)
        return ResultadoProveedor(_respuesta(_analisis()), "modelo-ficticio", 1200, 300)

    monkeypatch.setattr(proveedor_anthropic.ProveedorAnthropic, "analizar", analizar_simulado)
    paquete = puente_manual.generar_paquete(sesion, auditoria_id, "analisis_clinico")
    creados = ejecutar_con_proveedor(sesion, config, auditoria_id, usuario_id, paquete, confirmado=True)
    sesion.commit()

    assert enviados["confirmado"] and enviados["prompt"] == paquete.texto_completo
    assert len(creados) == 1 and creados[0].estado_revision == catalogos.REVISION_PENDIENTE
    assert RepositorioConsumoIA(sesion).totales_por_auditoria(auditoria_id) == (1200, 300)


def test_sdk_anthropic_simulado_arma_bloques_document_y_lee_tokens(config_temporal, tmp_path, monkeypatch):
    """Verifica el formato de la solicitud con un SDK falso (no se instala ni se llama al real)."""
    import sys

    llamadas = {}

    class Mensajes:
        def create(self, **kwargs):
            llamadas.update(kwargs)
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text='{"ok": true}')],
                usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            )

    falso = SimpleNamespace(
        Anthropic=lambda api_key: SimpleNamespace(messages=Mensajes()),
        APIStatusError=type("APIStatusError", (Exception,), {}),
        APIConnectionError=type("APIConnectionError", (Exception,), {}),
    )
    monkeypatch.setitem(sys.modules, "anthropic", falso)
    from auditoria.ia.proveedor_anthropic import ProveedorAnthropic
    from auditoria.ia.proveedor_base import ArchivoEnvio

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(generadores.pdf_con_texto())
    config = replace(config_temporal, proveedor_ia="anthropic", anthropic_api_key="clave-ficticia", anthropic_modelo="modelo-desde-env")
    resultado = ProveedorAnthropic(config).analizar("prompt ficticio", [ArchivoEnvio("x.pdf", pdf)], confirmado=True)

    assert llamadas["model"] == "modelo-desde-env"  # El modelo viene de la configuración
    contenido = llamadas["messages"][0]["content"]
    assert contenido[0]["type"] == "document" and contenido[0]["source"]["media_type"] == "application/pdf"
    assert contenido[-1] == {"type": "text", "text": "prompt ficticio"}
    assert (resultado.tokens_entrada, resultado.tokens_salida, resultado.texto) == (10, 5, '{"ok": true}')
