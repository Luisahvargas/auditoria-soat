"""Informe en texto plano, listo para copiar y pegar en el sistema de destino."""

from datetime import datetime

from auditoria.revision.cuenta import Cuenta
from auditoria.revision.puntos import CORRECTO, ERROR, FALTA, NO_APLICA, REVISAR, Punto

TITULOS = {
    ERROR: "ERRORES ENCONTRADOS",
    FALTA: "DOCUMENTOS O DATOS QUE NO SE ENCONTRARON",
    REVISAR: "REVISAR MANUALMENTE",
    CORRECTO: "SIN ERRORES",
    NO_APLICA: "NO APLICA",
}


def _linea(punto: Punto) -> str:
    folios = f" [{', '.join(punto.folios)}]" if punto.folios and punto.resultado != CORRECTO else ""
    return f"- {punto.nombre}: {punto.detalle}{folios}"


def generar_texto(cuenta: Cuenta, puntos: list[Punto], incluir_correctos: bool = True) -> str:
    archivos = sorted({f.archivo for f in cuenta.folios})
    errores = sum(p.resultado == ERROR for p in puntos)
    faltan = sum(p.resultado == FALTA for p in puntos)
    revisar = sum(p.resultado == REVISAR for p in puntos)

    lineas = [
        "AUDITORÍA DE CUENTA SOAT",
        f"Archivo(s): {', '.join(archivos) or '(ninguno)'} — {len(cuenta.folios)} folio(s)",
        f"Fecha de revisión: {datetime.now():%d/%m/%Y %H:%M}",
        f"Resultado: {errores} error(es), {faltan} faltante(s), {revisar} punto(s) para revisar manualmente.",
    ]
    sin_texto = cuenta.folios_sin_texto()
    if sin_texto:
        lineas.append(
            f"ATENCIÓN: {len(sin_texto)} folio(s) escaneados no se pudieron leer y no fueron revisados: "
            + ", ".join(cuenta.ubicacion(f) for f in sin_texto)
            + "."
        )
    for error in cuenta.errores_lectura:
        lineas.append(f"ATENCIÓN: no se pudo leer {error}")

    for resultado in (ERROR, FALTA, REVISAR, CORRECTO):
        if resultado == CORRECTO and not incluir_correctos:
            continue
        del_resultado = [p for p in puntos if p.resultado == resultado]
        if not del_resultado:
            continue
        lineas += ["", TITULOS[resultado]]
        lineas += [_linea(p) for p in del_resultado]
    return "\n".join(lineas) + "\n"
