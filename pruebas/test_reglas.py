"""Pruebas del motor de reglas con cuentas FICTICIAS: casos positivos, negativos y sin información."""

import pytest
import yaml

from auditoria import catalogos
from auditoria.documentos import clasificador, inventario
from auditoria.extraccion import ficha
from auditoria.hallazgos import servicio as servicio_hallazgos
from auditoria.reglas import definiciones, perfiles
from auditoria.reglas.contexto import ContextoAuditoria
from auditoria.reglas.definiciones import ErrorReglas, cargar_reglas
from auditoria.reglas.motor import ejecutar_reglas, evaluar
from pruebas import generadores


def _auditar(sesion, config, ids, paginas=None, **cambios):
    """Carga una cuenta ficticia, ejecuta las reglas y devuelve {regla_id: [hallazgos]}."""
    usuario_id, auditoria_id = ids
    contenido = generadores.pdf_con_paginas(paginas) if paginas is not None else generadores.cuenta_ficticia(**cambios)
    inventario.cargar_archivo(sesion, config, auditoria_id, usuario_id, "cuenta.pdf", contenido)
    ejecutar_reglas(sesion, auditoria_id, usuario_id)
    sesion.commit()
    por_regla = {}
    for h in servicio_hallazgos.listar(sesion, auditoria_id, servicio_hallazgos.Filtros(solo_atencion=False)):
        por_regla.setdefault(h.regla_id, []).append(h)
    return por_regla


def _estados(por_regla, regla_id):
    return {h.estado_resultado for h in por_regla.get(regla_id, [])}


# ---------------- Configuración ----------------


def test_las_21_reglas_cargan_y_tienen_referencia_pendiente():
    reglas = cargar_reglas()
    assert [r.id for r in reglas] == [f"R{i:02d}" for i in range(1, 22)]
    # Principio 7: no se inventan referencias normativas.
    assert all(r.referencia_normativa == catalogos.PENDIENTE_VALIDACION for r in reglas)


def test_regla_con_funcion_inexistente_se_rechaza(tmp_path):
    regla = {
        "id": "X1", "nombre": "x", "descripcion": "x", "categoria": "x", "funcion": "no_existe",
        "evidencia_necesaria": "x", "severidad": "Alta", "resultado_esperado": "x", "explicacion": "x",
        "aplicabilidad": "x", "version": "1",
    }
    (tmp_path / "r.yaml").write_text(yaml.safe_dump({"reglas": [regla]}), encoding="utf-8")
    with pytest.raises(ErrorReglas, match="no_existe"):
        definiciones.cargar_reglas(tmp_path)


def test_regla_con_severidad_invalida_se_rechaza(tmp_path):
    regla = {
        "id": "X1", "nombre": "x", "descripcion": "x", "categoria": "x", "funcion": "duplicados",
        "evidencia_necesaria": "x", "severidad": "Gravísima", "resultado_esperado": "x", "explicacion": "x",
        "aplicabilidad": "x", "version": "1",
    }
    (tmp_path / "r.yaml").write_text(yaml.safe_dump({"reglas": [regla]}), encoding="utf-8")
    with pytest.raises(ErrorReglas, match="severidad"):
        definiciones.cargar_reglas(tmp_path)


def test_perfil_desactiva_y_ajusta_reglas_sin_duplicar_codigo():
    reglas = cargar_reglas()
    efectivas = {r.id: r for r in perfiles.aplicar_perfil(reglas, perfiles.cargar_perfil("ejemplo_aseguradora"))}
    assert "R18" not in efectivas
    assert efectivas["R13"].severidad == "Alta"
    assert efectivas["R13"].parametros["umbral_dias_revision"] == 5
    assert "generica" in perfiles.listar_perfiles()


def test_perfil_con_regla_inexistente_se_rechaza():
    perfil = perfiles.Perfil(id="malo", nombre="Malo", reglas_desactivadas=["R99"])
    with pytest.raises(ErrorReglas, match="R99"):
        perfiles.aplicar_perfil(cargar_reglas(), perfil)


# ---------------- Casos negativos (cuenta coherente) ----------------


