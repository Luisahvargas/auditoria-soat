# Auditoría de cuentas médicas SOAT

Sube el PDF de una cuenta y el programa te dice qué errores tiene, folio por folio, según la lista de revisión del auditor. El resultado es un texto listo para copiar y pegar en el sistema donde se aprueba la cuenta.

No requiere internet, servicios pagos ni claves de API. Los documentos se leen en memoria: no se guardan ni se envían a ningún lado.

## Instalación (PowerShell, una sola vez)

Desde la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe scripts\verificar_entorno.py
```

## Uso

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

1. Se abre el navegador en `http://localhost:8501`.
2. Sube el PDF de la cuenta (o varios PDF) y pulsa **Auditar**.
3. Copia el texto con el botón de copiar del recuadro, o descárgalo como `.txt`.

Para cerrar el programa: `Ctrl + C` en la terminal.

## Qué revisa

| Sección | Puntos |
|---|---|
| FURIPS vs. hoja de admisión | Teléfono, fecha de nacimiento, fecha del evento, dirección del evento, zona rural/urbana, edad (calculada a la fecha del evento), calidad del accidentado, relato de los hechos |
| Factura, urgencia y estancia | Número de factura FURIPS vs. factura, cobro de urgencia con su soporte, días de estancia vs. ingreso/egreso y notas de evolución |
| Póliza, vehículo, propietario y conductor | Número de póliza y vigencia (FURIPS, póliza y RUNT), evento dentro de la vigencia, placa, nombre e identificación del propietario y del conductor |
| Paciente en todos los folios | Mismo paciente (nombre e identificación), sexo |
| Pertinencia, ayudas diagnósticas y firmas | Lateralidad, informe e interpretación de los exámenes radiológicos, justificación de las ayudas diagnósticas, material de osteosíntesis en la descripción quirúrgica, médicos con firma o registro, orden de medicamentos ambulatorios firmada por el paciente |

Cada punto sale como **Error**, **Falta** (no se encontró el documento o el dato), **Revisar** (hay que mirarlo a mano), **Correcto** o **No aplica**.

## Límites

- **Folios escaneados:** se leen con OCR (Tesseract, gratuito y local). Lo leído por OCR puede tener errores (sobre todo la letra a mano), por eso las diferencias que vienen solo de esos folios salen como "Revisar" y no como "Error". Instalación en un equipo nuevo:
  ```powershell
  winget install --id UB-Mannheim.TesseractOCR -e
  New-Item -ItemType Directory -Force "$env:LOCALAPPDATA\auditoria_soat\tessdata"
  Invoke-WebRequest "https://github.com/tesseract-ocr/tessdata_best/raw/main/spa.traineddata" -OutFile "$env:LOCALAPPDATA\auditoria_soat\tessdata\spa.traineddata"
  ```
  Luego pon `OCR_MOTOR=tesseract` en `.env`.
- **Lectura de la cuenta:** al final del texto se indica qué documentos se reconocieron, cuáles no y qué folios no se pudieron leer. Si un documento que sí está sale como "no se encontró", indica el folio para ajustar la lectura a ese formato.
- **Firmas:** las firmas manuscritas no se leen como texto, por eso esos puntos salen como "Revisar" con el folio.
- **RUNT:** no se consulta en línea. Se compara contra la consulta RUNT que venga dentro de la cuenta.

## Ajustes sin reprogramar

| Archivo | Para qué |
|---|---|
| `configuracion/tipos_documento.yaml` | Palabras que identifican cada tipo de folio (FURIPS, hoja de admisión, factura, RUNT…). |
| `configuracion/ficha.yaml` | Patrones para encontrar cada dato (teléfono, fechas, placa, póliza…). |
| `configuracion/revision.yaml` | Qué folios se comparan, estudios, regiones anatómicas, materiales, palabras de firma. |

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Usan solo cuentas ficticias generadas por código.
