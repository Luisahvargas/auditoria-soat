"""Auditoría de cuenta SOAT: sube el PDF y obtén la lista de errores para copiar.

Ejecutar con:  .\\.venv\\Scripts\\python.exe -m streamlit run app.py
"""

import streamlit as st

from auditoria.config import cargar_configuracion
from auditoria.documentos.ocr import estado_ocr
from auditoria.revision import auditar
from auditoria.revision.puntos import CORRECTO, ERROR, FALTA, NO_APLICA, ORDEN_RESULTADOS, REVISAR

ICONOS = {ERROR: "❌", FALTA: "🟡", REVISAR: "👁️", CORRECTO: "✅", NO_APLICA: "➖"}

st.set_page_config(page_title="Auditoría SOAT", page_icon="🩺", layout="wide")
st.title("Auditoría de cuenta SOAT")
st.caption("Sube la cuenta en PDF y el programa te dice qué errores tiene. Los documentos no se guardan ni se envían a ningún lado.")

configuracion = cargar_configuracion()
ocr = estado_ocr(configuracion)
st.caption(("🔤 " if ocr.disponible else "⚠️ ") + ocr.mensaje)

archivos = st.file_uploader("PDF de la cuenta (uno o varios)", type=["pdf"], accept_multiple_files=True)
if archivos and st.button("Auditar", type="primary"):
    aviso = " Los folios escaneados se leen con OCR: puede tardar unos segundos por folio." if ocr.disponible else ""
    with st.spinner("Revisando folios…" + aviso):
        st.session_state["resultado"] = auditar([(a.name, a.getvalue()) for a in archivos], configuracion)

if "resultado" not in st.session_state:
    st.stop()

cuenta, puntos, texto = st.session_state["resultado"]

columnas = st.columns(4)
columnas[0].metric("❌ Errores", sum(p.resultado == ERROR for p in puntos))
columnas[1].metric("🟡 No encontrado", sum(p.resultado == FALTA for p in puntos))
columnas[2].metric("👁️ Revisar a mano", sum(p.resultado == REVISAR for p in puntos))
columnas[3].metric("✅ Correctos", sum(p.resultado == CORRECTO for p in puntos))

if cuenta.folios_sin_texto():
    st.warning(
        f"{len(cuenta.folios_sin_texto())} folio(s) escaneados no se pudieron leer y NO fueron revisados. {cuenta.mensaje_ocr}"
    )
for error in cuenta.errores_lectura:
    st.error(f"No se pudo leer {error}")

st.subheader("Texto para copiar")
st.code(texto, language=None, wrap_lines=True)
st.download_button("Descargar .txt", texto.encode("utf-8"), file_name="auditoria_cuenta.txt", mime="text/plain")

st.subheader("Detalle por punto")
orden = {r: i for i, r in enumerate(ORDEN_RESULTADOS)}
st.dataframe(
    [
        {"": ICONOS[p.resultado], "Resultado": p.resultado, "Punto": p.nombre, "Sección": p.seccion,
         "Detalle": p.detalle, "Folios": ", ".join(p.folios)}
        for p in sorted(puntos, key=lambda p: orden[p.resultado])
    ],
    hide_index=True,
    width="stretch",
)

with st.expander("Folios leídos y tipo de documento detectado"):
    st.dataframe(
        [{"Archivo": f.archivo, "Folio": f.numero, "Tipo detectado": f.tipo or "Sin texto (escaneado)", "Lectura": f.metodo}
         for f in cuenta.folios],
        hide_index=True,
        width="stretch",
    )
