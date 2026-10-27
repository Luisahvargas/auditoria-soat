# Genera el ZIP para instalar o actualizar la aplicacion en otros computadores.
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\empaquetar.ps1
# Solo incluye lo guardado en git (sin pruebas, sin datos, sin .env, sin .venv).

$ErrorActionPreference = "Stop"
$raiz = Split-Path $PSScriptRoot -Parent
Set-Location $raiz

$pendientes = git status --porcelain
if ($pendientes) { Write-Host "AVISO: hay cambios sin guardar en git; el ZIP solo incluye lo guardado." -ForegroundColor Yellow }

$commit = (git rev-parse --short HEAD).Trim()
$version = "$(Get-Date -Format 'yyyy.MM.dd')-$commit"
$contenido = @("app.py", "auditoria", "configuracion", ".streamlit", "scripts\verificar_entorno.py",
               "requirements.txt", ".env.example", "instalar.bat", "instalar.ps1", "iniciar.bat", "iniciar.ps1", "LEEME.txt")

$temporal = Join-Path $env:TEMP "auditoria_soat_paquete"
if (Test-Path $temporal) { Remove-Item $temporal -Recurse -Force }
New-Item -ItemType Directory $temporal | Out-Null

git archive --format=tar -o "$temporal\paquete.tar" HEAD @($contenido | ForEach-Object { $_ -replace '\\', '/' })
tar -xf "$temporal\paquete.tar" -C $temporal
Remove-Item "$temporal\paquete.tar"
Set-Content -Path "$temporal\version.txt" -Value $version -Encoding ascii

New-Item -ItemType Directory -Force "$raiz\dist" | Out-Null
$zip = "$raiz\dist\AuditoriaSOAT_$version.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "$temporal\*" -DestinationPath $zip
Remove-Item $temporal -Recurse -Force

Write-Host "Paquete creado: $zip" -ForegroundColor Green
Write-Host "Envie este ZIP (correo o Drive). Instrucciones dentro del archivo LEEME.txt." -ForegroundColor Green
