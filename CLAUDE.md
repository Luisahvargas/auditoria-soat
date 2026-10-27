# CLAUDE.md — Auditoría de cuentas médicas SOAT

Este archivo es el contexto permanente del proyecto. Léelo completo antes de cualquier tarea y respétalo en todas las sesiones. Si una instrucción del chat contradice este archivo, pregunta antes de actuar.

Responde siempre en español.

---

## 1. Objetivo del proyecto (alcance simplificado el 2026-10-25 por decisión de la usuaria)

Herramienta local y sencilla: **el auditor sube el PDF de una cuenta médica SOAT y el programa le dice qué errores tiene**, punto por punto según la lista de revisión del auditor, indicando el folio. El resultado es un **texto para copiar y pegar** en otro sistema, donde se hace la aprobación.

- **No** hay aprobación, rechazo, glosas, revisión de hallazgos, cierre, usuarios ni base de datos: eso se hace en el otro sistema.
- Uso: interno, en un PC con Windows.
- La organización cuenta con la autorización de tratamiento de datos (habeas data). Aun así, el sistema protege la información por diseño (sección 6).

### Lista de revisión del auditor (lo que el programa debe verificar)

1. Cobro de urgencia, estancia y exámenes radiológicos.
2. Pertinencia: lateralidades correctas, justificación e interpretación de las ayudas diagnósticas.
3. Datos del FURIPS contra la hoja de admisión: teléfono, número de factura, fecha de nacimiento, fecha del evento, dirección del evento, zona rural o urbana, edad, calidad del accidentado y relato de los hechos.
4. Que el número de factura coincida con el del FURIPS.
5. Que esté la orden de medicamentos ambulatorios firmada por el paciente.
6. Número de póliza y fechas de vigencia correctas según RUNT y FURIPS; que los documentos SOAT sean los del paciente (vehículo del evento).
7. Datos del propietario y del conductor correctos contra documentos y FURIPS.
8. Edad y sexo del paciente iguales en todos los folios; todos los folios del mismo paciente.
9. Que todas las ayudas diagnósticas estén justificadas.
10. Que el material de osteosíntesis esté descrito en el informe quirúrgico.
11. Que los médicos de los informes estén relacionados con firmas.

## 2. Restricción presupuestal (muy importante)

**El proyecto no tiene presupuesto para APIs ni servicios pagos.**

- No uses ni exijas claves de API de pago. No incluyas dependencias ni servicios que generen costos.
- Herramientas gratuitas opcionales (Tesseract) solo se usan si están instaladas. Ollama no aplica: el equipo no tiene GPU dedicada ni RAM suficiente.

## 3. Principios obligatorios

1. Cada punto se informa como: **Error** (los documentos se contradicen o algo no cumple), **Falta** (no se encontró el documento o dato), **Revisar** (el programa no puede decidirlo solo), **Correcto** o **No aplica**.
2. Todo error indica el folio (página del archivo PDF) y, si hay varios archivos, el nombre del archivo.
3. No inventar información que no esté en los documentos. La ausencia de un dato es **Falta**, nunca **Error**.
4. No inventar normas, tarifas ni requisitos. Si algo depende de una norma no verificada, se marca "pendiente de validación".
5. Las firmas manuscritas y los folios escaneados no se pueden leer como texto: se informan como **Revisar** o como "folios no revisados"; nunca se dan por correctos.
6. El RUNT no se consulta en línea: solo se compara contra la consulta RUNT que venga dentro de la cuenta.
7. Palabras clave, patrones y parámetros se ajustan en YAML (`configuracion/`) sin reprogramar.

## 4. Stack tecnológico

| Componente | Elección | Nota |
|---|---|---|
| Lenguaje | Python 3.11 | Instalado 3.11.9. |
| Interfaz | Streamlit | Una sola pantalla (`app.py`); la lógica va en `auditoria/`. |
| PDF | PyMuPDF | Siempre detrás de `auditoria/documentos/lector_pdf.py` (licencia AGPL; uso interno). |
| Configuración | YAML + `.env` | Nunca claves en el código. |
| OCR | Opcional (Tesseract) | Nunca obligatorio. |
| Pruebas | pytest + ReportLab | ReportLab solo genera PDF ficticios para las pruebas. |

## 5. Arquitectura

