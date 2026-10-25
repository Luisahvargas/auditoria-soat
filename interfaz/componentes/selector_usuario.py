"""Selección o creación del usuario local en la barra lateral."""

import streamlit as st

from auditoria.usuarios import servicio
from interfaz.recursos import obtener_fabrica_sesiones

CLAVE_USUARIO = "usuario_activo"  # Guarda {"id": ..., "nombre": ...} en la sesión de Streamlit


def usuario_activo() -> dict | None:
    return st.session_state.get(CLAVE_USUARIO)


def mostrar_selector_usuario() -> dict | None:
    """Muestra el usuario activo o permite elegir / crear uno. Devuelve el usuario activo."""
    fabrica = obtener_fabrica_sesiones()

    with st.sidebar:
        st.subheader("Usuario")
        activo = usuario_activo()
        if activo:
            st.success(f"Usuario activo: **{activo['nombre']}**")
            if st.button("Cambiar de usuario"):
                del st.session_state[CLAVE_USUARIO]
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
