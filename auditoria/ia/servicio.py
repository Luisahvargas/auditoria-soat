"""Ejecución de análisis con un proveedor automático (hoy ninguno activo).

Registra el consumo de tokens por auditoría e importa la respuesta con la misma
validación del puente manual (todo o nada, pendiente de revisión humana).
"""

from sqlalchemy.orm import Session

from auditoria.config import Configuracion
from auditoria.db.modelos import ConsumoIA, Hallazgo
from auditoria.db.repositorios import RepositorioConsumoIA, RepositorioDocumentos
from auditoria.documentos import almacenamiento
from auditoria.ia.proveedor_base import ArchivoEnvio, ErrorProveedorIA, obtener_proveedor
from auditoria.ia.puente_manual import PaqueteIA, importar_respuesta


def archivos_del_paquete(sesion: Session, config: Configuracion, paquete: PaqueteIA) -> list[ArchivoEnvio]:
    repositorio = RepositorioDocumentos(sesion)
    archivos = []
    for archivo in paquete.archivos:
        documento = repositorio.obtener(archivo.documento_id)
        archivos.append(ArchivoEnvio(archivo.nombre, almacenamiento.ruta_absoluta(config.ruta_datos, documento.ruta_relativa)))
    return archivos


def ejecutar_con_proveedor(
    sesion: Session, config: Configuracion, auditoria_id: int, usuario_id: int, paquete: PaqueteIA, confirmado: bool
) -> list[Hallazgo]:
    """Envía el paquete al proveedor configurado, registra tokens e importa la respuesta. No hace commit."""
    proveedor = obtener_proveedor(config)
    if proveedor.es_manual or not proveedor.disponible():
        raise ErrorProveedorIA(proveedor.descripcion_estado())
    resultado = proveedor.analizar(paquete.texto_completo, archivos_del_paquete(sesion, config, paquete), confirmado)
    # El consumo se registra aunque la respuesta resulte inválida: el costo ya ocurrió.
    RepositorioConsumoIA(sesion).agregar(
        ConsumoIA(
            auditoria_id=auditoria_id,
            usuario_id=usuario_id,
            proveedor=proveedor.nombre,
            modelo=resultado.modelo,
            tokens_entrada=resultado.tokens_entrada,
            tokens_salida=resultado.tokens_salida,
        )
    )
    sesion.flush()
    return importar_respuesta(sesion, auditoria_id, usuario_id, resultado.texto, paquete.tipo, medio=f"API {proveedor.nombre}")
