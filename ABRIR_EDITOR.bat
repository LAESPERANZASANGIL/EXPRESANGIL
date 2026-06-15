@echo off
cd /d "%~dp0"
if not exist "config\settings.toml" copy "config\settings.example.toml" "config\settings.toml" >nul
if not exist ".venv\Scripts\python.exe" (
    echo No existe .venv. Ejecuta primero INICIAR_GESTOR.bat
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m gestor_guias.app editar

