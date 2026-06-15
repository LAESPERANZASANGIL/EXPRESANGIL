@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo No se encontro el entorno virtual .venv.
    echo Creando entorno virtual...
    py -m venv .venv
    if errorlevel 1 (
        echo.
        echo No se pudo crear el entorno virtual con py.
        echo Intenta instalar Python o ejecutar: python -m venv .venv
        pause
        exit /b 1
    )
)

if not exist "config\settings.toml" (
    echo.
    echo Creando archivo de configuracion local...
    copy "config\settings.example.toml" "config\settings.toml" >nul
)

echo.
echo Verificando instalacion del programa...
".venv\Scripts\python.exe" -m pip show gestor-guias-envia >nul 2>nul
if errorlevel 1 (
    echo Instalando dependencias. Esto puede tardar la primera vez...
    ".venv\Scripts\python.exe" -m pip install -e .
    if errorlevel 1 (
        echo.
        echo No se pudo instalar el programa.
        echo Revisa que tengas internet y Python instalado correctamente.
        pause
        exit /b 1
    )
)

:menu
cls
echo ==========================================
echo        GESTOR DE GUIAS ENVIA
echo ==========================================
echo.
echo 1. Importar planilla descargada
echo 2. Abrir editor de operador, estado y causal
echo 3. Exportar consolidado
echo 4. Generar informes
echo 5. Borrar toda la informacion guardada
echo 6. Salir
echo.
set /p opcion=Elige una opcion: 

if "%opcion%"=="1" goto importar
if "%opcion%"=="2" goto editar
if "%opcion%"=="3" goto exportar
if "%opcion%"=="4" goto informes
if "%opcion%"=="5" goto borrar
if "%opcion%"=="6" goto salir
goto menu

:fecha
set /p fecha=Fecha en formato YYYY-MM-DD. Enter para usar la fecha de hoy: 
exit /b 0

:importar
cls
echo IMPORTAR PLANILLA
echo.
echo Puedes arrastrar uno o varios archivos .xls o .xlsx a esta ventana y presionar Enter.
set /p archivo=Ruta de la planilla:
call :fecha
if "%fecha%"=="" (
    ".venv\Scripts\python.exe" -m gestor_guias.app importar %archivo%
) else (
    ".venv\Scripts\python.exe" -m gestor_guias.app importar %archivo% --fecha %fecha%
)
echo.
echo Revisa la carpeta data\output para ver el consolidado.
pause
goto menu

:editar
cls
".venv\Scripts\python.exe" -m gestor_guias.app editar
goto menu

:exportar
cls
call :fecha
if "%fecha%"=="" (
    ".venv\Scripts\python.exe" -m gestor_guias.app exportar
) else (
    ".venv\Scripts\python.exe" -m gestor_guias.app exportar --fecha %fecha%
)
echo.
echo Revisa la carpeta data\output.
pause
goto menu

:informes
cls
echo GENERAR INFORMES
echo.
echo Si ya exportaste el consolidado, normalmente esta en data\output.
set /p archivo=Ruta del consolidado .xlsx: 
set archivo=%archivo:"=%
call :fecha
if "%fecha%"=="" (
    ".venv\Scripts\python.exe" -m gestor_guias.app informes "%archivo%"
) else (
    ".venv\Scripts\python.exe" -m gestor_guias.app informes "%archivo%" --fecha %fecha%
)
echo.
echo Revisa la carpeta data\output.
pause
goto menu

:borrar
cls
echo ATENCION: esto borra toda la informacion guardada en la base local.
set /p confirma=Escribe BORRAR para confirmar: 
if /i "%confirma%"=="BORRAR" (
    ".venv\Scripts\python.exe" -m gestor_guias.app borrar-datos --confirmar
) else (
    echo Borrado cancelado.
)
pause
goto menu

:salir
exit /b 0

