"""API de Anthropic: PREPARADA PERO DESACTIVADA (tiene costo).

Solo se habilita si en .env hay PROVEEDOR_IA=anthropic, ANTHROPIC_API_KEY y ANTHROPIC_MODELO.
El nombre del modelo nunca está fijo en el código. Antes de enviar, la interfaz muestra
qué se enviará y exige confirmación (confirmado=True).

Para activarla en el futuro también hay que instalar el SDK oficial (gratuito; el costo es del uso):
    .\\.venv\\Scripts\\python.exe -m pip install anthropic
"""

import base64

from auditoria.ia.proveedor_base import ArchivoEnvio, ErrorProveedorIA, ProveedorIA, ResultadoProveedor

LIMITE_BYTES_SOLICITUD = 32 * 1024 * 1024  # Límite de tamaño de una solicitud con PDF


class ProveedorAnthropic(ProveedorIA):
    nombre = "anthropic"
    tiene_costo = True

    def disponible(self) -> bool:
        return bool(self.config.anthropic_api_key and self.config.anthropic_modelo)

    def descripcion_estado(self) -> str:
        if not self.config.anthropic_api_key:
            return "API de Anthropic seleccionada pero SIN clave en .env: no se enviará nada."
        if not self.config.anthropic_modelo:
            return "API de Anthropic seleccionada pero sin ANTHROPIC_MODELO en .env: no se enviará nada."
        return f"API de Anthropic activa con el modelo «{self.config.anthropic_modelo}». Cada análisis tiene costo."

    def analizar(self, prompt: str, archivos: list[ArchivoEnvio], confirmado: bool) -> ResultadoProveedor:
        if not confirmado:
            raise ErrorProveedorIA("El envío a la API requiere confirmación explícita del usuario.")
        if not self.disponible():
            raise ErrorProveedorIA(self.descripcion_estado())
        try:
            import anthropic
        except ImportError as error:
            raise ErrorProveedorIA("El SDK 'anthropic' no está instalado (ver instrucciones en este módulo).") from error

        contenido = []
        total = 0
        for archivo in archivos:
            datos = archivo.ruta.read_bytes()
            total += len(datos)
            contenido.append(
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(datos).decode("ascii"),
                    },
                    "title": archivo.nombre,
                }
            )
        if total * 4 / 3 > LIMITE_BYTES_SOLICITUD:
            raise ErrorProveedorIA("Los PDF superan el tamaño máximo de una solicitud. Envíelos por partes.")
        contenido.append({"type": "text", "text": prompt})

        cliente = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
        try:
            respuesta = cliente.messages.create(
                model=self.config.anthropic_modelo,
                max_tokens=16000,
                messages=[{"role": "user", "content": contenido}],
            )
        except anthropic.APIStatusError as error:
            raise ErrorProveedorIA(f"La API respondió con error {error.status_code}: {error.message}") from error
        except anthropic.APIConnectionError as error:
            raise ErrorProveedorIA("No hubo conexión con la API.") from error

        if respuesta.stop_reason == "refusal":
            raise ErrorProveedorIA("El modelo declinó la solicitud; no se importó nada.")
        texto = "".join(bloque.text for bloque in respuesta.content if bloque.type == "text")
        return ResultadoProveedor(
            texto=texto,
            modelo=self.config.anthropic_modelo,
            tokens_entrada=respuesta.usage.input_tokens,
            tokens_salida=respuesta.usage.output_tokens,
        )
