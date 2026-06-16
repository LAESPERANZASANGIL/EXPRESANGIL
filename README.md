# Gestor de Guias Envia

Aplicacion local en Python para la oficina de Envia (Colvanes) que importa las planillas diarias de guias, las consolida en una base local, permite editar y hacer seguimiento de cada guia (operador, estado, causal), gestiona la operacion de los repartidores y genera los informes y relaciones de cada dia.

Esta version agrega un **panel web local (launcher)** con dos zonas:

- **Zona del administrador**: importar planillas, exportar el consolidado, generar informes y abrir la Zona de Trabajo.
- **Zona de operadores**: cada repartidor inicia sesion, registra las guias que saca a reparto, reporta novedades y hace el cierre de recaudo del dia.

## Que hace

Automatiza el proceso diario de la oficina:

1. Descargar manualmente las planillas desde el sistema o el correo.
2. Importarlas al programa (uno o varios archivos `.xls` / `.xlsx`).
3. Leer las planillas y extraer solo las columnas necesarias.
4. Consolidar y conservar la informacion en una base local SQLite.
5. Actualizar guias repetidas por `GUIA` sin perder datos anteriores.
6. Mantener lo ya editado de `OPERADOR`, `ESTADO` y `CAUSAL`.
7. Dejar en el consolidado solo las guias con estado de movimiento `N`.
8. Exportar aparte los movimientos con estados distintos de `N`.
9. Generar el Excel final de trabajo (por ejemplo `09 junio.xlsx`).
10. Editar operador, estado y causal por guia o de forma masiva.
11. Operar el reparto: salidas, novedades y cierre de recaudo por operador.
12. Generar informes (general, por operador, recaudo) y la relacion CE/RR.
13. Borrar la informacion solo cuando el usuario lo confirma.

## Como ejecutarlo (Windows)

La forma recomendada es con los `.bat` incluidos:

| Archivo | Para que sirve |
| --- | --- |
| `INICIAR_GESTOR.bat` | Crea el entorno `.venv`, instala el programa y abre el **menu de consola** (importar, editar, exportar, informes, borrar). Ejecutalo la primera vez. |
| `PANEL.bat` | Abre el **panel web** (administrador + operadores) en el navegador. |
| `ABRIR_EDITOR.bat` | Abre directamente la **Zona de Trabajo** (editor de guias). |

El primer inicio crea `config/settings.toml` a partir de `config/settings.example.toml` e instala las dependencias si hace falta.

### Panel web

`PANEL.bat` levanta un servidor local (`http://127.0.0.1:8765/`) y abre el navegador:

- **Administrador** (`/`): importar, exportar, generar informes y abrir la Zona de Trabajo.
- **Operadores** (`/operadores`): login por usuario y contrasena; salidas, novedades y cierre de recaudo.
- **Usuarios** (`/usuarios`): gestion de usuarios (solo administradores). El primer usuario que se crea debe ser `admin`.

## Preparacion manual (opcional)

