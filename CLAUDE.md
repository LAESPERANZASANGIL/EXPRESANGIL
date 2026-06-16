# CLAUDE.md

Guia para trabajar en este repositorio. El proyecto es local, en espanol, y corre en Windows.

## Que es

Gestor diario de guias de la oficina de Envia (Colvanes) en San Gil. Importa planillas Excel descargadas a mano, las consolida en SQLite, permite editar/seguir cada guia, gestiona la operacion de los repartidores (salidas, novedades, cierre de recaudo) y genera informes en Excel/PDF. Incluye un panel web local servido desde la stdlib.

## Como correr y probar

- **Entorno**: Windows + PowerShell. El intérprete vive en `.venv\Scripts\python.exe`.
- **Setup inicial**: doble clic en `INICIAR_GESTOR.bat` (crea `.venv`, instala con `pip install -e .`, copia `settings.toml`). Manual: `pip install -e ".[dev]"`.
- **Tests**: `.venv\Scripts\python.exe -m pytest` (config en `pyproject.toml`: `pythonpath=["src"]`, `testpaths=["tests"]`).
- **CLI**: `python -m gestor_guias.app <comando>` — es el unico punto de entrada real. Ver tabla de comandos en el README.
- **Panel web**: `PANEL.bat` -> `python -m gestor_guias.launcher_server` -> `http://127.0.0.1:8765/`.
- **Editor (Zona de Trabajo)**: `ABRIR_EDITOR.bat` o `python -m gestor_guias.app editar`.

## Arquitectura (importante para no romper nada)

- **`app.py`** es la CLI con `argparse` y la unica fachada de negocio. Toda accion (importar, exportar, informes, operadores) es un subcomando aqui.
- **`launcher_server.py`** NO reimplementa logica: su handler HTTP (`http.server`, sin frameworks) llama a `app.py` por `subprocess` (`run_command`) para informes/importar/exportar, e invoca directamente `operadores.py` + `repository.py` para login, salidas, novedades y cierre. Las sesiones viven en memoria (`SESSIONS`, cookie `session`), se pierden al reiniciar.
- **`launcher/`** es frontend estatico (HTML/CSS/JS plano, sin build). Se sirve desde `STATIC_FILES` en `launcher_server.py`; si agregas un archivo nuevo hay que registrarlo en ese diccionario.
- **`config.py`** carga `config/settings.toml` con `tomllib` a dataclasses congeladas (`Settings`). Rutas relativas se resuelven contra la raiz del repo (`BASE_DIR`).
- **`repository.py`** es el unico acceso a SQLite. Tablas: `guias` (PK `guia`), `operadores` (PK `usuario`, con `rol`), `cierres_operador` (PK `fecha, operador`). `initialize()` hace migracion ligera (ej. agrega columna `rol` si falta).
- **`excel_processor.py`** lee/normaliza/une planillas. `normalize_guide` quita guiones y cero inicial — es la forma canonica de la guia en toda la app.
- **`reports.py`** centraliza constantes compartidas: `ESTADO_RECAUDO = "E"`, `value_to_number`, `normalize_dataframe`, `filter_by_date`. `recaudo.py`, `relacion_ce_rr.py` y `operadores.py` importan de aqui — no dupliques esas utilidades.
- **`operadores.py`**: hashing PBKDF2-SHA256 (`hash_password`/`verify_password`), parseo de guias pegadas (`parse_guides`), y la maquina de estados de la operacion: salida `R`, novedades `RO`/`N`/`D`, recaudo `E`, cierre con calculo de efectivo.

## Estados de guia (no inventar nuevos sin confirmar)

- `N`: movimiento normal — unico estado que entra al consolidado.
- `R`: en reparto (salio con el operador). Constante `ESTADO_SALIDA` en `operadores.py`.
- `RO`, `N`, `D`: novedades capturadas en el dia.
- `E`: entregada/recaudada. Constante `ESTADO_RECAUDO` en `reports.py`.

## Convenciones del codigo

- Comentarios y mensajes al usuario en **espanol**; identificadores de codigo en su mayoria en espanol tambien (`registrar_salidas`, `cerrar_dia`). Mantener el estilo del archivo que tocas.
- `from __future__ import annotations` al inicio de cada modulo; type hints en firmas.
- Solo stdlib + las deps de `pyproject.toml` (pandas, openpyxl, xlrd, reportlab, google-*). No metas frameworks web ni ORMs.
- Nombres de archivos de salida en espanol con dia y mes (ej. `informe de recaudo 09 junio.xlsx`); el mes sale de `MONTHS_ES` en `exporter.py`.
- Moneda colombiana: separador de miles con punto (`format_currency_co`).

## Git y archivos ignorados

- **Antes de cualquier push, correr la suite completa y confirmar que esta en verde**: `.venv\Scripts\python.exe -m pytest`. Si algun test falla, NO hacer push: arreglar la causa primero. Esto aplica siempre, sin importar cuan pequeno parezca el cambio.
- **No versionar**: `config/credentials.json`, `config/token.json`, todo `data/`, `*.egg-info/`, `.venv/`, `__pycache__/`, `*.pyc`. Ya estan en `.gitignore`.
- `config/settings.toml` SI se versiona (decision del usuario): el repo lleva la configuracion de la oficina. `settings.example.toml` se mantiene como plantilla de referencia. Si cambias `settings.example.toml` (ej. `[excel].columns`), sincroniza tambien `settings.toml`.
- Rama principal: `main`. Remoto: `origin` (GitHub `LAESPERANZASANGIL/EXPRESANGIL`).
- No hacer commit/push salvo que el usuario lo pida.

## Al hacer cambios

- Si tocas un subcomando de la CLI, revisa si el panel web lo usa (`INFORME_COMANDOS`, rutas `/api/*` en `launcher_server.py`).
- Si cambias columnas del consolidado, sincroniza `settings.example.toml` (`[excel].columns`), `repository.py` (esquema y `save_consolidated`) y el editor.
- Si agregas un informe nuevo: modulo propio que reusa utilidades de `reports.py`, subcomando en `app.py`, y entrada en `INFORME_COMANDOS` + frontend si va al panel.
- Hay tests para `excel_processor`, `repository`, `exporter`, `operadores` y `reports`. Corre pytest antes de dar por terminado.
