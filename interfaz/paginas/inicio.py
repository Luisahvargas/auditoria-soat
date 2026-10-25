"""Inicio: bienvenida, lista de auditorías y creación de una nueva."""

import streamlit as st

from auditoria.auditorias import servicio
from interfaz.estado import auditoria_activa, fijar_auditoria, usuario_activo
from interfaz.recursos import obtener_configuracion, obtener_fabrica_sesiones


def mostrar() -> None:
    st.title("Auditoría de cuentas médicas SOAT")
    st.caption("Herramienta de apoyo al auditor · Prototipo local")

    st.markdown(
        """
        Esta herramienta **revisa la cuenta y le señala lo que está mal o requiere verificación**,
        siempre con la evidencia (archivo y página). **La decisión final es suya.**
        No genera glosas definitivas ni rechaza cuentas.
        """
    )

    config = obtener_configuracion()
    if config.proveedor_ia == "desactivado":
        st.caption("🤖 Análisis con IA: **desactivado** (solo reglas automáticas).")
    else:
        st.caption(f"🤖 Proveedor de IA configurado: **{config.proveedor_ia}**.")

    usuario = usuario_activo()
    if not usuario:
        st.warning("Seleccione o cree su usuario en la barra lateral para comenzar.")
        return

    fabrica = obtener_fabrica_sesiones()
    columna_lista, columna_nueva = st.columns([3, 2], gap="large")

    with columna_nueva:
        st.subheader("Nueva auditoría")
        with st.form("nueva_auditoria", clear_on_submit=True):
            identificador = st.text_input(
                "Identificador interno *", help="Código interno de la cuenta. No use nombres ni documentos del paciente."
            )
            descripcion = st.text_area("Descripción (opcional)", help="Sin datos personales.")
            perfiles = _perfiles_disponibles()
            perfil = st.selectbox("Perfil de aseguradora", list(perfiles), format_func=perfiles.get)
            if st.form_submit_button("Crear auditoría", type="primary"):
                try:
                    with fabrica() as sesion:
                        auditoria = servicio.crear_auditoria(sesion, usuario["id"], identificador, descripcion, perfil)
                        sesion.commit()
                        fijar_auditoria(auditoria)
                except servicio.ErrorAuditoria as error:
                    st.error(str(error))
                else:
                    st.rerun()

    with columna_lista:
        st.subheader("Auditorías")
        with fabrica() as sesion:
            auditorias = servicio.listar_auditorias(sesion)
            filas = [
                {
                    "id": a.id,
                    "Identificador": a.identificador,
                    "Descripción": a.descripcion or "",
                    "Estado": a.estado,
                    "Creada por": a.usuario_creador.nombre,
                    "Fecha": a.fecha_creacion,
                }
                for a in auditorias
            ]
        if not filas:
            st.info("Aún no hay auditorías. Cree la primera a la derecha.")
            return

        activa = auditoria_activa()
        st.dataframe(
            [{k: v for k, v in f.items() if k != "id"} for f in filas],
            hide_index=True,
            width="stretch",
        )
        opciones = {f["id"]: f"{f['Identificador']} — {f['Estado']}" for f in filas}
        ids = list(opciones)
        indice = ids.index(activa["id"]) if activa and activa["id"] in ids else 0
        elegida = st.selectbox("Abrir auditoría", ids, index=indice, format_func=opciones.get)
        if st.button("Abrir", type="primary"):
            with fabrica() as sesion:
                fijar_auditoria(servicio.obtener_auditoria(sesion, elegida))
            st.rerun()


def _perfiles_disponibles() -> dict[str, str]:
    """Perfiles de aseguradora configurados en YAML (identificador -> nombre)."""
    try:
        from auditoria.reglas.perfiles import listar_perfiles

        return listar_perfiles()
    except ImportError:  # El motor de reglas aún no existe
        return {"generica": "Genérica (sin ajustes de aseguradora)"}
