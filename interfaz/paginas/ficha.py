"""Ficha de datos generales (ficha maestra) de la cuenta."""

import streamlit as st

from auditoria.documentos import inventario
from auditoria.extraccion import ficha as servicio_ficha
from auditoria.extraccion.extractor import cargar_definicion
from interfaz.estado import auditoria_finalizada, ir_a_pagina, requerir_auditoria
from interfaz.recursos import obtener_fabrica_sesiones


def mostrar() -> None:
    st.title("Ficha de datos generales")
    usuario, auditoria = requerir_auditoria()
    fabrica = obtener_fabrica_sesiones()
    finalizada = auditoria_finalizada()

    st.caption(
        "Cada dato muestra de dónde salió (archivo y página). Si dos documentos no coinciden se conservan "
        "ambos valores y se marca ⚠️. Ninguna fuente se asume correcta por sí sola, tampoco el FURIPS."
    )
    st.info(
        "Los datos de facturación del XML y los RIPS tendrán prioridad cuando exista su lector "
        "(Fase 5, pendiente de ejemplos reales). Por ahora la ficha se arma con el texto de los PDF y lo que usted registre."
    )

    if not finalizada and st.button("Extraer datos de los documentos", type="primary"):
        with fabrica() as sesion:
            creados = servicio_ficha.extraer_auditoria(sesion, auditoria["id"], usuario["id"])
            sesion.commit()
        st.toast(f"Extracción terminada: {creados} dato(s) nuevo(s). Lo validado o corregido por usted se conserva.")
        st.rerun()

    with fabrica() as sesion:
        ficha = servicio_ficha.construir_ficha(sesion, auditoria["id"])
        documentos = {d.id: d for d in inventario.listar_documentos(sesion, auditoria["id"])}

    edad = servicio_ficha.edad_al_accidente(ficha)
    st.metric("Edad a la fecha del accidente (calculada)", f"{edad.valor} años" if edad.valor is not None else "No evaluable")
    st.caption(edad.explicacion)

    definicion = cargar_definicion()
    for bloque, estados in ficha.items():
        st.subheader(definicion.bloques[bloque])
        st.dataframe(
            [
                {
                    "Campo": e.campo.etiqueta,
                    "Valor(es)": " | ".join(v.mostrar for v in e.valores) or "—",
                    "Fuentes": sum(len(v.datos) for v in e.valores),
                    "Estado": "—  Sin dato" if e.sin_dato else ("⚠️ Valores distintos" if e.discrepancia else "✅"),
                }
                for e in estados
            ],
            hide_index=True,
            width="stretch",
        )

    st.divider()
    _detalle_y_validacion(ficha, documentos, usuario, auditoria, finalizada)
    if not finalizada:
        _dato_manual(definicion, documentos, usuario, auditoria)


def _detalle_y_validacion(ficha, documentos, usuario, auditoria, finalizada) -> None:
    st.subheader("Detalle de un campo y validación")
    estados = {e.campo.id: e for lista in ficha.values() for e in lista}
    con_datos = [campo_id for campo_id, e in estados.items() if not e.sin_dato]
    if not con_datos:
        st.info("Aún no hay datos. Pulse **Extraer datos de los documentos** o regístrelos manualmente.")
        return

    campo_id = st.selectbox(
        "Campo",
        con_datos,
        format_func=lambda c: ("⚠️ " if estados[c].discrepancia else "") + estados[c].campo.etiqueta,
    )
    estado = estados[campo_id]
    datos = [d for v in estado.valores for d in v.datos]
    st.dataframe(
        [
            {
                "Valor": d.valor_efectivo,
                "Valor original": d.valor if d.valor_corregido is not None else "",
                "Archivo": documentos[d.documento_id].nombre_original if d.documento_id in documentos else "(sin archivo)",
                "Página del archivo": d.numero_pagina,
                "Método": d.metodo,
                "Confianza": d.confianza or "",
                "Validación": d.estado_validacion,
                "Evidencia": d.evidencia or "",
            }
            for d in datos
        ],
        hide_index=True,
        width="stretch",
    )

    opciones = {d.id: f"«{d.valor_efectivo}» — {_origen(d, documentos)}" for d in datos}
    dato_id = st.selectbox("Dato", list(opciones), format_func=opciones.get)
    dato = next(d for d in datos if d.id == dato_id)

    columnas = st.columns(4)
    if dato.documento_id and dato.numero_pagina and columnas[0].button("Ver página de origen"):
        ir_a_pagina(dato.documento_id, dato.numero_pagina)
    if finalizada:
        return
    fabrica = obtener_fabrica_sesiones()
    if columnas[1].button("Validar"):
        with fabrica() as sesion:
            servicio_ficha.validar_dato(sesion, dato.id, usuario["id"])
            sesion.commit()
        st.rerun()
    if columnas[2].button("Descartar"):
        with fabrica() as sesion:
            servicio_ficha.descartar_dato(sesion, dato.id, usuario["id"])
            sesion.commit()
        st.rerun()
    with st.form(f"corregir_{dato.id}"):
        nuevo = st.text_input("Valor corregido (se conserva el original)", value=dato.valor_efectivo)
        if st.form_submit_button("Guardar corrección"):
            try:
                with fabrica() as sesion:
                    servicio_ficha.corregir_dato(sesion, dato.id, nuevo, usuario["id"])
                    sesion.commit()
            except servicio_ficha.ErrorFicha as error:
                st.error(str(error))
            else:
                st.rerun()


def _origen(dato, documentos) -> str:
    if dato.documento_id in documentos:
        return f"{documentos[dato.documento_id].nombre_original}, pág. {dato.numero_pagina} ({dato.metodo})"
    return dato.metodo


def _dato_manual(definicion, documentos, usuario, auditoria) -> None:
    with st.expander("Registrar un dato manualmente"):
        with st.form("dato_manual", clear_on_submit=True):
            campos = {c.id: f"{definicion.bloques[c.bloque]} · {c.etiqueta}" for c in definicion.campos}
            campo_id = st.selectbox("Campo", list(campos), format_func=campos.get)
            valor = st.text_input("Valor")
            opciones_doc = [None] + list(documentos)
            documento_id = st.selectbox(
                "Archivo de origen (recomendado)",
                opciones_doc,
                format_func=lambda d: "(sin archivo)" if d is None else documentos[d].nombre_original,
            )
            pagina = st.number_input("Página del archivo", min_value=0, value=0, help="0 = sin página")
            evidencia = st.text_area("Evidencia (texto que respalda el dato)")
            if st.form_submit_button("Registrar"):
                try:
                    with obtener_fabrica_sesiones()() as sesion:
                        servicio_ficha.agregar_dato_manual(
                            sesion, auditoria["id"], campo_id, valor, usuario["id"], documento_id, int(pagina) or None, evidencia
                        )
                        sesion.commit()
                except servicio_ficha.ErrorFicha as error:
                    st.error(str(error))
                else:
                    st.rerun()
