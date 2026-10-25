"""Elementos visuales reutilizables: estados con color e ícono."""

import streamlit as st

from auditoria import catalogos

ICONOS_PROCESAMIENTO = {
    catalogos.PROC_PENDIENTE: ("⏳", "gray"),
    catalogos.PROC_EN_CURSO: ("🔄", "blue"),
    catalogos.PROC_PROCESADO: ("✅", "green"),
    catalogos.PROC_REQUIERE_REVISION: ("⚠️", "orange"),
    catalogos.PROC_ERROR: ("❌", "red"),
}

ICONOS_RESULTADO = {
    catalogos.CONTRADICCION: "🔴",
    catalogos.POSIBLE_INCONSISTENCIA: "🟠",
    catalogos.FALTANTE: "🟡",
    catalogos.ILEGIBLE: "🟣",
    catalogos.NO_APLICA: "⚪",
    catalogos.NO_EVALUABLE: "⚪",
    catalogos.SIN_INCONSISTENCIA: "🟢",
}

ICONOS_ORIGEN = {
    catalogos.ORIGEN_REGLA: "⚙️",
    catalogos.ORIGEN_IA: "🤖",
    catalogos.ORIGEN_AUDITOR: "👤",
}


def etiqueta_procesamiento(estado: str) -> str:
    """Texto con ícono para tablas (las tablas no admiten colores)."""
    icono, _ = ICONOS_PROCESAMIENTO.get(estado, ("❔", "gray"))
    return f"{icono} {estado}"


def insignia_procesamiento(estado: str) -> None:
    icono, color = ICONOS_PROCESAMIENTO.get(estado, ("❔", "gray"))
    st.badge(estado, icon=icono, color=color)


def etiqueta_resultado(estado: str) -> str:
    return f"{ICONOS_RESULTADO.get(estado, '❔')} {estado}"


def etiqueta_origen(origen: str) -> str:
    return f"{ICONOS_ORIGEN.get(origen, '❔')} {origen}"


def texto_no_confiable(texto: str, altura: int = 250) -> None:
    """Muestra texto extraído de un documento SIN interpretarlo (ni como Markdown ni como HTML)."""
    st.text_area("Texto extraído (contenido del documento, solo lectura)", texto or "", height=altura, disabled=True)


def pendiente_de_fase(descripcion: str) -> None:
    st.info(f"🚧 {descripcion} — disponible en una fase posterior.")
