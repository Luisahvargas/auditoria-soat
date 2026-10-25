"""Proveedor 'puente manual': la app prepara el paquete y el usuario lo lleva a claude.ai."""

from auditoria.ia.proveedor_base import ProveedorIA


class ProveedorPuenteManual(ProveedorIA):
    nombre = "puente_manual"
    es_manual = True

    def disponible(self) -> bool:
        return True

    def descripcion_estado(self) -> str:
        return (
            "Puente manual activo (sin costo). La app no envía nada: usted sube los PDF y el prompt a claude.ai "
            "y pega aquí la respuesta JSON. Antes de usarlo, confirme que la organización autoriza subir estos documentos a claude.ai."
        )