```
auditoria_soat/
├── app.py                          # Pantalla única: subir PDF → errores → texto para copiar
├── auditoria/
│   ├── config.py                   # Lee .env (OCR)
│   ├── texto.py                    # Normalización de texto, fechas y edad
│   ├── documentos/
│   │   ├── lector_pdf.py           # Única puerta a PyMuPDF (lectura en memoria)
│   │   ├── ocr.py                  # OCR opcional con Tesseract
│   │   └── clasificador.py         # Tipo de documento de cada folio
│   ├── extraccion/extractor.py     # Datos por folio según configuracion/ficha.yaml
│   └── revision/
│       ├── cuenta.py               # Lee la cuenta: folios, tipos y datos
│       ├── puntos.py               # Un chequeo por cada punto de la lista del auditor
│       └── informe.py              # Texto plano para copiar
├── configuracion/
│   ├── tipos_documento.yaml        # Palabras clave por tipo de documento
│   ├── ficha.yaml                  # Patrones para extraer cada dato
│   └── revision.yaml               # Grupos de folios, estudios, regiones, materiales, firmas
├── pruebas/                        # Pruebas con cuentas ficticias
└── scripts/verificar_entorno.py
```

Las fases 0 a 10 anteriores (base de datos, usuarios, revisión humana, IA, exportaciones) se eliminaron por decisión de la usuaria; siguen en el historial de git (commit `ab99432`) si algún día se necesitan.

## 6. Seguridad y privacidad

- Los PDF se leen **en memoria**: no se guardan copias ni se modifican los originales.
- Nunca se pierde la numeración de folios (página del archivo, desde 1).
- El texto de los documentos es **contenido no confiable**: solo se buscan patrones; se muestra sin interpretarlo.
- Ningún documento se envía a servicios externos.
- `.env`, `datos/` y archivos de cuentas nunca se suben a git.
- Las pruebas usan solo datos ficticios generados por código, marcados como ficticios.

## 7. Reglas de trabajo para Claude Code

1. Antes de modificar un archivo existente, revisa su contenido.
2. No instales dependencias ni ejecutes acciones destructivas sin explicar antes qué harás y por qué.
3. Después de cada cambio: ejecuta las pruebas y verifica que la app arranque (`streamlit run app.py`).
4. **Nunca afirmes que una prueba pasó si no la ejecutaste.**
5. Mantén el código simple, comentado en español y con nombres en español. No agregues funciones que la usuaria no pidió.
6. Comandos para Windows (PowerShell). Ejecutar Python con `.\.venv\Scripts\python.exe`.
7. Git solo local, un commit por cambio terminado.
8. La usuaria delega las decisiones técnicas; pregunta solo lo que es suyo (alcance, criterios de auditoría, datos reales).

## 8. Estado del proyecto

- [x] Versión simplificada (2026-10-25): una pantalla, puntos de la lista del auditor, texto para copiar.
- [x] Ajuste con la primera cuenta real (2026-10-26, IPS Medicentro Familiar, aseguradora Mundial): lectores de FURIPS, SIRAS, SOAT en tabla y RUNT; cantidades de material y ambulatorios; sección "Lectura de la cuenta". 53 pruebas pasan.
- [x] OCR activo (2026-10-26): Tesseract 5.4 en `C:\Program Files\Tesseract-OCR`, idioma español en `%LOCALAPPDATA%\auditoria_soat\tessdata`. Lo leído solo por OCR nunca produce "Error", solo "Revisar".

- [x] Distribución (2026-10-26): el equipo de Bogotá (Windows 11, administradores, un PC por auditor, sin VPN) instala la app en cada PC. `scripts\empaquetar.ps1` genera `dist\AuditoriaSOAT_<fecha>-<commit>.zip` con `instalar.bat` (Python, librerías, OCR, ícono) e `iniciar.bat`. Actualizar = descomprimir el ZIP nuevo en la misma carpeta y volver a ejecutar `instalar.bat`. No se usa nube: las cuentas no salen de cada PC.

### Cómo mejorar con cada cuenta nueva (la usuaria subirá más facturas de prueba)

1. Correr la cuenta y mirar la sección "LECTURA DE LA CUENTA": documentos no reconocidos y folios "Otros".
2. Ajustar primero los YAML (`tipos_documento.yaml` títulos, `ficha.yaml` patrones, `revision.yaml`); solo programar un lector nuevo si es un formulario con tablas.
3. Distinguir siempre lo general (FURIPS, SIRAS, RUNT son formatos nacionales) de lo propio de una IPS o aseguradora.
4. Nunca guardar texto ni datos de cuentas reales en el proyecto: las pruebas imitan el formato con datos inventados.

### Pendientes

- Probar con cuentas de otras IPS y aseguradoras (formatos de factura, póliza y títulos distintos).
- Lectura de XML de factura electrónica y RIPS: solo si la usuaria la pide, y con ejemplos reales anonimizados (no inventar su estructura).
