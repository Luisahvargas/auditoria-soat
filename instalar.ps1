# Instalador de Auditoria SOAT para Windows 10/11.
# Se puede ejecutar varias veces: tambien sirve para actualizar a una version nueva.
# Pasos: Python 3.11, librerias, OCR (Tesseract + espanol), configuracion y acceso directo.
param(
    [switch]$SinAccesoDirecto,  # Para pruebas: no crea el icono en el escritorio
    [switch]$SinOCR             # No instala Tesseract
)

$ErrorActionPreference = "Stop"
$carpeta = $PSScriptRoot
Set-Location $carpeta

function Paso($texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }
function Ok($texto) { Write-Host "    OK: $texto" -ForegroundColor Green }
function Aviso($texto) { Write-Host "    AVISO: $texto" -ForegroundColor Yellow }

function Buscar-Python311 {
    $candidatos = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "C:\Program Files\Python311\python.exe"
    )
    foreach ($c in $candidatos) { if (Test-Path $c) { return $c } }
    try {
        $ruta = (& py -3.11 -c "import sys; print(sys.executable)") 2>$null
        if ($ruta -and (Test-Path $ruta)) { return $ruta }
    } catch {}
    return $null
}

try {
    Write-Host "Instalacion de Auditoria SOAT en: $carpeta" -ForegroundColor White

    # Los archivos descargados de internet quedan "bloqueados" por Windows.
    Get-ChildItem -Path $carpeta -Recurse -File | Unblock-File -ErrorAction SilentlyContinue

    Paso "1/5 Python 3.11"
    $python = Buscar-Python311
    if (-not $python) {
        Write-Host "    Instalando Python 3.11 (puede tardar unos minutos)..."
        winget install -e --id Python.Python.3.11 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
        $python = Buscar-Python311
        if (-not $python) { throw "No se pudo instalar Python 3.11. Instalelo desde https://www.python.org/downloads/ y vuelva a ejecutar el instalador." }
    }
    Ok "Python en $python"

    Paso "2/5 Librerias de la aplicacion"
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        & $python -m venv .venv
    }
    & ".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet --disable-pip-version-check
    & ".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { throw "No se pudieron instalar las librerias (revise la conexion a internet)." }
    Ok "Librerias instaladas"

    Paso "3/5 OCR para folios escaneados (Tesseract)"
    $tessdata = Join-Path $env:LOCALAPPDATA "auditoria_soat\tessdata"
    if ($SinOCR) {
        Aviso "Se omitio el OCR por solicitud."
    } else {
        if (-not (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe")) {
            Write-Host "    Instalando Tesseract (Windows puede pedir permiso de administrador)..."
            winget install -e --id UB-Mannheim.TesseractOCR --silent --accept-package-agreements --accept-source-agreements | Out-Host
        }
        if (Test-Path "C:\Program Files\Tesseract-OCR\tesseract.exe") { Ok "Tesseract instalado" } else { Aviso "Tesseract no quedo instalado: la app funciona, pero no leera folios escaneados." }
        New-Item -ItemType Directory -Force $tessdata | Out-Null
        $spa = Join-Path $tessdata "spa.traineddata"
        if (-not (Test-Path $spa)) {
            Write-Host "    Descargando idioma espanol para el OCR..."
            Invoke-WebRequest -UseBasicParsing "https://github.com/tesseract-ocr/tessdata_best/raw/main/spa.traineddata" -OutFile $spa
        }
        Ok "Idioma espanol listo"
    }

    Paso "4/5 Configuracion"
    if (-not (Test-Path ".env")) {
        $config = Get-Content ".env.example" -Raw
        if (-not $SinOCR) { $config = $config -replace "OCR_MOTOR=ninguno", "OCR_MOTOR=tesseract" }
        $config = $config -replace "RUTA_TESSDATA=", "RUTA_TESSDATA=$tessdata"
        [IO.File]::WriteAllText((Join-Path $carpeta ".env"), $config, (New-Object System.Text.UTF8Encoding $false))
        Ok "Archivo .env creado"
    } else {
        Ok "Se conserva la configuracion existente (.env)"
    }
    & ".venv\Scripts\python.exe" "scripts\verificar_entorno.py" | Out-Host

    Paso "5/5 Icono en el escritorio"
    if ($SinAccesoDirecto) {
        Aviso "Se omitio el icono por solicitud."
    } else {
        $escritorio = [Environment]::GetFolderPath("Desktop")
        $acceso = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $escritorio "Auditoria SOAT.lnk"))
        $acceso.TargetPath = Join-Path $carpeta "iniciar.bat"
        $acceso.WorkingDirectory = $carpeta
        $acceso.WindowStyle = 7  # Minimizado
        $acceso.IconLocation = "$env:SystemRoot\System32\imageres.dll,76"
        $acceso.Description = "Abrir la aplicacion de auditoria de cuentas SOAT"
        $acceso.Save()
        Ok "Icono 'Auditoria SOAT' creado en el escritorio"
    }

    Write-Host "`nLISTO. Abra la aplicacion con el icono 'Auditoria SOAT' del escritorio." -ForegroundColor Green
} catch {
    Write-Host "`nERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Envie una foto de esta ventana a quien le compartio la aplicacion." -ForegroundColor Red
    exit 1
}
