"""Exportación del informe de auditoría (Excel y PDF)."""

import streamlit as st

from auditoria.db.repositorios import RepositorioTrazabilidad
from auditoria.exportacion.excel import generar_excel
from auditoria.exportacion.informe_pdf import generar_pdf
from auditoria.exportacion.resumen import construir_resumen
from interfaz.estado import requerir_auditoria
from interfaz.recursos import obtener_fabrica_sesiones


def mostrar() -> None:
    st.title("Exportación")
    usuario, auditoria = requerir_auditoria()

    st.markdown(
        "Genera el **informe PDF** y el **Excel** (resumen, hallazgos detallados, evidencias por archivo y página, ficha e inventario). "
        "Ambos distinguen regla automática, sugerencia de IA y conclusión del auditor, y no contienen glosas."
    )
    st.caption("Los archivos se generan en este equipo y se descargan desde el navegador; no se envían a ningún servicio.")

    with obtener_fabrica_sesiones()() as sesion:
        resumen = construir_resumen(sesion, auditoria["id"])
    if not resumen.finalizada:
        st.warning("La auditoría no está finalizada: los archivos se marcarán como BORRADOR.")

    nombre_base = f"auditoria_{resumen.identificador}".replace("/", "-").replace(" ", "_")
    columnas = st.columns(2)
    if columnas[0].button("Generar Excel", width="stretch"):
        st.session_state[f"exportacion_excel_{auditoria['id']}"] = generar_excel(resumen)
        _registrar(usuario, auditoria, "excel")
    if columnas[1].button("Generar informe PDF", width="stretch"):
        st.session_state[f"exportacion_pdf_{auditoria['id']}"] = generar_pdf(resumen)
        _registrar(usuario, auditoria, "pdf")

    if st.session_state.get(f"exportacion_excel_{auditoria['id']}"):
        columnas[0].download_button(
            "⬇️ Descargar Excel",
            st.session_state[f"exportacion_excel_{auditoria['id']}"],
            file_name=f"{nombre_base}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
    if st.session_state.get(f"exportacion_pdf_{auditoria['id']}"):
        columnas[1].download_button(
            "⬇️ Descargar PDF",
            st.session_state[f"exportacion_pdf_{auditoria['id']}"],
            file_name=f"{nombre_base}.pdf",
            mime="application/pdf",
            width="stretch",
        )


def _registrar(usuario, auditoria, formato: str) -> None:
    with obtener_fabrica_sesiones()() as sesion:
        RepositorioTrazabilidad(sesion).registrar(usuario["id"], "exportacion_generada", f"formato={formato}", auditoria["id"])
        sesion.commit()
