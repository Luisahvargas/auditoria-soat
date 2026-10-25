"""Proveedor por defecto: no ejecuta IA y lo informa claramente."""

from auditoria.ia.proveedor_base import ProveedorIA


class ProveedorDesactivado(ProveedorIA):
    nombre = "desactivado"

    def disponible(self) -> bool:
        return False

    def descripcion_estado(self) -> str:
        return (
            "El análisis con IA está DESACTIVADO: no se ejecutó ningún análisis de IA. "
            "La auditoría se basa solo en reglas automáticas y en la revisión del auditor. "
            "Para usar el puente manual (sin costo), ponga PROVEEDOR_IA=puente_manual en el archivo .env y reinicie la app."
        )
