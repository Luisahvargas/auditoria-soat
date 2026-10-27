"""Auditoría de cuenta SOAT: sube el PDF y obtén los errores, con texto listo para copiar.

Ejecutar con:  .\\.venv\\Scripts\\python.exe -m streamlit run app.py
"""

import re

import streamlit as st

from auditoria.config import cargar_configuracion
from auditoria.documentos.ocr import estado_ocr
from auditoria.revision import auditar
from auditoria.revision.informe import lectura_de_la_cuenta
from auditoria.revision.puntos import CORRECTO, ERROR, FALTA, NO_APLICA, REVISAR

ESTILO = {
    ERROR: {"icono": "❌", "titulo": "Errores", "caja": st.error},
    FALTA: {"icono": "🟡", "titulo": "No encontrado", "caja": st.warning},
    REVISAR: {"icono": "👁️", "titulo": "Revisar a mano", "caja": st.info},
    CORRECTO: {"icono": "✅", "titulo": "Correctos", "caja": st.success},
    NO_APLICA: {"icono": "➖", "titulo": "No aplica", "caja": st.info},
}
_ESPECIALES_MARKDOWN = "\\`*_{}[]()#+-.!|<>$~"


def escapar(texto: str) -> str:
    """El texto viene de los documentos: se muestra literal, sin interpretarlo como formato."""
    return "".join("\\" + c if c in _ESPECIALES_MARKDOWN else c for c in texto or "")


def detalle_en_vinetas(detalle: str) -> str:
    """Convierte 'No coincide. FURIPS: … | ADMISIÓN: … | SIRAS: …' en una lista fácil de leer."""
    partes = detalle.split(" | ")
    if len(partes) == 1:
        return escapar(detalle)
    primera = partes[0]
    corte_punto, corte_dos = primera.find(". "), primera.find(": ")
    if 0 <= corte_punto < (corte_dos if corte_dos >= 0 else len(primera)):
        encabezado, primera = primera[: corte_punto + 1], primera[corte_punto + 2 :]
    elif corte_dos >= 0:
        encabezado, primera = primera[: corte_dos + 1], primera[corte_dos + 2 :]
    else:
        encabezado = ""
    vinetas = "\n".join(f"- {escapar(p)}" for p in [primera, *partes[1:]])
    return (f"**{escapar(encabezado)}**\n\n" if encabezado else "") + vinetas


def tarjeta(punto) -> None:
    estilo = ESTILO[punto.resultado]
    folios = "  ".join(f"`{f}`" for f in punto.folios[:15])
    if len(punto.folios) > 15:
        folios += f"  … y {len(punto.folios) - 15} más"
    contenido = f"**{escapar(punto.nombre)}**  \n:gray[{escapar(punto.seccion)}]\n\n{detalle_en_vinetas(punto.detalle)}"
    if folios and punto.resultado != CORRECTO:
        contenido += f"\n\n📄 {folios}"
    estilo["caja"](contenido, icon=estilo["icono"])


