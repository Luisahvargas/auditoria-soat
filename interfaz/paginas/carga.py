"""Carga de documentos a la auditoría activa."""

import streamlit as st

from auditoria.auditorias.servicio import ErrorAuditoria
from auditoria.documentos import inventario
from interfaz.estado import auditoria_finalizada, requerir_auditoria
from interfaz.recursos import obtener_configuracion, obtener_fabrica_sesiones


def mostrar() -> None:
    st.title("Carga de documentos")
    usuario, auditoria = requerir_auditoria()

    st.markdown(
        "Cargue los **PDF** de la cuenta y, si los tiene, la **factura electrónica (XML)** y los **RIPS (JSON)**. "
        "Los originales se copian sin modificarse y se identifican por su huella SHA-256; "
        "si carga dos veces el mismo archivo, el sistema lo detecta."
    )
    st.caption("Ningún documento se envía a servicios externos.")

    if auditoria_finalizada():
        st.warning("La auditoría está finalizada: no admite nuevos documentos.")
        return

    archivos = st.file_uploader(
        "Seleccione uno o varios archivos",
        type=list(inventario.EXTENSIONES_PERMITIDAS),
        accept_multiple_files=True,
        key=f"cargador_{st.session_state.get('contador_cargas', 0)}",
    )
    if not archivos:
        _mostrar_ultimos_resultados()
        return

    if st.button(f"Cargar {len(archivos)} archivo(s)", type="primary"):
        config = obtener_configuracion()
        resultados = []
        progreso = st.progress(0.0, text="Procesando…")
        with obtener_fabrica_sesiones()() as sesion:
            for indice, archivo in enumerate(archivos, start=1):
                progreso.progress(indice / len(archivos), text=f"Procesando {indice} de {len(archivos)}…")
                try:
                    resultado = inventario.cargar_archivo(
                        sesion, config, auditoria["id"], usuario["id"], archivo.name, archivo.getvalue()
                    )
                    sesion.commit()
                except ErrorAuditoria as error:
                    sesion.rollback()
                    st.error(str(error))
                    return
                resultados.append(resultado)
        progreso.empty()

        st.session_state["contador_cargas"] = st.session_state.get("contador_cargas", 0) + 1
        st.session_state["ultimos_resultados_carga"] = [
            {"Archivo": r.nombre, "Resultado": r.resultado, "Detalle": r.mensaje} for r in resultados
        ]
        st.rerun()


def _mostrar_ultimos_resultados() -> None:
    resultados = st.session_state.get("ultimos_resultados_carga")
    if resultados:
        st.subheader("Resultado de la última carga")
        st.dataframe(resultados, hide_index=True, width="stretch")
        st.caption("Revise el detalle en **Inventario de archivos**.")
