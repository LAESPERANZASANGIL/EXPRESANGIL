# CLAUDE.md

Guia para trabajar en este repositorio. El proyecto esta en espanol; se desarrolla en Windows y corre en produccion en un VPS Linux.

## Que es

Gestor diario de guias de la oficina de Envia (Colvanes) en San Gil. Importa planillas Excel descargadas a mano, las consolida en SQLite, permite editar/seguir cada guia, gestiona la operacion de los repartidores (salidas, novedades, cierre de recaudo) y genera informes en Excel/PDF. Incluye un panel web servido desde la stdlib.

**Produccion**: VPS en `https://expresangil.cloud`, servicio systemd `gestor-guias.service` desde `/root/gestor_guias`.

## Como correr y probar

- **Entorno local**: Windows + PowerShell. El interprete vive en `.venv\Scripts\python.exe`.
- **Setup inicial**: doble clic en `INICIAR_GESTOR.bat` (crea `.venv`, instala con `pip install -e .`, copia `settings.toml`). Manual: `pip install -e ".[dev]"`.
- **Tests**: `.venv\Scripts\python.exe -m pytest` (config en `pyproject.toml`: `pythonpath=["src"]`, `testpaths=["tests"]`). Hoy son 111 tests.
- **CLI**: `python -m gestor_guias.app <comando>` — la fachada de negocio. Comandos: `consolidar`, `importar`, `procesar-archivos`, `exportar`, `informes`, `borrar-datos`, `informe-operador`, `informe-salidas`, `informe-entregas`, `informe-dia`, `informe-recaudo`, `informe-relacion-ce-rr`, `informe-devoluciones`, `informe-mensual`, `editar`, `operador-crear`, `operador-listar`, `operador-eliminar`.
- **Panel web**: `PANEL.bat` -> `python -m gestor_guias.launcher_server` -> `http://127.0.0.1:8765/`.

### Despliegue en el VPS (manual, por SSH)

```bash
cd /root/gestor_guias
git fetch origin main
git reset --hard origin/main
systemctl restart gestor-guias.service
```

El reinicio **cierra las sesiones activas** de admin y operadores (viven en memoria): avisar antes de desplegar en horario de trabajo.

## Arquitectura (importante para no romper nada)

- **`app.py`** es la CLI con `argparse`. Toda accion (importar, exportar, informes, operadores) es un subcomando aqui.
- **`launcher_server.py`** es el panel web: handler HTTP (`http.server`, sin frameworks). Llama a `app.py` por `subprocess` (`run_command`) para informes/importar/exportar, e invoca directamente `operadores.py` + `repository.py` para login, salidas, novedades, cierres y acciones de admin. Las sesiones viven en memoria (`SESSIONS`, cookie `session`) y se pierden al reiniciar. Tambien arranca el hilo de respaldo periodico.
- **`launcher/`** es frontend estatico (HTML/CSS/JS plano, sin build). Se sirve desde `STATIC_FILES` en `launcher_server.py`; **si agregas un archivo nuevo hay que registrarlo en ese diccionario** o devuelve 404.
- **`config.py`** carga `config/settings.toml` con `tomllib` a dataclasses congeladas (`Settings`). Rutas relativas se resuelven contra la raiz del repo (`BASE_DIR`).
- **`repository.py`** es el unico acceso a SQLite. `initialize()` hace migracion ligera (crea tablas y agrega columnas faltantes).
- **`excel_processor.py`** lee/normaliza/une planillas. `normalize_guide` quita guiones y cero inicial — es la forma canonica de la guia en toda la app.
- **`reports.py`** centraliza constantes y utilidades compartidas: `ESTADO_RECAUDO = "E"`, `DENOMINACIONES`, `value_to_number`, `normalize_dataframe`, `filter_by_date`, `apply_report_format`. `recaudo.py`, `relacion_ce_rr.py`, `devoluciones.py` y `operadores.py` importan de aqui — no dupliques esas utilidades.
- **`operadores.py`**: hashing PBKDF2-SHA256, parseo de guias pegadas (`parse_guides`) y la maquina de estados de la operacion. Importa de `reports.py`, nunca al reves (evitar import circular; por eso `DENOMINACIONES` esta duplicada con comentario).
- **`consulta_publica.py`**: la raiz `/` del dominio es publica para que el cliente final consulte su guia. El panel interno vive en `/panel`.

### Tablas SQLite

