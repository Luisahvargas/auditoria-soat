"""Barra lateral: usuario activo y auditoría activa (siempre visibles)."""

import streamlit as st

from auditoria.auditorias import servicio as servicio_auditorias
from auditoria.usuarios import servicio
from interfaz.estado import CLAVE_AUDITORIA, CLAVE_USUARIO, auditoria_activa, fijar_auditoria, usuario_activo
from interfaz.recursos import obtener_fabrica_sesiones


def mostrar_barra_lateral() -> dict | None:
    """Muestra el usuario y la auditoría activos. Devuelve el usuario activo."""
    with st.sidebar:
        usuario = _selector_usuario()
        if usuario:
            st.divider()
            _auditoria_activa()
    return usuario


def _selector_usuario() -> dict | None:
    fabrica = obtener_fabrica_sesiones()
    st.subheader("👤 Usuario")
    activo = usuario_activo()
    if activo:
        st.success(f"Usuario activo: **{activo['nombre']}**")
        if st.button("Cambiar de usuario"):
            st.session_state.pop(CLAVE_USUARIO, None)
            st.session_state.pop(CLAVE_AUDITORIA, None)
            st.rerun()
        return activo

    with fabrica() as sesion:
        usuarios = servicio.listar_usuarios(sesion)

    if usuarios:
        opciones = {u.nombre: u.id for u in usuarios}
        nombre = st.selectbox("Seleccione su usuario", list(opciones))
        if st.button("Ingresar", type="primary"):
            with fabrica() as sesion:
                servicio.registrar_seleccion(sesion, opciones[nombre])
                sesion.commit()
            st.session_state[CLAVE_USUARIO] = {"id": opciones[nombre], "nombre": nombre}
            st.rerun()

    with st.expander("Crear usuario nuevo", expanded=not usuarios):
        with st.form("crear_usuario", clear_on_submit=True):
            nombre_nuevo = st.text_input("Nombre del auditor")
            if st.form_submit_button("Crear y entrar"):
                try:
                    with fabrica() as sesion:
                        usuario = servicio.crear_usuario(sesion, nombre_nuevo)
                        servicio.registrar_seleccion(sesion, usuario.id)
                        sesion.commit()
                        datos = {"id": usuario.id, "nombre": usuario.nombre}
                except servicio.ErrorUsuario as error:
                    st.error(str(error))
                else:
                    st.session_state[CLAVE_USUARIO] = datos
                    st.rerun()
    return None


def _auditoria_activa() -> None:
    st.subheader("📁 Auditoría activa")
    activa = auditoria_activa()
    if not activa:
        st.caption("Ninguna. Créela o selecciónela en Inicio.")
        return

    # Se refresca el estado por si otra pantalla la finalizó.
    with obtener_fabrica_sesiones()() as sesion:
        try:
            fijar_auditoria(servicio_auditorias.obtener_auditoria(sesion, activa["id"]))
        except servicio_auditorias.ErrorAuditoria:
            st.session_state.pop(CLAVE_AUDITORIA, None)
            st.caption("La auditoría ya no existe.")
            return
    activa = auditoria_activa()
    st.info(f"**{activa['identificador']}**  \nEstado: {activa['estado']}")
    if st.button("Salir de esta auditoría"):
        st.session_state.pop(CLAVE_AUDITORIA, None)
        st.rerun()
