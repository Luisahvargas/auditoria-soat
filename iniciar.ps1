# Inicia la aplicacion y abre el navegador. Si ya esta abierta, solo abre el navegador.
$carpeta = $PSScriptRoot
Set-Location $carpeta
$direccion = "http://localhost:8501"

function Esta-Lista {
    try { return (Invoke-WebRequest -UseBasicParsing "$direccion/_stcore/health" -TimeoutSec 2).Content -eq "ok" } catch { return $false }
}

if (Esta-Lista) {
    Start-Process $direccion
    exit 0
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "La aplicacion no esta instalada. Ejecute primero instalar.bat" -ForegroundColor Red
    Read-Host "Presione Enter para cerrar"
    exit 1
}

Write-Host "Iniciando Auditoria SOAT... el navegador se abrira en unos segundos." -ForegroundColor Cyan
Write-Host "NO cierre esta ventana mientras use la aplicacion. Para salir, cierrela." -ForegroundColor Yellow

# Abre el navegador cuando la aplicacion responda.
Start-Job -ScriptBlock {
    param($d)
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        try { if ((Invoke-WebRequest -UseBasicParsing "$d/_stcore/health" -TimeoutSec 2).Content -eq "ok") { Start-Process $d; break } } catch {}
    }
} -ArgumentList $direccion | Out-Null

& ".venv\Scripts\python.exe" -m streamlit run app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false