| Tabla | PK | Para que |
|---|---|---|
| `guias` | `guia` | Zona de trabajo: guias vivas del dia |
| `guias_archivo` | `guia` | Historico de entregadas archivadas al cerrar el dia |
| `operadores` | `usuario` | Usuarios/empleados: `rol`, documentos, y datos laborales (`apellidos`, `fecha_ingreso`, `fecha_retiro`, `tipo_contrato`, `salario_base`, `auxilio_transporte`, `valor_encomienda`) |
| `cierres_operador` | `fecha, operador` | Cierre diario por repartidor (incluye `denominaciones` en JSON) |
| `cierres_generales` | `fecha` | Conteo de billetes del cierre general de la oficina |
| `prestamos` | `id` | Prestamos (2% mensual) y adelantos de nomina |
| `prestamo_abonos` | `id` | Abonos aplicados a cada prestamo o adelanto |
| `nomina` | `periodo, empleado` | Liquidacion mensual por empleado |
| `liquidaciones_semanales` | `semana_inicio, empleado` | Pago semanal de contratistas por encomienda |
| `liquidaciones_laborales` | `id` | Liquidacion definitiva al retirar a un empleado |

## Estados de guia (no inventar nuevos sin confirmar)

- `N`: movimiento normal — unico estado que entra al consolidado al importar.
- `R`: en reparto (salio con el operador). Constante `ESTADO_SALIDA` en `operadores.py`.
- `RO`, `N`, `D`: novedades capturadas en el dia (`D` lleva causal de 2 digitos).
- `E`: entregada/recaudada. Constante `ESTADO_RECAUDO` en `reports.py`.
- Operadores especiales sin estado asignado: `PLANILLADA` (aun sin repartidor) y `BODEGA` (no sale a reparto).
- **Las guias en `E` estan protegidas contra borrado**: no las elimina ninguna herramienta de la Zona de Trabajo. Solo salen con "Cerrar el dia" (pasan a `guias_archivo`) o con el boton explicito "Borrar guias del mes" en Entregas del Mes.

### Fechas: F_INGRESO vs F_ENTREGA

Distincion critica y fuente de varios bugs pasados:

- **`fecha` (F_INGRESO)**: dia en que la guia entro por planilla.
- **`ingreso` (F_ENTREGA)**: dia en que se gestiono (entrega o novedad). La sella `fecha_entrega()` solo para estados de `ESTADOS_GESTION`.

La operacion del repartidor y los cierres se filtran por **F_ENTREGA**, no por fecha de planilla: una guia puede llegar un dia y entregarse otro.

## Modulos del panel web

- **Inicio** (`/panel`): importar planillas, exportar, informes y cierre general del dia.
- **Zona de Trabajo** (`/zona-trabajo`, solo admin): tabla editable con busqueda, filtros estilo Excel, orden por VALOR, edicion individual y masiva, eliminacion, deshacer la ultima modificacion, reversar/regenerar cierres de operador, simular y ejecutar el cierre del dia.
- **Entregas del Mes** (`/entregas-mes`, solo admin): consulta de entregadas del mes (archivo + zona), buscador de guia, informes finales en Excel y PDF, informes de rendimiento mensual (por operador y de todos), y borrado de las guias del mes.
- **Modulo Operadores** (`/operadores`): salidas, novedades y cierre del dia del repartidor.
- **Prestamos y Adelantos** (`/prestamos`, solo admin): registro de prestamos y adelantos, abonos, saldos con interes e informe mensual.
- **Nomina** (`/nomina`, solo admin): liquidacion mensual de los empleados con contrato **NOMINA**, con descuento automatico de prestamos e informes Excel/PDF.
- **Liquidaciones** (`/liquidaciones`, solo admin): pago semanal de los de contrato **SERVICIOS** (por encomienda entregada) y liquidacion laboral definitiva al retirar a un empleado.
- **Modulo Usuarios** (`/usuarios`, solo admin): usuarios del sistema y **datos laborales del empleado** (contrato, fechas, salario o valor por encomienda). **Dashboard** (`/dashboard`, solo admin).
- **Consulta publica** (`/`): el cliente final consulta el estado de su guia.

## Informes

- **`informe diario dd mes.xlsx`**: unifica recaudo e informe del dia. Hojas: `RECAUDO` (por operador, con la tabla del cierre general y el resumen de verificacion), `RESUMEN`, `POR ESTADO`, `POR MUNICIPIO`, `POR OPERADOR` (solo guias `E`) y `DETALLE`. Lo generan tanto `informe-dia` como `informe-recaudo`.
- **`entregas {operador} dd mes.xlsx`**: hojas `ENTREGAS`, `NOVEDADES` (RO/N/D con causal) y `CIERRE` (resumen y conteo de billetes).
- **`informe mensual entregadas {mes} {anio}`** (Excel y PDF) e **informes de rendimiento mensual** (PDF por operador tipo ficha, y PDF horizontal de todos).
- **`relacion guias ce y rr dd mes.xlsx`**: solo servicios CE/RR entregados con valor > 1; resta el link de Envia. **Es el unico informe que no lleva unidades** (decision del usuario).

## Prestamos, adelantos y nomina (`nomina.py`)

