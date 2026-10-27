@echo off
rem Instala o actualiza la aplicacion Auditoria SOAT (doble clic).
cd /d "%~dp0"
title Instalando Auditoria SOAT
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"
echo.
pause