Si prefieres no usar los `.bat`:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy config\settings.example.toml config\settings.toml
```

## Linea de comandos

Todo el programa se maneja con `python -m gestor_guias.app <comando>`. El panel web simplemente llama a estos mismos comandos.

| Comando | Que hace |
| --- | --- |
| `importar <archivos...> [--fecha YYYY-MM-DD]` | Importa planillas descargadas y conserva lo existente. |
| `procesar-archivos <archivos...>` | Alias de `importar` (compatibilidad). |
| `consolidar [--fecha]` | Descarga adjuntos desde Gmail y genera el Excel (flujo automatico). |
| `exportar [--fecha]` | Reexporta el Excel desde la base local. |
| `editar` | Abre la Zona de Trabajo (editor Tkinter de operador/estado/causal). |
| `informes <archivo.xlsx> [--fecha]` | Genera informes desde un consolidado en Excel. |
| `informe-operador [--fecha]` | Informe por operador (Excel + PDF) desde la base. |
| `informe-dia [--fecha]` | Informe del dia desde la base. |
| `informe-recaudo [--fecha]` | Informe de recaudo diario. |
| `informe-relacion-ce-rr [--fecha]` | Relacion en PDF de guias CE y RR por operador. |
| `operador-crear --usuario --password --nombre [--rol operador\|admin]` | Crea o actualiza un usuario del panel. |
| `operador-listar` | Lista los usuarios registrados. |
| `operador-eliminar --usuario` | Elimina un usuario. |
| `borrar-datos --confirmar` | Borra toda la informacion guardada. |

Ejemplos:

```bash
python -m gestor_guias.app importar "ruta\planilla1.xls" "ruta\planilla2.xls" --fecha 2026-06-09
python -m gestor_guias.app editar
python -m gestor_guias.app informe-recaudo --fecha 2026-06-09
python -m gestor_guias.app operador-crear --usuario johan --password 1234 --nombre "JOHAN A. ORTIZ" --rol admin
```

En el editor puedes seleccionar varias guias con `Ctrl` o `Shift`, escribir `OPERADOR`, `ESTADO` y `CAUSAL`, aplicar a las seleccionadas, o pegar una lista de guias y aplicar a la lista.

## Arquitectura

```text
EXPRESANGIL/
├── config/
│   ├── settings.example.toml      # Plantilla de configuracion (settings.toml se ignora)
│   └── credentials.example.json   # Plantilla de credenciales de Gmail
├── data/                          # Ignorado por git (solo .gitkeep)
│   ├── attachments/               # Adjuntos descargados por fecha
│   ├── database/guias.db          # Base local SQLite
│   └── output/                    # Excel e informes generados
├── launcher/                      # Frontend del panel web (HTML/CSS/JS estatico)
│   ├── index.html / app.js / style.css            # Zona administrador
│   ├── operadores.html / .js / .css               # Zona operadores
│   └── usuarios.html / .js / .css                 # Gestion de usuarios
├── src/gestor_guias/
│   ├── app.py              # CLI (punto de entrada de todos los comandos)
│   ├── launcher_server.py  # Servidor HTTP del panel web (stdlib http.server)
│   ├── config.py           # Carga settings.toml (dataclasses)
│   ├── gmail_client.py     # Descarga de adjuntos desde Gmail (flujo consolidar)
│   ├── excel_processor.py  # Lectura/normalizacion/union de planillas
│   ├── repository.py       # Acceso a SQLite (guias, operadores, cierres)
│   ├── exporter.py         # Exportacion a Excel del consolidado
│   ├── reports.py          # Informes general, por operador y del dia
│   ├── recaudo.py          # Informe de recaudo diario
│   ├── relacion_ce_rr.py   # Relacion PDF de guias CE y RR
│   ├── operadores.py       # Logica de operadores: hash, salidas, novedades, cierre
│   └── editor_gui.py       # Editor Tkinter (Zona de Trabajo)
├── tests/                  # Pruebas con pytest
├── INICIAR_GESTOR.bat / PANEL.bat / ABRIR_EDITOR.bat
├── pyproject.toml
└── README.md
```

## Tecnologias

- **Python 3.12+** (usa `tomllib` y `zoneinfo` de la stdlib).
- **pandas** + **openpyxl** + **xlrd**: lectura y union de planillas y exportacion a Excel.
- **SQLite** (stdlib): base local de guias, operadores y cierres.
- **reportlab**: informes y relaciones en PDF.
- **http.server** (stdlib): servidor del panel web, sin frameworks.
- **Tkinter** (stdlib): editor de la Zona de Trabajo.
- **google-api-python-client** / **google-auth**: descarga de adjuntos desde Gmail (comando `consolidar`).
- **pytest**: pruebas.

## Modelo de datos (SQLite)

- **`guias`**: una fila por `GUIA` (clave primaria). Columnas del consolidado mas seguimiento (`operador`, `estado`, `causal`).
- **`operadores`**: `usuario` (PK), `password_hash` (PBKDF2-SHA256), `nombre`, `rol` (`operador` / `admin`).
- **`cierres_operador`**: cierre de recaudo por `(fecha, operador)`: gestionadas, conteos de estados, recaudado, bancos, nequi, envia y efectivo.

## Flujo de la operacion (operadores)

1. **Salidas**: el operador inicia sesion y registra (escaneando o pegando) las guias que saca a reparto. Pasan a estado `R`.
2. **Novedades**: durante el dia reporta guias `RO`, `N` o `D`.
3. **Cierre**: al final registra recaudo por banco, Nequi y Envia; el sistema calcula el efectivo y guarda el cierre del dia.

## Estructura del consolidado diario

El archivo diario conserva exactamente estas columnas:

```text
PLANILLA  SERVICIO  GUIA  UNID  TIPO DE SERVICIO  DESTINATARIO
MUNICIPIO  VALOR  OPERADOR  ESTADO  CAUSAL  FECHA  INGRESO
```

Reglas aplicadas desde los reportes descargados:

- `SERVICIO`: toma la marca `TG` (por ejemplo `RR`) cuando existe.
- `TIPO DE SERVICIO`: toma el tipo `PT`, `MT`, `DE`, etc.
- `GUIA`: se guarda sin guiones y sin cero inicial.
- `VALOR`: si es cero, se muestra como `$ -`.
- `OPERADOR`, `ESTADO`, `CAUSAL` e `INGRESO`: quedan vacios al consolidar.
- Solo se consolidan las filas con estado de movimiento `N`; las demas se guardan en `movimientos otros estado DD mes.xlsx`.

## Configuracion

`config/settings.toml` (creado a partir de `settings.example.toml`) define remitentes de Gmail, zona horaria, rutas de datos, columnas del consolidado, columnas editables y datos de la oficina (`nombre`, `admin_name`).

## Seguridad y control de versiones

- La base de datos local (`data/database/guias.db`) no se borra al importar; solo con `borrar-datos --confirmar`.
- Quedan **fuera del control de versiones**: `config/settings.toml`, `config/credentials.json`, `config/token.json`, todo `data/`, `*.egg-info/` y artefactos de Python (`.venv/`, `__pycache__/`, `*.pyc`).
- En un clon nuevo hay que copiar `config/settings.example.toml` a `config/settings.toml` antes de ejecutar.