def test_cuenta_coherente_sin_inconsistencias_en_datos_clave(sesion, config_temporal, usuario_y_auditoria):
    r = _auditar(sesion, config_temporal, usuario_y_auditoria)
    for regla_id in ("R01", "R02", "R03", "R04", "R05", "R06", "R07", "R09", "R10", "R11", "R14", "R19"):
        assert catalogos.CONTRADICCION not in _estados(r, regla_id), regla_id
        assert catalogos.POSIBLE_INCONSISTENCIA not in _estados(r, regla_id), regla_id
    assert _estados(r, "R03") == {catalogos.SIN_INCONSISTENCIA}
    assert _estados(r, "R11") == {catalogos.SIN_INCONSISTENCIA}


# ---------------- Casos positivos ----------------


@pytest.mark.parametrize(
    "regla_id, cambios",
    [
        ("R01", {"id_factura": "7654321"}),
        ("R02", {"nacimiento_urgencias": "15/05/1991"}),
        ("R03", {"edad_urgencias": "40"}),
        ("R04", {"accidente_epicrisis": "11/01/2025"}),
        ("R05", {"factura": "FE-2002"}),
        ("R06", {"poliza_soporte": "9999999999"}),
        ("R06", {"accidente_furips": "10/07/2025", "accidente_epicrisis": "10/07/2025", "ingreso": "10/07/2025", "egreso": "12/07/2025"}),
        ("R07", {"placa_poliza": "XYZ987"}),
        ("R08", {"propietario_poliza": "1111111"}),
        ("R09", {"nombre_factura": "Persona Totalmente Distinta"}),
        ("R10", {"ingreso": "09/01/2025"}),
        ("R10", {"egreso": "08/01/2025"}),
        ("R11", {"lado_informe": "izquierda"}),
        ("R13", {"egreso": "20/01/2025"}),
        ("R14", {"material_cirugia": "clavo endomedular"}),
    ],
)
def test_cada_regla_detecta_su_inconsistencia(sesion, config_temporal, usuario_y_auditoria, regla_id, cambios):
    r = _auditar(sesion, config_temporal, usuario_y_auditoria, **cambios)
    assert _estados(r, regla_id) & {catalogos.POSIBLE_INCONSISTENCIA, catalogos.CONTRADICCION}, (regla_id, _estados(r, regla_id))


def test_hallazgo_conserva_regla_y_evidencias_con_archivo_y_pagina(sesion, config_temporal, usuario_y_auditoria):
    r = _auditar(sesion, config_temporal, usuario_y_auditoria, lado_informe="izquierda")
    hallazgo = next(h for h in r["R11"] if h.estado_resultado == catalogos.POSIBLE_INCONSISTENCIA)

    assert hallazgo.origen == catalogos.ORIGEN_REGLA and hallazgo.regla_version == "1.0"
    assert hallazgo.estado_revision == catalogos.REVISION_PENDIENTE
    paginas = {e["pagina"] for e in hallazgo.evidencias}
    assert {3, 4} <= paginas  # Urgencias (derecha) e informe (izquierda)
    assert all(e["archivo"] == "cuenta.pdf" and e["texto"] for e in hallazgo.evidencias)


def test_diferencia_validada_por_auditor_es_contradiccion(sesion, config_temporal, usuario_y_auditoria):
    usuario_id, auditoria_id = usuario_y_auditoria
    _auditar(sesion, config_temporal, usuario_y_auditoria, placa_poliza="XYZ987")
    for estado in ficha.construir_ficha(sesion, auditoria_id)["accidente"]:
        if estado.campo.id == "accidente.placa":
            for valor in estado.valores:
                for dato in valor.datos:
                    ficha.validar_dato(sesion, dato.id, usuario_id)
    ejecutar_reglas(sesion, auditoria_id, usuario_id)
    sesion.commit()
    r07 = [h for h in servicio_hallazgos.listar(sesion, auditoria_id) if h.regla_id == "R07"]
    assert any(h.estado_resultado == catalogos.CONTRADICCION for h in r07)


# ---------------- Sin información suficiente ----------------


