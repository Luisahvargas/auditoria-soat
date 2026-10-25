# Auditoría inteligente de cuentas médicas SOAT

Prototipo local que **apoya al auditor humano** en la revisión de cuentas médicas SOAT: revisa los soportes y señala lo que está mal o requiere verificación, con evidencia (archivo y página). La decisión final es siempre del auditor.

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

## Estructura

| Carpeta / archivo | Función |
|---|---|
| `app.py` | Punto de entrada de Streamlit. |
| `auditoria/` | Toda la lógica, independiente de la interfaz. |
| `auditoria/config.py` | Lee la configuración desde `.env`. |
| `auditoria/db/` | Tablas, conexión y repositorios (SQLAlchemy + SQLite). |
| `auditoria/usuarios/` | Usuario activo y trazabilidad. |
| `interfaz/` | Pantallas y componentes de Streamlit (sin lógica de negocio). |
| `configuracion/` | Reglas, tipos de documento y perfiles de aseguradoras (YAML). |
| `datos/` | Archivos cargados y base de datos. **No se sube a git.** |
| `pruebas/` | Pruebas automatizadas con datos ficticios. |
| `scripts/verificar_entorno.py` | Comprueba Python, dependencias y carpeta de datos. |

## Privacidad

- `datos/` y `.env` están excluidos de git.
- Los documentos originales nunca se modifican.
- Ningún documento se envía a servicios externos sin configuración explícita y confirmación.
- Se recomienda tener BitLocker activo en el equipo, porque `datos/` guarda copias de las cuentas.

## Base de datos durante el prototipo

Mientras el proyecto está en desarrollo, la estructura de la base puede cambiar entre fases. Si una fase nueva lo requiere, se puede borrar `datos\auditoria.db` (se recrea al iniciar la app). Esto borra los usuarios y auditorías de prueba.
