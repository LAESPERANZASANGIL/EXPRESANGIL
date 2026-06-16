<#
.SYNOPSIS
    Arma el instalador offline de Gestor de Guias Envia y lo nombra con la version.

.DESCRIPTION
    - Lee la version desde pyproject.toml (unica fuente de verdad).
    - Copia el codigo a dist\GestorGuiasEnvia_Instalador\app (sin .venv, datos, ni cachés).
    - Estampa la version en VERSION y LEEME.txt.
    - (Opcional) regenera las wheels offline desde las dependencias actuales.
    - Comprime todo en dist\GestorGuiasEnvia_Instalador_v<version>.zip.

    Requiere que herramientas\python-*.exe (instalador offline de Python) y herramientas\wheels\
    existan dentro de dist\GestorGuiasEnvia_Instalador. El .exe de Python se descarga una sola vez
    a mano; las wheels se pueden regenerar con -RefreshWheels.

.PARAMETER RefreshWheels
    Vuelve a descargar las wheels de las dependencias a herramientas\wheels (necesita internet).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
    powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1 -RefreshWheels
#>
[CmdletBinding()]
param(
    [switch]$RefreshWheels
)

$ErrorActionPreference = "Stop"

# --- Rutas base ---
$RepoRoot   = Split-Path -Parent $PSScriptRoot
$DistDir    = Join-Path $RepoRoot "dist"
$Installer  = Join-Path $DistDir "GestorGuiasEnvia_Instalador"
$AppDir     = Join-Path $Installer "app"
$ToolsDir   = Join-Path $Installer "herramientas"
$WheelsDir  = Join-Path $ToolsDir "wheels"

# --- 1. Leer la version desde pyproject.toml ---
$pyproject = Get-Content (Join-Path $RepoRoot "pyproject.toml") -Raw
$match = [regex]::Match($pyproject, '(?m)^\s*version\s*=\s*"([^"]+)"')
if (-not $match.Success) {
    throw "No se pudo leer 'version' de pyproject.toml."
}
$Version = $match.Groups[1].Value
Write-Host "Version: $Version" -ForegroundColor Cyan

# --- 2. Validar herramientas offline ---
$pythonExe = Get-ChildItem -Path $ToolsDir -Filter "python-*-amd64.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pythonExe) {
    Write-Warning "No se encontro herramientas\python-*-amd64.exe."
    Write-Warning "Descargalo de https://www.python.org/downloads/windows/ (instalador 64-bit) y dejalo en:"
    Write-Warning "  $ToolsDir"
    throw "Falta el instalador offline de Python."
}

# --- 3. (Opcional) regenerar wheels ---
if ($RefreshWheels) {
    Write-Host "Regenerando wheels offline..." -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $WheelsDir | Out-Null
    Get-ChildItem $WheelsDir -Filter *.whl -ErrorAction SilentlyContinue | Remove-Item -Force
    $deps = @(
        "setuptools", "wheel",
        "pandas", "openpyxl", "xlrd", "reportlab",
        "google-api-python-client", "google-auth", "google-auth-oauthlib",
        "pytest"
    )
    python -m pip download $deps --dest $WheelsDir
    if ($LASTEXITCODE -ne 0) { throw "Fallo 'pip download' al regenerar wheels." }
}
if (-not (Test-Path $WheelsDir) -or -not (Get-ChildItem $WheelsDir -Filter *.whl -ErrorAction SilentlyContinue)) {
    throw "Falta herramientas\wheels con las dependencias. Ejecuta con -RefreshWheels (necesita internet)."
}

# --- 4. Preparar carpeta app/ limpia ---
if (Test-Path $AppDir) { Remove-Item $AppDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

# Archivos sueltos del programa
foreach ($file in @("ABRIR_EDITOR.bat", "INICIAR_GESTOR.bat", "PANEL.bat", "README.md", "pyproject.toml")) {
    Copy-Item (Join-Path $RepoRoot $file) -Destination $AppDir
}

# Carpetas de codigo (robocopy excluye cachés, entornos y datos/secretos locales)
$excludeDirs  = @("__pycache__", ".venv", ".git", "node_modules")
$excludeFiles = @("*.pyc", "settings.toml", "credentials.json", "token.json")

function Copy-Tree($name) {
    $src = Join-Path $RepoRoot $name
    $dst = Join-Path $AppDir $name
    robocopy $src $dst /E /NFL /NDL /NJH /NJS /NP /XD @excludeDirs /XF @excludeFiles | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy fallo copiando $name (codigo $LASTEXITCODE)." }
}
Copy-Tree "src"
Copy-Tree "launcher"
Copy-Tree "tests"
Copy-Tree "config"   # conserva *.example.*, excluye settings.toml/credentials.json/token.json

# --- 5. Estampar la version ---
Set-Content -Path (Join-Path $AppDir "VERSION") -Value $Version -Encoding utf8

$fecha = Get-Date -Format "yyyy-MM-dd"
$leeme = @"
INSTALADOR - GESTOR DE GUIAS ENVIA (EXPRESANGIL)
================================================
Version: $Version    (empaquetado: $fecha)

COMO INSTALAR EN UN EQUIPO NUEVO
--------------------------------
1. Copia TODA esta carpeta (GestorGuiasEnvia_Instalador) al equipo nuevo
   o dejala en la memoria USB.
2. Haz CLIC DERECHO sobre INSTALAR.bat y elige
   "Ejecutar como administrador".
3. Sigue los mensajes en pantalla. El instalador hace todo solo:
   - Instala Python si el equipo no lo tiene (incluido en la carpeta).
   - Copia el programa a C:\gestor_guias_envia
   - Instala todas las librerias (incluidas en la carpeta).
   - Crea el acceso directo "Gestor de Guias Envia" en el escritorio.

NOTAS
-----
- La informacion (base de datos) queda en C:\gestor_guias_envia\data
  Este instalador NO borra datos si ya existia el programa instalado:
  solo actualiza el codigo.
- Para usar la descarga desde Gmail hay que copiar tambien
  config\credentials.json y config\token.json al equipo nuevo
  (no se incluyen aqui por seguridad).
"@
Set-Content -Path (Join-Path $Installer "LEEME.txt") -Value $leeme -Encoding utf8

# --- 6. Comprimir ---
$zipPath = Join-Path $DistDir "GestorGuiasEnvia_Instalador_v$Version.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Write-Host "Comprimiendo (puede tardar por el Python embebido)..." -ForegroundColor Cyan
Compress-Archive -Path $Installer -DestinationPath $zipPath -CompressionLevel Optimal

$size = "{0:N1} MB" -f ((Get-Item $zipPath).Length / 1MB)
Write-Host ""
Write-Host "Listo: $zipPath ($size)" -ForegroundColor Green
Write-Host "Siguiente paso: etiquetar y publicar la release (ver README, seccion Versionamiento)." -ForegroundColor Green
