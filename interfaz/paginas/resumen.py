"""Resumen de la auditoría, conclusión del auditor y cierre."""

import streamlit as st

from auditoria import catalogos
from auditoria.auditorias import cierre
from auditoria.auditorias import servicio as servicio_auditorias
from auditoria.db.repositorios import RepositorioTrazabilidad
from auditoria.exportacion.resumen import construir_resumen
from interfaz.componentes.visuales import etiqueta_procesamiento, etiqueta_resultado
from interfaz.estado import auditoria_finalizada, fijar_auditoria, requerir_auditoria
from interfaz.recursos import obtener_fabrica_sesiones


def mostrar() -> None:
    st.title("Resumen de auditoría")
    usuario, auditoria = requerir_auditoria()
    fabrica = obtener_fabrica_sesiones()
    with fabrica() as sesion:
        resumen = construir_resumen(sesion, auditoria["id"])
        trazabilidad = RepositorioTrazabilidad(sesion).listar_por_auditoria(auditoria["id"])

    finalizada = auditoria_finalizada()
    if finalizada:
        st.success(f"Auditoría FINALIZADA por {resumen.finalizada_por} el {resumen.fecha_finalizacion:%Y-%m-%d %H:%M}.")

    columnas = st.columns(5)
    columnas[0].metric("Archivos", len(resumen.documentos))
    columnas[1].metric("Páginas sin texto", sum(d.sin_texto for d in resumen.documentos))
    columnas[2].metric("Páginas sin confirmar tipo", sum(d.sin_confirmar for d in resumen.documentos))
    columnas[3].metric("Hallazgos que requieren atención", len(resumen.hallazgos_atencion))
    columnas[4].metric("Pendientes de revisión", resumen.contar(revision=catalogos.REVISION_PENDIENTE))

    st.subheader("Hallazgos por origen y revisión")
    st.dataframe(
        [
            {
                "Origen": origen,
                "Total": resumen.contar(origen),
                "Pendientes": resumen.contar(origen, catalogos.REVISION_PENDIENTE),
                "Confirmados": resumen.contar(origen, catalogos.REVISION_CONFIRMADO),
                "Descartados": resumen.contar(origen, catalogos.REVISION_DESCARTADO),
                "Modificados": resumen.contar(origen, catalogos.REVISION_MODIFICADO),
            }
            for origen in catalogos.ORIGENES
        ],
        hide_index=True,
        width="stretch",
    )
    if not resumen.hubo_ia:
        st.caption("🤖 No se ejecutó análisis de IA en esta auditoría.")

    with st.expander(f"Reglas ejecutadas: {resumen.reglas_ejecutadas} · último análisis: {resumen.ultima_ejecucion}"):
        for estado, cantidad in resumen.resultados_por_estado.items():
            st.write(f"{etiqueta_resultado(estado)}: {cantidad}")
        if resumen.no_evaluables:
            st.markdown("**No evaluables** (faltó información; no implica error):")
            st.dataframe(
                [{"Regla": h.regla, "Verificación": h.titulo} for h in resumen.no_evaluables], hide_index=True, width="stretch"
            )

    with st.expander("Documentos recibidos"):
        st.dataframe(
            [
                {"Archivo": d.archivo, "Tipo": d.tipo, "Estado": etiqueta_procesamiento(d.estado), "Páginas": d.paginas,
                 "Sin texto": d.sin_texto, "Sin confirmar": d.sin_confirmar, "Ilegibles": d.ilegibles}
                for d in resumen.documentos
            ],
            hide_index=True,
            width="stretch",
        )
    with st.expander("Datos extraídos y corregidos"):
        st.caption(resumen.edad_al_accidente)
        st.dataframe(
            [
                {"Bloque": f.bloque, "Campo": f.campo, "Valor(es)": f.valores or "—", "Fuentes": f.fuentes,
                 "Valores distintos": "⚠️" if f.discrepancia else "", "Corregidos": f.corregidos or ""}
                for f in resumen.ficha
            ],
            hide_index=True,
            width="stretch",
        )

    st.subheader("Conclusión y observaciones del auditor")
    with st.form("conclusion"):
        conclusion = st.text_area("Conclusión del auditor *", value=resumen.conclusion_auditor, height=150, disabled=finalizada)
        observaciones = st.text_area("Observaciones", value=resumen.observaciones_auditor, height=100, disabled=finalizada)
        if st.form_submit_button("Guardar", disabled=finalizada):
            with fabrica() as sesion:
                servicio_auditorias.guardar_conclusion(sesion, auditoria["id"], usuario["id"], conclusion, observaciones)
                sesion.commit()
            st.toast("Conclusión guardada.")
            st.rerun()

    st.subheader("Cierre de la auditoría")
    for requisito in resumen.requisitos:
        icono = "✅" if requisito.cumplido else ("❌" if requisito.obligatorio else "⚠️")
        sufijo = "" if requisito.obligatorio else " (recomendado)"
        st.markdown(f"{icono} **{requisito.nombre}**{sufijo}: {requisito.detalle}")

    if not finalizada:
        faltan = [r for r in resumen.requisitos if r.obligatorio and not r.cumplido]
        if st.button("Finalizar auditoría", type="primary", disabled=bool(faltan)):
            try:
                with fabrica() as sesion:
                    cierre.finalizar(sesion, auditoria["id"], usuario["id"])
                    sesion.commit()
                    fijar_auditoria(servicio_auditorias.obtener_auditoria(sesion, auditoria["id"]))
            except servicio_auditorias.ErrorAuditoria as error:
                st.error(str(error))
            else:
                st.rerun()
        if faltan:
            st.caption("Complete los pasos obligatorios para habilitar la finalización.")
    else:
        with st.form("reabrir"):
            motivo = st.text_input("Motivo para reabrir")
            if st.form_submit_button("Reabrir auditoría"):
                try:
                    with fabrica() as sesion:
                        cierre.reabrir(sesion, auditoria["id"], usuario["id"], motivo)
                        sesion.commit()
                        fijar_auditoria(servicio_auditorias.obtener_auditoria(sesion, auditoria["id"]))
                except servicio_auditorias.ErrorAuditoria as error:
                    st.error(str(error))
                else:
                    st.rerun()

    with st.expander("Registro de trazabilidad (quién hizo qué y cuándo)"):
        st.dataframe(
            [{"Fecha": r.fecha, "Usuario": r.usuario.nombre, "Acción": r.accion, "Detalle": r.detalle or ""} for r in trazabilidad],
            hide_index=True,
            width="stretch",
        )
