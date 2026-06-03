@echo off
setlocal
cd /d "%~dp0"

echo ====================================================
echo   Compilando Aplicacion con PyInstaller
echo ====================================================
echo.

if not exist "venv\Scripts\pyinstaller.exe" (
    echo [ERROR] No se encontro PyInstaller en venv\Scripts\pyinstaller.exe
    echo Por favor asegurese de tener el entorno virtual configurado correctamente.
    pause
    exit /b 1
)

echo [1/2] Limpiando carpetas de compilacion anteriores...
if exist "dist" rd /s /q "dist"
if exist "build" rd /s /q "build"

echo [2/2] Ejecutando PyInstaller...
call venv\Scripts\activate.bat
venv\Scripts\pyinstaller.exe --clean MonitorPesajes.spec

echo.
echo ====================================================
echo   Compilacion Finalizada
echo ====================================================
echo El ejecutable unico se ha generado en: dist\MonitorPesajes.exe
echo.
pause
