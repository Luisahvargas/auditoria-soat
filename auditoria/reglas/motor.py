"""Motor de reglas: ejecuta las verificaciones y registra los resultados como hallazgos.

Independiente de la interfaz y de la IA. Al volver a ejecutarse:
- Borra los resultados de reglas que el auditor aún no ha revisado.
- Conserva los que ya revisó (confirmó, descartó o modificó) y no los duplica.
"""

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from auditoria import catalogos
from auditoria.auditorias.servicio import obtener_auditoria, verificar_abierta
from auditoria.db.modelos import EjecucionReglas, Hallazgo
from auditoria.db.repositorios import RepositorioHallazgos, RepositorioTrazabilidad
from auditoria.extraccion.ficha import extraer_auditoria
from auditoria.reglas.contexto import ContextoAuditoria, Resultado
from auditoria.reglas.definiciones import Regla, cargar_reglas
from auditoria.reglas.perfiles import aplicar_perfil, cargar_perfil
from auditoria.reglas.verificaciones import VERIFICACIONES


@dataclass
class ResumenEjecucion:
    ejecucion_id: int
    reglas_ejecutadas: int
    por_estado: dict[str, int]
    nuevos: int
    conservados: int
    errores: list[str]


def evaluar(ctx: ContextoAuditoria, reglas: list[Regla]) -> list[tuple[Regla, Resultado]]:
    """Ejecuta las reglas sobre el contexto. Si una regla falla, se informa como 'No evaluable'."""
    resultados = []
    for regla in reglas:
        try:
            salida = VERIFICACIONES[regla.funcion](ctx, regla)
        except Exception as error:  # Una regla con error no debe detener las demás
            salida = [
                Resultado(
                    catalogos.NO_EVALUABLE,
                    f"La regla no se pudo evaluar por un error interno ({type(error).__name__}). Revísela en la configuración.",
                    detalle="error de evaluación",
                )
            ]
        resultados.extend((regla, r) for r in salida)
    return resultados


def clave_resultado(regla: Regla, resultado: Resultado) -> str:
    """Huella estable de un resultado para no duplicarlo al re-ejecutar."""
    evidencias = sorted(f"{e.documento_id}|{e.pagina}|{e.texto}" for e in resultado.evidencias)
    base = json.dumps([regla.id, resultado.estado, resultado.detalle, evidencias], ensure_ascii=False)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def ejecutar_reglas(sesion: Session, auditoria_id: int, usuario_id: int, extraer_antes: bool = True) -> ResumenEjecucion:
    """Extrae la ficha (opcional), ejecuta las reglas del perfil y guarda los hallazgos. No hace commit."""
    auditoria = obtener_auditoria(sesion, auditoria_id)
    verificar_abierta(auditoria)
    if extraer_antes:
        extraer_auditoria(sesion, auditoria_id, usuario_id)

    reglas = aplicar_perfil(cargar_reglas(), cargar_perfil(auditoria.perfil_aseguradora))
    ctx = ContextoAuditoria.desde_base(sesion, auditoria_id)
    resultados = evaluar(ctx, reglas)

    repositorio = RepositorioHallazgos(sesion)
    anteriores = repositorio.listar_por_auditoria(auditoria_id, catalogos.ORIGEN_REGLA)
    revisados = {h.clave for h in anteriores if h.estado_revision != catalogos.REVISION_PENDIENTE}
    repositorio.borrar_por_ids([h.id for h in anteriores if h.estado_revision == catalogos.REVISION_PENDIENTE])

    ejecucion = repositorio.agregar_ejecucion(
        EjecucionReglas(
            auditoria_id=auditoria_id,
            usuario_id=usuario_id,
            perfil_aseguradora=auditoria.perfil_aseguradora,
            reglas_ejecutadas=len(reglas),
        )
    )
    por_estado: dict[str, int] = {}
    nuevos = conservados = 0
    for regla, resultado in resultados:
        por_estado[resultado.estado] = por_estado.get(resultado.estado, 0) + 1
        clave = clave_resultado(regla, resultado)
        if clave in revisados:
            conservados += 1
            continue
        titulo = regla.nombre + (f" — {resultado.detalle}" if resultado.detalle else "")
        repositorio.agregar(
            Hallazgo(
                auditoria_id=auditoria_id,
                origen=catalogos.ORIGEN_REGLA,
                regla_id=regla.id,
                regla_version=regla.version,
                clave=clave,
                titulo=titulo[:255],
                categoria=regla.categoria,
                severidad=regla.severidad,
                estado_resultado=resultado.estado,
                explicacion=f"{resultado.explicacion}\n\n{regla.explicacion}",
                referencia_normativa=regla.referencia_normativa,
                evidencias_json=json.dumps([e.como_dict() for e in resultado.evidencias], ensure_ascii=False),
                ejecucion_id=ejecucion.id,
                usuario_creacion_id=usuario_id,
            )
        )
        nuevos += 1

    ejecucion.resumen_json = json.dumps(por_estado, ensure_ascii=False)
    RepositorioTrazabilidad(sesion).registrar(
        usuario_id, "reglas_ejecutadas", f"ejecucion_id={ejecucion.id}; reglas={len(reglas)}; resultados={len(resultados)}", auditoria_id
    )
    return ResumenEjecucion(ejecucion.id, len(reglas), por_estado, nuevos, conservados, [])