def test_sin_documentos_las_reglas_no_inventan(sesion, usuario_y_auditoria):
    usuario_id, auditoria_id = usuario_y_auditoria
    ejecutar_reglas(sesion, auditoria_id, usuario_id)
    sesion.commit()
    hallazgos = servicio_hallazgos.listar(sesion, auditoria_id, servicio_hallazgos.Filtros(solo_atencion=False))
    estados = {h.estado_resultado for h in hallazgos}
    assert catalogos.CONTRADICCION not in estados and catalogos.POSIBLE_INCONSISTENCIA not in estados
    # Lo único que requiere atención son los datos clave no encontrados (R17), nunca glosas.
    atencion = servicio_hallazgos.listar(sesion, auditoria_id)
    assert atencion and all(h.regla_id == "R17" and h.estado_resultado == catalogos.FALTANTE for h in atencion)
    assert all("no demuestra" in h.explicacion for h in atencion)


def test_ayuda_diagnostica_sin_soporte_es_faltante_no_impertinente(sesion, config_temporal, usuario_y_auditoria):
    r = _auditar(
        sesion,
        config_temporal,
        usuario_y_auditoria,
        paginas=[
            "INFORME RADIOLOGICO\nTomografia de craneo simple\nHallazgos: sin lesiones ficticias",
            "HISTORIA CLINICA\nanamnesis antecedentes examen fisico\nMotivo de consulta: dolor ficticio",
        ],
    )
    hallazgo = next(h for h in r["R12"] if h.estado_resultado == catalogos.FALTANTE)
    assert "no demuestra" in hallazgo.explicacion.lower()


def test_paginas_sin_texto_e_ilegibles(sesion, config_temporal, usuario_y_auditoria):
    usuario_id, auditoria_id = usuario_y_auditoria
    inventario.cargar_archivo(sesion, config_temporal, auditoria_id, usuario_id, "m.pdf", generadores.pdf_con_pagina_en_blanco_e_imagen())
    documento = inventario.listar_documentos(sesion, auditoria_id, con_paginas=True)[0]
    clasificador.marcar_legibilidad(sesion, documento.paginas[0].id, catalogos.NO_LEGIBLE, usuario_id)
    ejecutar_reglas(sesion, auditoria_id, usuario_id)
    sesion.commit()
    r16 = [h for h in servicio_hallazgos.listar(sesion, auditoria_id, servicio_hallazgos.Filtros(solo_atencion=False)) if h.regla_id == "R16"]
    assert {h.estado_resultado for h in r16} == {catalogos.ILEGIBLE, catalogos.NO_EVALUABLE}


def test_duplicado_de_pagina(sesion, config_temporal, usuario_y_auditoria):
    texto = "EPICRISIS\nResumen de egreso ficticio con suficiente texto para considerarse una pagina completa de prueba."
    r = _auditar(sesion, config_temporal, usuario_y_auditoria, paginas=[texto, "OTRA PAGINA ficticia distinta con texto", texto])
    assert catalogos.POSIBLE_INCONSISTENCIA in _estados(r, "R19")


def test_correccion_del_auditor_genera_r20(sesion, config_temporal, usuario_y_auditoria):
    usuario_id, auditoria_id = usuario_y_auditoria
    _auditar(sesion, config_temporal, usuario_y_auditoria)
    dato = ficha.construir_ficha(sesion, auditoria_id)["accidente"][0].valores[0].datos[0]
    ficha.corregir_dato(sesion, dato.id, "11/01/2025", usuario_id)
    ejecutar_reglas(sesion, auditoria_id, usuario_id)
    sesion.commit()
    r20 = [h for h in servicio_hallazgos.listar(sesion, auditoria_id) if h.regla_id == "R20"]
    assert r20 and r20[0].estado_resultado == catalogos.POSIBLE_INCONSISTENCIA


def test_xml_rips_pendiente_es_no_evaluable(sesion, config_temporal, usuario_y_auditoria):
    usuario_id, auditoria_id = usuario_y_auditoria
    inventario.cargar_archivo(sesion, config_temporal, auditoria_id, usuario_id, "f.xml", b"<ficticio/>")
    r = _auditar(sesion, config_temporal, usuario_y_auditoria)
    assert _estados(r, "R21") == {catalogos.NO_EVALUABLE}