# ----------------------------------------------------------------------------------------
st.set_page_config(page_title="Auditoría SOAT", page_icon="🩺", layout="wide")
st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1200px;}
      div[data-testid="stMetric"] {background: rgba(128,128,128,0.08); border-radius: 12px; padding: 12px 16px;}
      div[data-testid="stAlert"] p {margin-bottom: 0.3rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Auditoría de cuenta SOAT")
st.caption("Sube la cuenta en PDF y el programa te dice qué errores tiene, folio por folio. "
           "Los documentos no se guardan ni se envían a ningún lado.")

configuracion = cargar_configuracion()
ocr = estado_ocr(configuracion)

with st.container(border=True):
    archivos = st.file_uploader("📎 PDF de la cuenta (uno o varios)", type=["pdf"], accept_multiple_files=True)
    columna_boton, columna_ocr = st.columns([1, 3], vertical_alignment="center")
    auditar_ahora = columna_boton.button("🔍 Auditar cuenta", type="primary", disabled=not archivos, width="stretch")
    columna_ocr.caption(("🔤 " if ocr.disponible else "⚠️ ") + ocr.mensaje)

if archivos and auditar_ahora:
    aviso = " Los folios escaneados se leen con OCR: puede tardar unos segundos por folio." if ocr.disponible else ""
    with st.spinner("Revisando folios…" + aviso):
        st.session_state["resultado"] = auditar([(a.name, a.getvalue()) for a in archivos], configuracion)

if "resultado" not in st.session_state:
    st.info("👆 Sube el PDF de la cuenta y pulsa **Auditar cuenta**.")
    st.stop()

cuenta, puntos, texto = st.session_state["resultado"]
por_resultado = {r: [p for p in puntos if p.resultado == r] for r in ESTILO}
errores, faltan, revisar = len(por_resultado[ERROR]), len(por_resultado[FALTA]), len(por_resultado[REVISAR])

# ---------------- Resumen ----------------
st.divider()
archivos_cuenta = sorted({f.archivo for f in cuenta.folios})
st.subheader(f"Resultado · {', '.join(archivos_cuenta)} · {len(cuenta.folios)} folios")
if errores:
    st.error(f"Se encontraron **{errores} error(es)** en la cuenta. Revísalos en la pestaña **❌ Errores**.", icon="🚨")
elif faltan or revisar:
    st.warning("No se encontraron errores, pero hay puntos que **no se encontraron** o que debes **revisar a mano**.", icon="⚠️")
else:
    st.success("No se encontraron errores en los puntos revisados.", icon="🎉")

columnas = st.columns(4)
columnas[0].metric("❌ Errores", errores)
columnas[1].metric("🟡 No encontrado", faltan)
columnas[2].metric("👁️ Revisar a mano", revisar)
columnas[3].metric("✅ Correctos", len(por_resultado[CORRECTO]))

sin_texto = cuenta.folios_sin_texto()
if sin_texto:
    st.warning(
        f"**{len(sin_texto)} folio(s) escaneados no se pudieron leer** y no fueron revisados: "
        + "  ".join(f"`{cuenta.ubicacion(f)}`" for f in sin_texto),
        icon="📷",
    )
for error in cuenta.errores_lectura:
    st.error(f"No se pudo leer {escapar(error)}")

# ---------------- Detalle por pestañas ----------------
pestanas = st.tabs([
    f"❌ Errores ({errores})",
    f"🟡 No encontrado ({faltan})",
    f"👁️ Revisar a mano ({revisar})",
    f"✅ Correctos ({len(por_resultado[CORRECTO])})",
    "📑 Lectura de la cuenta",
    "📋 Texto para copiar",
])
mensajes_vacios = {
    ERROR: "No se encontraron errores. 🎉",
    FALTA: "Todos los documentos y datos revisados se encontraron.",
    REVISAR: "No hay puntos pendientes de revisión manual.",
    CORRECTO: "Ningún punto quedó correcto.",
}
for pestana, resultado in zip(pestanas[:4], (ERROR, FALTA, REVISAR, CORRECTO)):
    with pestana:
        if not por_resultado[resultado]:
            st.caption(mensajes_vacios[resultado])
        for punto in por_resultado[resultado]:
            tarjeta(punto)
        if resultado == CORRECTO and por_resultado[NO_APLICA]:
            with st.expander(f"➖ No aplica ({len(por_resultado[NO_APLICA])})"):
                for punto in por_resultado[NO_APLICA]:
                    st.markdown(f"- **{escapar(punto.nombre)}:** {escapar(punto.detalle)}")

with pestanas[4]:
    st.caption("Qué documentos reconoció el programa. Si un documento que sí está en la cuenta no aparece, "
               "el programa no supo leerlo: indica el folio para ajustarlo.")
    por_tipo: dict[str, list] = {}
    for folio in cuenta.folios:
        por_tipo.setdefault(folio.tipo or "Sin texto (escaneado sin leer)", []).append(folio)
    st.dataframe(
        [
            {
                "Documento": tipo,
                "Folios": ", ".join(cuenta.ubicacion(f).replace("folio ", "") for f in folios),
                "Cantidad": len(folios),
                "Leído con OCR": str(sum(f.metodo == "OCR" for f in folios) or ""),
            }
            for tipo, folios in por_tipo.items()
        ],
        hide_index=True,
        width="stretch",
    )
    avisos = [l for l in lectura_de_la_cuenta(cuenta) if not l.startswith("- Documentos reconocidos")]
    for aviso in avisos:
        st.markdown(("⚠️ " if "No se reconoció" in aviso else "ℹ️ ") + escapar(aviso.lstrip("- ")))

with pestanas[5]:
    st.caption("Usa el botón de copiar (esquina superior derecha del recuadro) y pégalo en el sistema de destino.")
    st.code(texto, language=None, wrap_lines=True)
    st.download_button("⬇️ Descargar como .txt", texto.encode("utf-8"), file_name="auditoria_cuenta.txt", mime="text/plain")
