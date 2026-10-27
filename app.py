"""Auditoría de cuenta SOAT: sube los PDF y obtén los errores, con texto listo para copiar.

Dos modos:
- Mundial de Seguros: la cuenta llega completa en un PDF.
- La Previsora: la cuenta llega en documentos separados (PREFIJO_NIT_FACTURA.pdf), de una o varias facturas.

Ejecutar con:  .\\.venv\\Scripts\\python.exe -m streamlit run app.py
"""

import os

import streamlit as st

from auditoria.config import RAIZ_PROYECTO, cargar_configuracion
from auditoria.documentos.ocr import estado_ocr
from auditoria.revision import auditar
from auditoria.revision.informe import lectura_de_la_cuenta
from auditoria.revision.paquetes import agrupar_por_factura, auditar_factura, describir_prefijo, documentos_faltantes, repetidos
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


def contar(puntos) -> dict[str, int]:
    return {r: sum(p.resultado == r for p in puntos) for r in ESTILO}


def mostrar_resultado(resultado, clave: str, titulo: str, avisos: list[str] | None = None) -> None:
    """Resumen, tarjetas por pestaña, lectura de la cuenta y texto para copiar de UNA cuenta."""
    cuenta, puntos, texto = resultado
    por_resultado = {r: [p for p in puntos if p.resultado == r] for r in ESTILO}
    errores, faltan, revisar = len(por_resultado[ERROR]), len(por_resultado[FALTA]), len(por_resultado[REVISAR])

    st.subheader(f"{titulo} · {len(cuenta.folios)} folios")
    if errores:
        st.error(f"Se encontraron **{errores} error(es)** en la cuenta. Revísalos en la pestaña **❌ Errores**.", icon="🚨")
    elif faltan or revisar:
        st.warning("No se encontraron errores, pero hay puntos que **no se encontraron** o que debes **revisar a mano**.", icon="⚠️")
    else:
        st.success("No se encontraron errores en los puntos revisados.", icon="🎉")
    for aviso in avisos or []:
        st.warning(aviso, icon="📂")

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

    pestanas = st.tabs([
        f"❌ Errores ({errores})",
        f"🟡 No encontrado ({faltan})",
        f"👁️ Revisar a mano ({revisar})",
        f"✅ Correctos ({len(por_resultado[CORRECTO])})",
        "📑 Lectura de la cuenta",
        "📋 Texto para copiar",
    ])
    vacios = {
        ERROR: "No se encontraron errores. 🎉",
        FALTA: "Todos los documentos y datos revisados se encontraron.",
        REVISAR: "No hay puntos pendientes de revisión manual.",
        CORRECTO: "Ningún punto quedó correcto.",
    }
    for pestana, resultado_punto in zip(pestanas[:4], (ERROR, FALTA, REVISAR, CORRECTO)):
        with pestana:
            if not por_resultado[resultado_punto]:
                st.caption(vacios[resultado_punto])
            for punto in por_resultado[resultado_punto]:
                tarjeta(punto)
            if resultado_punto == CORRECTO and por_resultado[NO_APLICA]:
                with st.expander(f"➖ No aplica ({len(por_resultado[NO_APLICA])})"):
                    for punto in por_resultado[NO_APLICA]:
                        st.markdown(f"- **{escapar(punto.nombre)}:** {escapar(punto.detalle)}")

    with pestanas[4]:
        st.caption("Qué documentos reconoció el programa. Si un documento que sí está en la cuenta no aparece, "
                   "el programa no supo leerlo: indica el folio para ajustarlo.")
        filas: dict[tuple[str, str], list] = {}
        for folio in cuenta.folios:
            archivo = cuenta.etiquetas.get(folio.archivo, folio.archivo)
            filas.setdefault((archivo, folio.tipo or "Sin texto (escaneado sin leer)"), []).append(folio)
        st.dataframe(
            [
                {
                    "Archivo": archivo,
                    "Documento": tipo,
                    "Folios": ", ".join(str(f.numero) for f in folios),
                    "Cantidad": len(folios),
                    "Leído con OCR": str(sum(f.metodo == "OCR" for f in folios) or ""),
                }
                for (archivo, tipo), folios in filas.items()
            ],
            hide_index=True,
            width="stretch",
        )
        for aviso in lectura_de_la_cuenta(cuenta):
            if not aviso.startswith("- Documentos reconocidos"):
                st.markdown(("⚠️ " if "No se reconoció" in aviso else "ℹ️ ") + escapar(aviso.lstrip("- ")))

    with pestanas[5]:
        st.caption("Usa el botón de copiar (esquina superior derecha del recuadro) y pégalo en el sistema de destino.")
        st.code(texto, language=None, wrap_lines=True)
        st.download_button("⬇️ Descargar como .txt", texto.encode("utf-8"), file_name=f"auditoria_{clave}.txt",
                           mime="text/plain", key=f"descarga_{clave}")


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
archivo_version = RAIZ_PROYECTO / "version.txt"
version = archivo_version.read_text(encoding="ascii").strip() if archivo_version.exists() else "desarrollo"
st.caption("Sube la cuenta en PDF y el programa te dice qué errores tiene, folio por folio. "
           f"Los documentos no se guardan ni se envían a ningún lado. · Versión {version}")