def test_regla_que_falla_no_detiene_las_demas(sesion, config_temporal, usuario_y_auditoria, monkeypatch):
    from auditoria.reglas import verificaciones

    def falla(_ctx, _regla):
        raise RuntimeError("error simulado")

    monkeypatch.setitem(verificaciones.VERIFICACIONES, "duplicados", falla)
    ctx = ContextoAuditoria.desde_base(sesion, usuario_y_auditoria[1])
    resultados = evaluar(ctx, cargar_reglas())
    r19 = [r for regla, r in resultados if regla.id == "R19"]
    assert r19[0].estado == catalogos.NO_EVALUABLE
    assert len({regla.id for regla, _ in resultados}) == 21


# ---------------- Revisión humana y re-ejecución ----------------


def test_reejecutar_conserva_revisiones_y_no_duplica(sesion, config_temporal, usuario_y_auditoria):
    usuario_id, auditoria_id = usuario_y_auditoria
    r = _auditar(sesion, config_temporal, usuario_y_auditoria, lado_informe="izquierda")
    hallazgo = next(h for h in r["R11"] if h.estado_resultado == catalogos.POSIBLE_INCONSISTENCIA)
    servicio_hallazgos.revisar(sesion, hallazgo.id, usuario_id, catalogos.REVISION_DESCARTADO, "Lesión bilateral ficticia")
    sesion.commit()
    total_antes = len(servicio_hallazgos.listar(sesion, auditoria_id, servicio_hallazgos.Filtros(solo_atencion=False)))

    ejecutar_reglas(sesion, auditoria_id, usuario_id)
    sesion.commit()
    todos = servicio_hallazgos.listar(sesion, auditoria_id, servicio_hallazgos.Filtros(solo_atencion=False))
    assert len(todos) == total_antes
    conservado = next(h for h in todos if h.id == hallazgo.id)
    assert conservado.estado_revision == catalogos.REVISION_DESCARTADO
    assert conservado.comentario_auditor == "Lesión bilateral ficticia"


def test_revision_exige_comentario_y_estado(sesion, config_temporal, usuario_y_auditoria):
    usuario_id, _ = usuario_y_auditoria
    r = _auditar(sesion, config_temporal, usuario_y_auditoria, placa_poliza="XYZ987")
    hallazgo = next(h for h in r["R07"] if h.estado_resultado == catalogos.POSIBLE_INCONSISTENCIA)
    with pytest.raises(servicio_hallazgos.ErrorHallazgo):
        servicio_hallazgos.revisar(sesion, hallazgo.id, usuario_id, catalogos.REVISION_DESCARTADO, "")
    with pytest.raises(servicio_hallazgos.ErrorHallazgo):
        servicio_hallazgos.revisar(sesion, hallazgo.id, usuario_id, catalogos.REVISION_MODIFICADO, "x", "Estado inventado")

    servicio_hallazgos.revisar(sesion, hallazgo.id, usuario_id, catalogos.REVISION_MODIFICADO, "Leído en original", catalogos.CONTRADICCION)
    sesion.commit()
    assert hallazgo.estado_final == catalogos.CONTRADICCION
    assert hallazgo.estado_resultado == catalogos.POSIBLE_INCONSISTENCIA  # Se conserva el resultado de la regla
    assert hallazgo.usuario_revision_id == usuario_id and hallazgo.fecha_revision


def test_filtro_por_defecto_solo_muestra_lo_que_requiere_atencion(sesion, config_temporal, usuario_y_auditoria):
    _, auditoria_id = usuario_y_auditoria
    _auditar(sesion, config_temporal, usuario_y_auditoria)
    visibles = servicio_hallazgos.listar(sesion, auditoria_id)
    todos = servicio_hallazgos.listar(sesion, auditoria_id, servicio_hallazgos.Filtros(solo_atencion=False))
    assert all(h.estado_final in catalogos.ESTADOS_QUE_REQUIEREN_ATENCION for h in visibles)
    assert len(todos) > len(visibles)