- **Prestamo**: causa **2% mensual sobre el saldo de capital** (`TASA_INTERES_MENSUAL`). El mes del desembolso no causa interes; cada mes posterior si, sobre el capital vigente. Los abonos se aplican **primero a intereses** y el remanente a capital.
- **Adelanto de nomina**: sin interes; se descuenta de la nomina del mes.
- `estado_prestamo()` recorre mes a mes hasta la fecha de corte y devuelve saldo de capital, intereses causados/pendientes y la cuota sugerida del mes (capital/cuotas + interes).
- **Nomina mensual**: salario prorrateado sobre `DIAS_MES_NOMINA = 30`, mas auxilio de transporte (tambien prorrateado) y bonificaciones; menos salud 4%, pension 4%, cuotas de prestamos y otros descuentos. **Salud y pension se calculan solo sobre el salario**, no sobre el auxilio.
- Los empleados salen de la tabla `operadores` (columnas `salario_base`, `auxilio_transporte`, `cedula`, `cargo`).
- Informes: `prestamos y adelantos {mes} {anio}.xlsx` y `nomina {mes} {anio}` (Excel y PDF).

## Tipos de contrato y liquidaciones (`liquidaciones.py`)

Cada empleado tiene un `tipo_contrato` que define como se le paga:

- **NOMINA**: salario mensual. Aparece en el modulo de Nomina.
- **SERVICIOS**: se le paga un valor fijo por cada encomienda entregada (`valor_encomienda`). Aparece en la liquidacion semanal.

**Liquidacion semanal de servicios**: la semana va de **lunes a domingo** (`inicio_de_semana`). Cuenta las guias en estado `E` por **F_ENTREGA** en `guias` **y** `guias_archivo` (`contar_entregas_periodo`), para que una liquidacion vieja siga dando el mismo resultado despues de archivar. Se descuentan las cuotas de prestamos/adelantos pendientes.

**Liquidacion laboral definitiva**: al retirar a un empleado. Usa la convencion de **360 dias** (`dias_laborales_360`, meses de 30):
- Cesantias = (salario + auxilio) x dias / 360
- Intereses de cesantias = cesantias x dias x 12% / 360
- Prima = (salario + auxilio) x dias de prima / 360
- Vacaciones = salario x dias / 720 (solo salario, sin auxilio)
- Mas indemnizacion, menos otros descuentos.

Los dias de prima y de vacaciones se pueden ajustar; por defecto toman todo el tiempo trabajado.

**Ambas quedan almacenadas** (`liquidaciones_semanales`, `liquidaciones_laborales`) con su fecha de registro, como soporte de los pagos realizados.

## Respaldos e integridad de la base

Historial: la base se ha corrompido varias veces en produccion (`database disk image is malformed`, `disk I/O error`), por reinicios inesperados del VPS y por conexiones SQLite que no se cerraban. Protecciones actuales:

- `PRAGMA synchronous=FULL` y `journal_mode=WAL` en cada conexion.
- **Todas las conexiones se cierran** con `contextlib.closing` (`with closing(self._connect()) as connection, connection:`). `with` a secas sobre una conexion sqlite3 **no la cierra** — nunca volver a ese patron.
- Respaldo antes de cada borrado (`_backup_antes_de_borrar`, 10 copias rotadas) y respaldo periodico cada 2 horas (`respaldo_periodico`, 24 copias). Los periodicos **no se generan si la base esta danada**, para no desplazar por rotacion a las copias sanas.
- `verificar_integridad()` corre al arrancar el panel y avisa en el log.
- Todo vive en `data/database/backups/`.

Para recuperar una base danada: elegir el respaldo sano mas reciente (`PRAGMA quick_check`) o rescatar lo legible copiando tabla por tabla a una base nueva.

## Convenciones del codigo

- Comentarios y mensajes al usuario en **espanol**; identificadores en su mayoria en espanol (`registrar_salidas`, `cerrar_dia`). Mantener el estilo del archivo que tocas.
- `from __future__ import annotations` al inicio de cada modulo; type hints en firmas.
- Solo stdlib + las deps de `pyproject.toml` (pandas, openpyxl, xlrd, reportlab, google-*). No metas frameworks web ni ORMs.
- Nombres de archivos de salida en espanol con dia y mes (ej. `informe diario 09 junio.xlsx`); el mes sale de `MONTHS_ES` en `exporter.py`.
- Moneda colombiana: separador de miles con punto (`format_currency_co`).
- Endpoints de admin: proteger siempre con `self._require_admin()`. Acciones destructivas: `registrar_auditoria(...)` y doble confirmacion en el frontend.

## Git y archivos ignorados

