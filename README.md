# Auditoría inteligente de cuentas médicas SOAT

Prototipo local que **apoya al auditor humano** en la revisión de cuentas médicas SOAT: revisa los soportes y señala lo que está mal o requiere verificación, con evidencia (archivo y página). La decisión final es siempre del auditor. No genera glosas ni rechaza cuentas.

El contexto completo del proyecto está en [CLAUDE.md](CLAUDE.md).

## Requisitos

- Windows 10/11
- Python 3.11 o 3.12
- Git (recomendado)
- No requiere servicios pagos ni claves de API.

## Instalación (PowerShell, una sola vez)

Desde la carpeta del proyecto:

```powershell
# 1. Crear el entorno virtual
python -m venv .venv

# 2. Instalar las dependencias
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3. Crear el archivo de configuración a partir del ejemplo
Copy-Item .env.example .env

# 4. Verificar el entorno
.\.venv\Scripts\python.exe scripts\verificar_entorno.py
```

## Ejecutar la aplicación

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Se abre en el navegador en `http://localhost:8501`. Para detenerla: `Ctrl + C` en la terminal.

## Ejecutar las pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Las pruebas usan solo documentos ficticios generados por código.

## Flujo de trabajo

1. **Usuario** (barra lateral): seleccione o cree su usuario. Toda acción queda registrada con usuario y fecha.
2. **Inicio**: cree la auditoría (identificador interno, sin datos personales) y elija el perfil de aseguradora.
3. **Carga de documentos**: suba los PDF de la cuenta (y el XML/RIPS si los tiene). Los originales se copian en solo lectura con su SHA-256; los duplicados se detectan.
4. **Inventario**: revise el estado de cada archivo, las páginas sin texto y las secciones documentales. Confirme o corrija la clasificación propuesta.
5. **Vista de documentos**: vea cada página (imagen + texto), corrija su tipo y márquela como ilegible si es necesario.
6. **Panel de hallazgos** → *Ejecutar análisis automático*: extrae la ficha y ejecuta las 21 reglas. Por defecto solo verá lo que requiere su atención. Confirme, descarte o modifique cada hallazgo.
7. **Ficha de datos generales**: revise los datos extraídos con su fuente; valide, corrija (se conserva el original) o registre datos manuales.
8. **Análisis con IA** (opcional, puente manual): genere el paquete, súbalo a claude.ai con los PDF indicados y pegue la respuesta JSON. Lo importado queda como sugerencia pendiente de revisión.
9. **Resumen y cierre**: escriba la conclusión, verifique los requisitos y finalice la auditoría.
10. **Exportación**: descargue el informe PDF y el Excel.

## Configuración (`.env`)

| Variable | Valores | Uso |
|---|---|---|
| `RUTA_DATOS` | carpeta | Dónde se guardan originales, miniaturas y base de datos (por defecto `datos`). |
| `URL_BASE_DATOS` | cadena SQLAlchemy | Vacío = SQLite local. Futuro: PostgreSQL. |
| `OCR_MOTOR` | `ninguno` / `tesseract` | OCR opcional para PDF escaneados. |
| `RUTA_TESSERACT` | ruta | Solo si `tesseract.exe` no está en el PATH. |
| `PROVEEDOR_IA` | `desactivado` / `puente_manual` / `anthropic` / `ollama` | Por defecto `desactivado`; el puente manual no tiene costo. |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODELO` | — | API preparada pero desactivada. Dejar vacías mientras no haya presupuesto. |

Reinicie la app después de cambiar `.env`.

### OCR opcional (Tesseract, gratuito)

```powershell
winget install --id UB-Mannheim.TesseractOCR
```

Durante la instalación incluya el idioma **Spanish**. Luego ponga `OCR_MOTOR=tesseract` en `.env`. Sin Tesseract la app funciona igual y marca las páginas escaneadas como pendientes de análisis visual.

## Reglas, perfiles y patrones (sin reprogramar)

| Archivo | Qué contiene |
|---|---|
| `configuracion/reglas/reglas_base.yaml` | Las 21 reglas: descripción, severidad, parámetros, explicación, referencia normativa (hoy **"Pendiente de validación"**), versión y fecha de validación. |
| `configuracion/aseguradoras/*.yaml` | Perfiles de aseguradora: desactivar reglas o ajustar severidad y parámetros. `ejemplo_aseguradora.yaml` es **ficticio**. |
| `configuracion/tipos_documento.yaml` | Tipos documentales y palabras clave de la clasificación preliminar. |
| `configuracion/ficha.yaml` | Campos de la ficha maestra y patrones de extracción. |
| `auditoria/ia/prompts/*.md` | Plantillas de prompt versionadas (las mismas para el puente manual y la API). |

Cambie la `version` del archivo cuando lo modifique.

## Estructura

| Carpeta / archivo | Función |
|---|---|
| `app.py` | Punto de entrada de Streamlit y navegación. |
| `auditoria/` | Toda la lógica, independiente de la interfaz (se puede usar desde una futura API). |
| `auditoria/catalogos.py` | Estados de resultado, severidades, orígenes y estados de revisión. |
| `auditoria/documentos/` | Almacenamiento con SHA-256, lectura de PDF (`lector_pdf.py` es la única puerta a PyMuPDF), OCR opcional y clasificación. |
| `auditoria/extraccion/` | Extracción determinística y ficha maestra. |
| `auditoria/reglas/` | Motor de reglas, verificaciones y perfiles de aseguradora. |
| `auditoria/hallazgos/` | Revisión humana y filtros. |
| `auditoria/ia/` | Esquema JSON, puente manual y proveedores de IA. |
| `auditoria/auditorias/` | Creación, conclusión y cierre de auditorías. |
| `auditoria/exportacion/` | Resumen único, Excel e informe PDF. |
| `interfaz/` | Pantallas y componentes de Streamlit (sin lógica de negocio). |
| `datos/` | Archivos cargados y base de datos. **No se sube a git.** |
| `pruebas/` | Pruebas automatizadas con datos ficticios. |

## Privacidad

- `datos/` y `.env` están excluidos de git.
- Los documentos originales nunca se modifican (se guardan en solo lectura).
- El texto de los documentos se trata como contenido no confiable: se muestra sin interpretar y nunca como instrucción.
- El registro de trazabilidad no guarda nombres de archivo ni datos clínicos.
- Ningún documento se envía a servicios externos sin configuración explícita y confirmación.
- Se recomienda tener BitLocker activo en el equipo, porque `datos/` guarda copias de las cuentas.

## Base de datos durante el prototipo

La estructura de la base puede cambiar entre fases. Si una versión nueva lo requiere, renombre `datos\auditoria.db` (se recrea al iniciar la app). Esto deja fuera los usuarios y auditorías de prueba.

## Pendientes conocidos

- **Fase 5 (XML de factura electrónica y RIPS)**: requiere ejemplos reales anonimizados. Mientras tanto esos archivos se guardan e inventarían, pero no se leen; las reglas R05 (contra XML/RIPS), R15 (cotejo de medicamentos) y R21 quedan "No evaluable".
- Validar con el equipo auditor las referencias normativas y los umbrales de las reglas (todas "Pendiente de validación").
- Confirmar si la organización autoriza subir documentos a claude.ai para el puente manual.
- Fase 11 (multiusuario): pendiente de aprobación.
