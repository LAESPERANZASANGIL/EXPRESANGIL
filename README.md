# Gestor de guias Envia

Aplicacion local en Python para importar planillas descargadas manualmente, consolidar guias, conservar la informacion hasta que el usuario decida borrarla, generar el archivo de trabajo y permitir editar `OPERADOR`, `ESTADO` y `CAUSAL`.

## Objetivo

Automatizar el proceso diario:

1. Descargar manualmente la planilla desde el sistema o correo.
2. Importar la planilla al programa.
3. Leer la planilla y extraer las columnas necesarias.
4. Conservar la informacion ya importada en la base local.
5. Actualizar guias repetidas por `GUIA` sin borrar datos anteriores.
6. Mantener `OPERADOR`, `ESTADO` y `CAUSAL` ya editados.
7. Dejar en el consolidado solo las guias cuyo estado de movimiento sea `N`.
8. Generar una copia descargable de los movimientos con estados diferentes a `N`.
9. Generar un Excel final, por ejemplo `09 junio.xlsx`.
10. Usar ese Excel como archivo de trabajo.
11. Permitir editar operador, estado y causal por guia o masivamente.
12. Generar informes generales y por operador.
13. Borrar la informacion solo cuando el usuario ejecute la opcion de borrado.

## Arquitectura

```text
gestor_guias_envia/
├── config/
│   ├── settings.example.toml
│   └── credentials.example.json
├── data/
│   ├── database/
│   └── output/
├── src/
│   └── gestor_guias/
│       ├── app.py
│       ├── config.py
│       ├── gmail_client.py
│       ├── excel_processor.py
│       ├── repository.py
│       ├── exporter.py
│       ├── reports.py
│       └── editor_gui.py
├── tests/
│   └── test_excel_processor.py
├── .gitignore
├── pyproject.toml
└── README.md
```

## Tecnologias recomendadas

- **Python 3.12+**: lenguaje principal.
- **pandas**: lectura, limpieza y union de planillas Excel.
- **openpyxl**: motor para leer y crear archivos `.xlsx`.
- **xlrd**: lectura de archivos `.xls` antiguos como los reportes de Colvanes.
- **SQLite**: base de datos local para guardar guias y ediciones.
- **Tkinter**: interfaz grafica simple incluida con Python.
- **pytest**: pruebas del procesamiento de planillas.

## Preparacion

1. Crear entorno virtual:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Instalar dependencias:

```bash
pip install -e ".[dev]"
```

3. Crear configuracion local:

```bash
cp config/settings.example.toml config/settings.toml
```

## Como ejecutarlo

Forma recomendada en Windows:

1. Abre la carpeta del proyecto.
2. Da doble clic en `INICIAR_GESTOR.bat`.
3. Elige una opcion del menu.

El primer inicio crea la configuracion local e instala el programa si hace falta.

Importar planillas descargadas manualmente:

```bash
python -m gestor_guias.app importar "ruta/archivo1.xls" "ruta/archivo2.xls" --fecha 2026-06-09
```

Tambien puedes usar el comando anterior `procesar-archivos`; funciona igual que `importar`:

```bash
python -m gestor_guias.app procesar-archivos "ruta/archivo1.xls" --fecha 2026-06-09
```

Abrir la interfaz para editar operador, estado y causal:

```bash
python -m gestor_guias.app editar
```

En el editor puedes:

- Seleccionar varias guias con `Ctrl` o `Shift`.
- Escribir `OPERADOR`, `ESTADO` y `CAUSAL`.
- Presionar `Aplicar a seleccionadas`.
- Pegar una lista de guias en el cuadro inferior y usar `Aplicar a lista`.

Exportar nuevamente el Excel con la informacion guardada:

```bash
python -m gestor_guias.app exportar --fecha 2026-06-09
```

Generar informes desde el consolidado:

```bash
python -m gestor_guias.app informes "data/output/09 junio.xlsx" --fecha 2026-06-09
```

Borrar toda la informacion guardada solo cuando el usuario lo decida:

```bash
python -m gestor_guias.app borrar-datos --confirmar
```

## Flujo de datos

Entrada:

- Planillas Excel descargadas manualmente por el usuario.

Proceso:

- Lectura de columnas esperadas.
- Soporte para reportes Colvanes donde `PLANILLA` y `FECHA` vienen en la cabecera.
- Normalizacion de `GUIA` al formato numerico del consolidado diario.
- Filtro de guias activas: solo quedan movimientos con estado `N`.
- Exportacion separada de movimientos con estado distinto de `N`.
- Normalizacion de nombres.
- Union de planillas.
- Limpieza de duplicados por `GUIA`.
- Guardado acumulativo en SQLite.
- Conservacion de datos hasta borrado manual.
- Exportacion a Excel.
- Generacion de informes desde el consolidado diario.

Salida:

- Excel final en `data/output/`.
- Excel de informes en `data/output/`.
- Base de datos local en `data/database/guias.db`.

## Estructura del consolidado diario

El archivo diario conserva exactamente estas columnas:

```text
PLANILLA
SERVICIO
GUIA
UNID
TIPO DE SERVICIO
DESTINATARIO
MUNICIPIO
VALOR
OPERADOR
ESTADO
CAUSAL
FECHA
INGRESO
```

Reglas aplicadas desde los reportes descargados:

- `SERVICIO`: toma la marca `TG`, por ejemplo `RR`, cuando existe.
- `TIPO DE SERVICIO`: toma el tipo `PT`, `MT`, `DE`, etc.
- `GUIA`: se guarda sin guiones y sin cero inicial.
- `VALOR`: si el valor es cero, se muestra como `$ -`.
- `OPERADOR`, `ESTADO`, `CAUSAL` e `INGRESO`: quedan vacios al consolidar.
- Si el archivo descargado trae `ESTADO` o `ESTADO MOVIMIENTO`, solo se consolidan las filas con valor `N`.
- Las filas con otros estados se guardan en `movimientos otros estado DD mes.xlsx`.

## Seguridad

La base de datos local queda en `data/database/guias.db`. Esa informacion no se borra al importar nuevas planillas. Solo se elimina con el comando `borrar-datos --confirmar`.

Los archivos de configuracion local, la base de datos y los archivos de salida quedan excluidos del control de versiones.