- **Antes de cualquier push, correr la suite completa y confirmar que esta en verde**: `.venv\Scripts\python.exe -m pytest`. Si algun test falla, NO hacer push: arreglar la causa primero. Aplica siempre, sin importar cuan pequeno parezca el cambio.
- **No versionar**: `config/credentials.json`, `config/token.json`, todo `data/`, `*.egg-info/`, `.venv/`, `__pycache__/`, `*.pyc`. Ya estan en `.gitignore`.
- `config/settings.toml` SI se versiona (decision del usuario). `settings.example.toml` es la plantilla; si cambias uno, sincroniza el otro.
- Rama principal: `main`. Remoto: `origin` (GitHub `LAESPERANZASANGIL/EXPRESANGIL`).
- No hacer commit/push salvo que el usuario lo pida.

## Al hacer cambios

- Si tocas un subcomando de la CLI, revisa si el panel lo usa (`INFORME_COMANDOS`, rutas `/api/*` en `launcher_server.py`).
- Si cambias columnas del consolidado, sincroniza `settings.example.toml` (`[excel].columns`), `repository.py` (esquema y `save_consolidated`) y el frontend.
- Si agregas un informe: modulo propio que reusa utilidades de `reports.py`, subcomando en `app.py`, entrada en `INFORME_COMANDOS` y frontend.
- Si agregas un archivo a `launcher/`, registralo en `STATIC_FILES`.
- Si agregas una tabla o columna, hazlo dentro de `initialize()` con migracion tolerante (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE` condicionado a `PRAGMA table_info`).

---

# Estado actual

## Lo que funciona

- Importacion de planillas Excel, consolidacion en SQLite y exportacion.
- Operacion completa del repartidor: salidas, novedades (RO/N/D con causal), cierre con conteo de billetes y calculo de efectivo, con simulacion previa.
- Cierre general de la oficina, con conteo persistido y reflejado en el informe diario.
- Zona de Trabajo: busqueda multi-campo, filtros estilo Excel, orden por valor, edicion individual y masiva, marcar/desmarcar, deshacer la ultima modificacion, reversar/regenerar cierres.
- Archivo historico mensual y modulo Entregas del Mes con informes Excel/PDF y estadistica por operador.
- Prestamos con interes del 2% mensual sobre saldo, adelantos de nomina, abonos e informe mensual.
- Nomina mensual con descuento automatico de las cuotas del mes e informes en Excel y PDF.
- Datos laborales por empleado (contrato de nomina o servicios, fechas, salario o valor por encomienda).
- Liquidacion semanal de contratistas por encomiendas entregadas y liquidacion laboral definitiva, ambas almacenadas como soporte de pago.
- Gestion de usuarios con roles y auditoria de acciones destructivas.
- Consulta publica de guias para el cliente final.
- Suite de 111 tests en verde.

## Que se puede mejorar

**Robustez / operacion**
- Las sesiones viven en memoria: cada despliegue expulsa a todos los usuarios y un operador con la pestana abierta pierde la sesion sin aviso claro. Persistirlas (tabla o archivo firmado) evitaria el problema.
- Despliegue manual por SSH. Un timer de systemd que haga `fetch`/`reset`/`restart` automatizaria el paso mas repetitivo.
- Los reinicios inesperados del VPS siguen siendo la causa de fondo de las corrupciones: es un tema de infraestructura con el proveedor, no del codigo.
- No hay copia de los respaldos fuera del servidor. Si el disco falla, se pierden todos.

**Calidad de codigo**
- `launcher_server.py` supera las 1.300 lineas con toda la logica HTTP en un solo `do_POST`/`do_GET`. Separarlo por modulos (rutas de admin, operador, informes) lo haria mantenible.
- No hay tests del servidor HTTP: los endpoints solo se prueban a mano. Las regresiones del panel (403 al descargar, cierre general en cero) se habrian detectado con tests de integracion.
- Archivos muertos: `launcher/zona.html`, `zona.css`, `zona.js` no estan en `STATIC_FILES` y no se sirven. `editor_gui.py` (Tkinter) quedo obsoleto tras la Zona de Trabajo web y es el unico consumidor de `generate_daily_report`.
- `run_command` lanza un subproceso Python por cada informe; llamar a las funciones directamente seria mas rapido y daria mejores errores.

**Funcionalidad**
- El "deshacer" es de un solo nivel y en memoria: se pierde al reiniciar y no cubre acciones de operadores.
- Las fechas de trabajo se refrescan por reloj del navegador; un desfase de zona horaria en el equipo del operador aun podria guardar un cierre con fecha equivocada. Validarlo contra la hora del servidor seria mas seguro.
- No hay paginacion en la Zona de Trabajo: con miles de guias el navegador renderiza toda la tabla.
- La nomina no genera colilla de pago individual por empleado.
- Los abonos a prestamos se registran a mano: liquidar la nomina no descuenta automaticamente la cuota del saldo.