configuracion = cargar_configuracion()
ocr = estado_ocr(configuracion)

if os.getenv("AVISO_WEB"):
    # Versión publicada en internet (Streamlit Community Cloud): los archivos pasan por servidores externos.
    st.warning(
        "**Versión web de prueba.** Los PDF se procesan en servidores externos: use solo cuentas "
        "**ficticias o anonimizadas**, salvo autorización de la organización. Nada se guarda después de cerrar la página.",
        icon="🌐",
    )

MUNDIAL = "🏢 Mundial de Seguros · paquete completo en un PDF"
PREVISORA = "📂 La Previsora · documentos separados por factura"
modo = st.radio("¿Cómo llega la cuenta?", [MUNDIAL, PREVISORA], horizontal=True, key="modo")
aviso_ocr = " Los folios escaneados se leen con OCR: puede tardar unos segundos por folio." if ocr.disponible else ""

# ---------------- Mundial de Seguros: un PDF con todo ----------------
if modo == MUNDIAL:
    with st.container(border=True):
        archivos = st.file_uploader("📎 PDF de la cuenta (uno o varios)", type=["pdf"], accept_multiple_files=True, key="pdf_mundial")
        columna_boton, columna_ocr = st.columns([1, 3], vertical_alignment="center")
        auditar_ahora = columna_boton.button("🔍 Auditar cuenta", type="primary", disabled=not archivos, width="stretch")
        columna_ocr.caption(("🔤 " if ocr.disponible else "⚠️ ") + ocr.mensaje)

    if archivos and auditar_ahora:
        with st.spinner("Revisando folios…" + aviso_ocr):
            st.session_state["resultado"] = auditar([(a.name, a.getvalue()) for a in archivos], configuracion)

    if "resultado" not in st.session_state:
        st.info("👆 Sube el PDF de la cuenta y pulsa **Auditar cuenta**.")
        st.stop()
    st.divider()
    cuenta_mundial = st.session_state["resultado"][0]
    mostrar_resultado(st.session_state["resultado"], "cuenta", "Resultado · " + ", ".join(sorted({f.archivo for f in cuenta_mundial.folios})))
    st.stop()

# ---------------- La Previsora: documentos separados por factura ----------------
with st.container(border=True):
    st.markdown("Sube **todos los documentos** (pueden ser de varias facturas). Deben llamarse "
                "`PREFIJO_NIT_FACTURA.pdf`, por ejemplo `FEV_900385628_MDF65863.pdf`. "
                "Cada factura se audita solo con sus documentos.")
    archivos = st.file_uploader("📎 Documentos de las cuentas", type=["pdf"], accept_multiple_files=True, key="pdf_previsora")
    st.caption(("🔤 " if ocr.disponible else "⚠️ ") + ocr.mensaje)

