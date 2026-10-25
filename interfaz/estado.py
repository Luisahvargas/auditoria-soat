"""Estado de la sesión de Streamlit: usuario activo y auditoría activa."""

import streamlit as st

from auditoria import catalogos

CLAVE_USUARIO = "usuario_activo"  # {"id": ..., "nombre": ...}
CLAVE_AUDITORIA = "auditoria_activa"  # {"id": ..., "identificador": ..., "estado": ...}


def usuario_activo() -> dict | None:
    return st.session_state.get(CLAVE_USUARIO)


def auditoria_activa() -> dict | None:
    return st.session_state.get(CLAVE_AUDITORIA)


def fijar_auditoria(auditoria) -> None:
    st.session_state[CLAVE_AUDITORIA] = {
        "id": auditoria.id,
        "identificador": auditoria.identificador,
        "estado": auditoria.estado,
    }


def requerir_usuario() -> dict:
    """Detiene la página si no hay usuario activo."""
    usuario = usuario_activo()
    if not usuario:
        st.warning("Seleccione o cree su usuario en la barra lateral para continuar.")
        st.stop()
    return usuario


def requerir_auditoria() -> tuple[dict, dict]:
    """Detiene la página si no hay usuario o auditoría activa. Devuelve (usuario, auditoria)."""
    usuario = requerir_usuario()
    auditoria = auditoria_activa()
    if not auditoria:
        st.warning("Seleccione o cree una auditoría en **Inicio** para continuar.")
        st.page_link(st.session_state["pagina_inicio"], label="Ir a Inicio", icon="🏠")
        st.stop()
    return usuario, auditoria


def auditoria_finalizada() -> bool:
    auditoria = auditoria_activa()
    return bool(auditoria and auditoria["estado"] == catalogos.AUDITORIA_FINALIZADA)
