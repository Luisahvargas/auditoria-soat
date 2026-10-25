"""Pantalla de bienvenida."""

import streamlit as st

from auditoria.config import Configuracion


def mostrar_bienvenida(config: Configuracion, usuario: dict | None) -> None:
    st.title("Auditoría de cuentas médicas SOAT")
    st.caption("Herramienta de apoyo al auditor · Prototipo local")

    st.markdown(
        """
        Esta herramienta **revisa la cuenta y le señala lo que está mal o requiere verificación**,
        siempre con la evidencia (archivo y página). **La decisión final es suya.**

        - No genera glosas definitivas ni rechaza cuentas.
        - Distingue entre resultados de **regla automática**, **sugerencia de IA** y **conclusión del auditor**.
        - Los documentos originales nunca se modifican.
        """
    )

    if config.proveedor_ia == "desactivado":
        st.info("Análisis con IA: **desactivado**. La auditoría se hará solo con reglas automáticas.")
    else:
        st.info(f"Proveedor de IA configurado: **{config.proveedor_ia}**.")

    if usuario:
        st.success(f"Bienvenido(a), {usuario['nombre']}. Las demás secciones se habilitarán en las próximas fases.")
    else:
        st.warning("Seleccione o cree su usuario en la barra lateral para comenzar.")
