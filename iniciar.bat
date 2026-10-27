@echo off
rem Abre la aplicacion Auditoria SOAT en el navegador.
cd /d "%~dp0"
title Auditoria SOAT - NO CIERRE ESTA VENTANA mientras use la aplicacion
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar.ps1"