if not archivos:
    st.info("👆 Sube los documentos. El programa los agrupará por número de factura.")
    st.stop()

grupos, no_reconocidos = agrupar_por_factura([(a.name, a.getvalue()) for a in archivos])
faltantes = documentos_faltantes(grupos)
if no_reconocidos:
    st.warning("Estos archivos no siguen el formato `PREFIJO_NIT_FACTURA.pdf` y no se tendrán en cuenta: "
               + ", ".join(f"`{n}`" for n in no_reconocidos), icon="⚠️")
if not grupos:
    st.stop()

st.markdown(f"**Se encontraron {len(grupos)} factura(s):**")
st.dataframe(
    [
        {
            "Factura": factura,
            "NIT": soportes[0].nit,
            "Documentos": ", ".join(s.prefijo for s in soportes),
            "Le falta (frente a las otras facturas)": ", ".join(faltantes[factura]) or "—",
            "Repetidos": ", ".join(repetidos(soportes)) or "—",
        }
        for factura, soportes in grupos.items()
    ],
    hide_index=True,
    width="stretch",
)
with st.expander("¿Qué significa cada prefijo?"):
    prefijos = sorted({s.prefijo for soportes in grupos.values() for s in soportes})
    st.markdown("\n".join(f"- **{p}**: {describir_prefijo(p)}" for p in prefijos))

seleccion = st.multiselect("Facturas a auditar", list(grupos), default=list(grupos))
if st.button(f"🔍 Auditar {len(seleccion)} factura(s)", type="primary", disabled=not seleccion):
    resultados = {}
    progreso = st.progress(0.0, text="Revisando…")
    for i, factura in enumerate(seleccion, start=1):
        progreso.progress((i - 1) / len(seleccion), text=f"Revisando factura {factura} ({i} de {len(seleccion)})…{aviso_ocr}")
        resultados[factura] = auditar_factura(grupos[factura], configuracion)
    progreso.empty()
    st.session_state["resultados_previsora"] = resultados
    st.session_state["faltantes_previsora"] = faltantes

resultados = st.session_state.get("resultados_previsora")
if not resultados:
    st.stop()

st.divider()
st.subheader("Resumen de las facturas auditadas")
resumen = []
for factura, (cuenta, puntos, _) in resultados.items():
    c = contar(puntos)
    resumen.append({
        "Factura": factura,
        "Estado": "🚨 Con errores" if c[ERROR] else ("⚠️ Revisar" if c[FALTA] or c[REVISAR] else "✅ Sin errores"),
        "❌ Errores": c[ERROR],
        "🟡 No encontrado": c[FALTA],
        "👁️ Revisar a mano": c[REVISAR],
        "Folios": len(cuenta.folios),
    })
st.dataframe(resumen, hide_index=True, width="stretch")

texto_todas = "\n\n".join(f"{'=' * 60}\nFACTURA {factura}\n{'=' * 60}\n{texto}" for factura, (_, _, texto) in resultados.items())
st.download_button("⬇️ Descargar el texto de todas las facturas (.txt)", texto_todas.encode("utf-8"),
                   file_name="auditoria_facturas.txt", mime="text/plain", key="descarga_todas")

factura_vista = st.selectbox("Ver el detalle de la factura", list(resultados),
                             format_func=lambda f: f"{f} — {next(r['Estado'] for r in resumen if r['Factura'] == f)}")
falta_vista = st.session_state.get("faltantes_previsora", {}).get(factura_vista, [])
avisos = [f"A esta factura le falta: {', '.join(f'**{p}** ({describir_prefijo(p)})' for p in falta_vista)}, que sí llegó para otras facturas."] if falta_vista else []
mostrar_resultado(resultados[factura_vista], factura_vista, f"Factura {factura_vista}", avisos)
