# CLAUDE.md

Guia para trabajar en este repositorio. El proyecto esta en espanol; se desarrolla en Windows y corre en produccion en un VPS Linux.

## Que es

Gestor diario de guias de la oficina de Envia (Colvanes) en San Gil. Importa planillas Excel descargadas a mano, las consolida en SQLite, permite editar/seguir cada guia, gestiona la operacion de los repartidores (salidas, novedades, cierre de recaudo) y genera informes en Excel/PDF. Incluye un panel web servido desde la stdlib.

**Produccion**: VPS en `https://expresangil.cloud`, servicio systemd `gestor-guias.service` desde `/root/gestor_guias`.

## Como correr y probar

- **Entorno local**: Windows + PowerShell. El interprete vive en `.venv\Scripts\python.exe`.
- **Setup inicial**: doble clic en `INICIAR_GESTOR.bat` (crea `.venv`, instala con `pip install -e .`, copia `settings.toml`). Manual: `pip install -e ".[dev]"`.
- **Tests**: `.venv\Scripts\python.exe -m pytest` (config en `pyproject.toml`: `pythonpath=["src"]`, `testpaths=["tests"]`). Hoy son 231 tests (18 se saltan sin Postgres; 6 mas sin navegador).
- **CLI**: `python -m gestor_guias.app <comando>` — la fachada de negocio. Comandos: `consolidar`, `importar`, `procesar-archivos`, `exportar`, `informes`, `borrar-datos`, `informe-operador`, `informe-salidas`, `informe-entregas`, `informe-dia`, `informe-recaudo`, `informe-relacion-ce-rr`, `informe-devoluciones`, `informe-mensual`, `editar`, `operador-crear`, `operador-listar`, `operador-eliminar`, `respaldo-externo`, `migrar-a-supabase`.
- **Panel web**: `PANEL.bat` -> `python -m gestor_guias.launcher_server` -> `http://127.0.0.1:8765/`.

### Despliegue en el VPS (manual, por SSH)

```bash
cd /root/gestor_guias
git fetch origin main
git reset --hard origin/main
systemctl restart gestor-guias.service
```

Las **sesiones sobreviven al reinicio** desde que viven en la tabla `sesiones`, asi que desplegar ya no expulsa a nadie. Aun asi conviene hacerlo fuera del horario de operacion: el servicio queda unos segundos abajo y una peticion en curso (un informe, un cierre) se corta.

Tras un cambio de frontend hay que recargar con **Ctrl+F5**: el navegador conserva el `.js` y el `.css` viejos y la pagina parece no haber cambiado.

## Arquitectura (importante para no romper nada)

- **`app.py`** es la CLI con `argparse`. Toda accion (importar, exportar, informes, operadores) es un subcomando aqui.
- **`launcher_server.py`** es el panel web: handler HTTP (`http.server`, sin frameworks). Llama a `app.py` por `subprocess` (`run_command`) para informes/importar/exportar, e invoca directamente `operadores.py` + `repository.py` para login, salidas, novedades, cierres y acciones de admin. Las sesiones viven en la tabla `sesiones` (cookie `session`) y **sobreviven a un reinicio**: de la cookie se guarda solo el hash SHA-256, porque los respaldos salen del servidor y una copia no debe entregar sesiones vivas. Vencen a las 12 horas (`SESSION_MAX_EDAD_SEGUNDOS`), medidas contra el reloj y no con `time.monotonic()`, que se reinicia con el proceso. El hilo de respaldo barre las vencidas. Tambien arranca el hilo de respaldo periodico.
- **`launcher/`** es frontend estatico (HTML/CSS/JS plano, sin build). Se sirve desde `STATIC_FILES` en `launcher_server.py`; **si agregas un archivo nuevo hay que registrarlo en ese diccionario** o devuelve 404.
- **`config.py`** carga `config/settings.toml` con `tomllib` a dataclasses congeladas (`Settings`). Rutas relativas se resuelven contra la raiz del repo (`BASE_DIR`).
- **`repository.py`** es el unico acceso a SQLite. `initialize()` hace migracion ligera (crea tablas y agrega columnas faltantes).
- **`excel_processor.py`** lee/normaliza/une planillas. `normalize_guide` quita guiones y cero inicial — es la forma canonica de la guia en toda la app.
- **`reports.py`** centraliza constantes y utilidades compartidas: `ESTADO_RECAUDO = "E"`, `DENOMINACIONES`, `value_to_number`, `normalize_dataframe`, `filter_by_date`, `apply_report_format`. `recaudo.py`, `relacion_ce_rr.py`, `devoluciones.py` y `operadores.py` importan de aqui — no dupliques esas utilidades.
- **`operadores.py`**: hashing PBKDF2-SHA256, parseo de guias pegadas (`parse_guides`) y la maquina de estados de la operacion. Importa de `reports.py`, nunca al reves (evitar import circular; por eso `DENOMINACIONES` esta duplicada con comentario).
- **`consulta_publica.py`**: la raiz `/` del dominio es publica para que el cliente final consulte su guia. El panel interno vive en `/panel`. `describir_estado(guia, operador, oficina)` arma el mensaje: si la guia esta en reparto (`R`) informa el nombre y el celular del repartidor; si sigue en la oficina da la direccion y el telefono de `[oficina]` en `settings.toml` (`direccion`, `telefono`). El celular sale de la columna `celular` de `operadores`, que se llena en Modulo Usuarios -> Datos laborales del empleado.

### Tablas SQLite

| Tabla | PK | Para que |
|---|---|---|
| `guias` | `guia` | Zona de trabajo: guias vivas del dia |
| `guias_archivo` | `guia` | Historico de entregadas archivadas al cerrar el dia |
| `operadores` | `usuario` | Usuarios/empleados: `rol`, documentos, `celular` (se le muestra al cliente) y datos laborales (`apellidos`, `fecha_ingreso`, `fecha_retiro`, `tipo_contrato`, `salario_base`, `auxilio_transporte`, `valor_encomienda`) |
| `cierres_operador` | `fecha, operador` | Cierre diario por repartidor (incluye `denominaciones` y `gastos_detalle` en JSON) |
| `cierres_generales` | `fecha` | Conteo de billetes del cierre general de la oficina |
| `prestamos` | `id` | Prestamos (2% mensual) y adelantos de nomina |
| `prestamo_abonos` | `id` | Abonos aplicados a cada prestamo o adelanto |
| `nomina` | `periodo, empleado` | Liquidacion mensual por empleado |
| `liquidaciones_semanales` | `semana_inicio, empleado` | Pago semanal de contratistas por encomienda |
| `liquidaciones_laborales` | `id` | Liquidacion definitiva al retirar a un empleado |
| `sesiones` | `token_hash` | Sesiones del panel, para que sobrevivan a un reinicio |
| `movimientos` | `id` | Ingresos y egresos digitados (libro de caja de la oficina) |

**Renombrar a un empleado**: `guias`, `guias_archivo`, `cierres_operador`, `prestamos`, `nomina`, `liquidaciones_semanales` y `liquidaciones_laborales` guardan el **nombre** del empleado como texto, no su `usuario`. Por eso el cambio de nombre pasa siempre por `repository.renombrar_operador()`, que arrastra esas siete tablas en la misma transaccion y rechaza un nombre ya usado por otro. Nunca actualizar `operadores.nombre` a secas.

## Soporte de Supabase (listo, pero NO activo)

**La aplicacion corre sobre SQLite y esa es la decision vigente.** El soporte de Postgres/Supabase esta completo y probado, y conmutar toma diez minutos, pero no se usa. Conviene entender por que antes de reactivarlo.

**Por que se hizo**: las corrupciones repetidas de la base (`database disk image is malformed`). **Por que no se conmuto**: esa causa ya estaba resuelta. Eran 43 conexiones SQLite que no se cerraban, agotaban los descriptores del sistema y producian el `disk I/O error` que terminaba en corrupcion; se corrigio con `contextlib.closing`. Sumado a los respaldos fuera del servidor, el seguro que daba Supabase ya se tenia por otra via.

**El costo medido** (300 guias, contra Postgres local, extrapolando ~100 ms de ida y vuelta a Oregon):

| | SQLite | Supabase | Supabase reutilizando conexion |
|---|---|---|---|
| Abrir conexion | 0 ms | ~300 ms (TLS son 3 viajes) | 0 ms |
| Consultar | 0,4 ms | ~100 ms | ~100 ms |
| **Por cada clic** | **~5 ms** | **~400 ms** | **~100 ms** |

Cada operacion del panel abre **una sola** conexion y hace 1-2 consultas, asi que el costo no se multiplica por guia; pero esos 400 ms se pagan en cada clic. A eso se suma que sin internet la oficina no podria trabajar.

**Que hay listo, si algun dia se reactiva**:

- `supabase/migrations/0001_esquema_inicial.sql`: esquema espejo del de SQLite, **ya aplicado** al proyecto `EXPRESANGIL` (plan Pro). Fechas como `TEXT` ISO porque toda la app las compara como texto; importes en `BIGINT`.
- **RLS activo y sin politicas en las 10 tablas**: hay salarios, cedulas y prestamos, y Supabase publica las tablas por PostgREST con la clave anonima, que es publica por diseño. La app entra por conexion directa, que no pasa por RLS. **No desactivar RLS** para "que funcione algo": agregar politicas explicitas.
- `migrar-a-supabase` copia las 10 tablas en una transaccion, sin tocar el origen, y muestra el cuadre. Conserva los ids con `OVERRIDING SYSTEM VALUE` y reajusta la secuencia con `setval`: sin eso los abonos colgarian de otro prestamo y el siguiente registro chocaria por id repetido.
- **La cadena de conexion va en `EXPRESANGIL_DB_DSN`, nunca en `settings.toml`**, que se versiona en GitHub y publicaria la contraseña.
- Desde el VPS hay que entrar por el **pooler** (`...pooler.supabase.com`): la conexion directa solo responde por IPv6. Por eso `abrir_postgres()` pasa `prepare_threshold=None`, porque el pooler en modo transaccion no admite sentencias preparadas.
- `psycopg` es una dependencia **opcional** (`pip install -e ".[supabase]"`) y se importa de forma diferida: sin el, todo lo demas funciona igual.

**`repository.py` habla los dos motores** y eso hay que respetarlo al tocarlo, aunque hoy solo se use SQLite:

- Nada de `rowid` ni de `PRAGMA` fuera de `initialize()` y los respaldos: no existen en Postgres. `initialize()` no hace nada en Postgres, porque alli el esquema lo gobierna `supabase/migrations/`.
- Para leer filas, `connection.consultar()` / `consultar_una()`, que devuelven diccionarios en ambos. `execute().fetchall()` entrega tuplas en psycopg y `fila["columna"]` revienta.
- Para el id recien insertado, `connection.insertar_devolviendo_id()`: `lastrowid` no existe en Postgres.
- **`Conexion` no soporta `with` a proposito**: en sqlite3 eso confirma pero **no cierra**, que es lo que corrompio la base. Se usa siempre `transaccion()`, que ademas cierra.

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

  **Gastos del cierre**: **ninguno es obligatorio**. El formulario arranca con **una sola linea vacia** y el operador agrega las que necesite con "+ Agregar gasto", hasta `MAX_GASTOS = 5` (el boton se deshabilita ahi); cada linea de mas se puede quitar, y la ultima que queda no, porque es el espacio en blanco del dia sin gastos. Cada linea lleva un concepto de la lista cerrada `CONCEPTOS_GASTO` (`operadores.py`: COMBUSTIBLE VAN, COMBUSTIBLE TURBO, CAMBIO DE ACEITE, MANTENIMIENTO MOTO, OTROS MANTENIMIENTOS) y su valor. Se guardan en `cierres_operador.gastos_detalle` (JSON) y su suma es `gastos`, que **se resta del efectivo** que el repartidor entrega, para que el cierre no quede descuadrado. El servidor valida concepto, valor y cantidad (`normalizar_gastos`), no solo el frontend. Al **regenerar** un cierre sin mandar detalle se conserva el que ya tenia.

  **Guias repetidas en Salidas**: escanear dos veces el mismo paquete cuadra el conteo con lo escaneado pero no con lo que el repartidor lleva encima. Por eso las repetidas se resaltan en rojo **dentro del campo** y el boton queda deshabilitado hasta corregirlas, y el servidor ademas **no registra nada** si llegan duplicadas (`guias_duplicadas()`), por si alguien salta el frontend. El campo siempre dice cuantas encomiendas va a sacar.

  Un `textarea` no puede pintar texto de colores, asi que el resaltado es una **capa espejo** detras del campo con el mismo texto y las repetidas marcadas. Las dos capas comparten tipografia, tamaño, interlineado, borde y relleno: **si se cambia uno hay que cambiar el otro**, o la marca roja señala el numero equivocado. Hay un test que lo comprueba en el navegador.

  La normalizacion del JavaScript debe seguir a `normalize_guide` (rellena con ceros hasta 12 digitos, **no** los quita): si no, `064108001` y `64108001` parecerian guias distintas.
- **Ingresos y Egresos** (`/ingresos-egresos`, solo admin): libro de caja de la oficina. **Todo se digita**, salvo los egresos que se traen solos de donde ya viven, para no teclearlos dos veces:
  - la **nomina** liquidada del mes (`nomina.total_pagar`),
  - los **gastos** del cierre de cada repartidor, **una linea por concepto** (`cierres_operador.gastos_detalle`; los cierres viejos sin detalle caen en `GASTOS SIN DETALLE`),
  - los **adelantos de salario** entregados en el cierre (`ADELANTOS DEL CIERRE`),
  - los **desembolsos** de `prestamos` del mes, agrupados por tipo (`PRESTAMOS ENTREGADOS`, `ADELANTOS ENTREGADOS`), sin contar los `ANULADO`.

  Llegan marcados como `automatico` y **no se guardan** en `movimientos`: su fuente de verdad sigue siendo la nomina, el cierre y el prestamo, y por eso no se pueden borrar desde esta pantalla.

  Es un **libro de caja**, no contabilidad de causacion: entregar un prestamo o un adelanto **es** salida de dinero y por eso entra. No hay doble conteo, porque la nomina que entra ya llega **neta** del descuento.

  **Lo que a proposito NO entra solo**: el **recaudo** no es ingreso de la oficina, es plata del cliente que se le entrega a Envia — el ingreso real es la comision, y se digita.
- **Prestamos y Adelantos** (`/prestamos`, solo admin): registro de prestamos y adelantos, abonos, saldos con interes e informe mensual.
- **Nomina** (`/nomina`, solo admin): liquidacion mensual de los empleados con contrato **NOMINA**, con descuento automatico de prestamos e informes Excel/PDF.
- **Liquidaciones** (`/liquidaciones`, solo admin): pago semanal de los de contrato **SERVICIOS** (por encomienda entregada) y liquidacion laboral en sus cuatro clases (anual, retiro voluntario, retiro forzoso, pension).
- **Modulo Usuarios** (`/usuarios`, solo admin): usuarios del sistema y **datos laborales del empleado** (nombre, contrato, fechas, cedula, celular, salario o valor por encomienda). El boton **Editar** de la tabla apunta tambien la seccion de datos laborales a esa persona. **Dashboard** (`/dashboard`, solo admin).
- **Consulta publica** (`/`): el cliente final consulta el estado de su guia. Es la unica pagina pensada para gente de fuera, y no reusa los estilos del panel (`consulta.html` + `consulta.css`): barra de marca, buscador destacado que acompaña el desplazamiento y en el celular va de primero, datos de contacto accionables (la direccion abre el mapa, los telefonos marcan) e instructivo del formato de la guia. El acceso del personal es un boton delineado debajo del buscador.

  **Cuidado al tocarla**: `style.css` estiliza todo `header` como columna centrada para el panel, y esa regla alcanza a la barra de marca — `.barra-marca` la neutraliza a proposito. Los IDs del HTML son el contrato con `consulta.js`: si se renombra uno hay que ajustar el JS.

## Informes

- **`informe diario dd mes.xlsx`**: unifica recaudo e informe del dia. Hojas: `RECAUDO` (por operador, con la tabla del cierre general y el resumen de verificacion), `RESUMEN`, `POR ESTADO`, `POR MUNICIPIO`, `POR OPERADOR` (solo guias `E`) y `DETALLE`. Lo generan tanto `informe-dia` como `informe-recaudo`.
- **`entregas {operador} dd mes.xlsx`**: hojas `ENTREGAS`, `NOVEDADES` (RO/N/D con causal) y `CIERRE` (resumen y conteo de billetes).
- **`informe mensual entregadas {mes} {anio}`** (Excel y PDF) e **informes de rendimiento mensual** (PDF por operador tipo ficha, y PDF horizontal de todos).
- **`relacion guias ce y rr dd mes.xlsx`**: solo servicios CE/RR entregados con valor > 1; resta el link de Envia. **Es el unico informe que no lleva unidades** (decision del usuario).

## Prestamos, adelantos y nomina (`nomina.py`)

- **Prestamo**: causa **2% mensual sobre el saldo de capital** (`TASA_INTERES_MENSUAL`). El mes del desembolso no causa interes; cada mes posterior si, sobre el capital vigente. Los abonos se aplican **primero a intereses** y el remanente a capital.
- **Adelanto de nomina**: sin interes; se descuenta de la nomina del mes.
- **Adelanto de salario del cierre**: el que el repartidor recibe al cerrar el dia (`cierres_operador.adelanto_salario`) tambien se descuenta de la nomina del mes. `nomina.detalle_descuento_nomina()` devuelve `cuotas_prestamos`, `adelantos_cierre` y `total`; `descuento_nomina_empleado()` es su total y es lo que usa la liquidacion.
- `estado_prestamo()` recorre mes a mes hasta la fecha de corte y devuelve saldo de capital, intereses causados/pendientes y la cuota sugerida del mes (capital/cuotas + interes).
- **Nomina mensual**: salario prorrateado sobre `DIAS_MES_NOMINA = 30`, mas auxilio de transporte (tambien prorrateado) y bonificaciones; menos salud 4%, pension 4%, cuotas de prestamos, adelantos de salario del cierre y otros descuentos. **Salud y pension se calculan solo sobre el salario**, no sobre el auxilio.
- Los empleados salen de la tabla `operadores` (columnas `salario_base`, `auxilio_transporte`, `cedula`, `cargo`).
- Informes: `prestamos y adelantos {mes} {anio}.xlsx` y `nomina {mes} {anio}` (Excel y PDF).

## Tipos de contrato y liquidaciones (`liquidaciones.py`)

Cada empleado tiene un `tipo_contrato` que define como se le paga:

- **NOMINA**: salario mensual. Aparece en el modulo de Nomina.
- **SERVICIOS**: se le paga un valor fijo por cada encomienda entregada (`valor_encomienda`). Aparece en la liquidacion semanal.

**Liquidacion semanal de servicios**: la semana va de **lunes a domingo** (`inicio_de_semana`). Cuenta las guias en estado `E` por **F_ENTREGA** en `guias` **y** `guias_archivo` (`contar_entregas_periodo`), para que una liquidacion vieja siga dando el mismo resultado despues de archivar. Se descuentan las cuotas de prestamos/adelantos pendientes.

**Liquidacion laboral**: usa la convencion de **360 dias** (`dias_laborales_360`, meses de 30):
- Cesantias = (salario + auxilio) x dias / 360
- Intereses de cesantias = cesantias x dias x 12% / 360
- Prima = (salario + auxilio) x dias de prima / 360
- Vacaciones = salario x dias / 720 (solo salario, sin auxilio)
- Mas indemnizacion, menos otros descuentos.

Los dias de prima y de vacaciones se pueden ajustar; por defecto toman todo el tiempo trabajado.

**Clases de liquidacion** (`TIPOS_LIQUIDACION`). **Todas** liquidan cesantias, intereses, prima y vacaciones de ley sobre el periodo indicado; lo que cambia es el motivo y la indemnizacion:

| Clase | Cesantias, intereses, prima y vacaciones | Indemnizacion |
|---|---|---|
| `ANUAL` (corte de fin de anio, el contrato sigue) | si | no |
| `RETIRO_VOLUNTARIO` (renuncia) | si | no |
| `RETIRO_FORZOSO` (despido sin justa causa) | si | **si** |
| `PENSION` (se pensiona) | si | no |

En `ANUAL` **las cesantias se reparten 50/50**: la mitad se le entrega al empleado y la mitad se consigna al fondo de cesantias (`PORCENTAJE_CESANTIAS_CONSIGNADAS_ANUAL`). En las clases de retiro se le pagan completas. El calculo devuelve `cesantias_pagadas`, `cesantias_consignadas`, `total_pagar` (lo liquidado) y `total_al_empleado` (lo que recibe en mano).

En `ANUAL` las dos fechas delimitan **el anio a liquidar**, no el ingreso y retiro del empleado (el frontend renombra los campos a "DESDE/HASTA" y propone el anio en curso, o desde la fecha de ingreso si entro a mitad de anio).

La indemnizacion solo existe en `RETIRO_FORZOSO`. `calcular_indemnizacion()` sugiere la del **art. 64 del CST** para contrato indefinido con salario inferior a 10 SMMLV: **30 dias de salario por el primer anio y 20 por cada anio siguiente**, proporcional por fraccion. El admin puede escribir otro valor; si deja el campo vacio se usa el sugerido.

**Ambas quedan almacenadas** (`liquidaciones_semanales`, `liquidaciones_laborales`) con su fecha de registro, como soporte de los pagos realizados.

## Respaldos e integridad de la base

Historial: la base se ha corrompido varias veces en produccion (`database disk image is malformed`, `disk I/O error`), por reinicios inesperados del VPS y por conexiones SQLite que no se cerraban. Protecciones actuales:

- `PRAGMA synchronous=FULL` y `journal_mode=WAL` en cada conexion.
- **Todas las conexiones se cierran** con `contextlib.closing` (`with closing(self._connect()) as connection, connection:`). `with` a secas sobre una conexion sqlite3 **no la cierra** — nunca volver a ese patron.
- Respaldo antes de cada borrado (`_backup_antes_de_borrar`, 10 copias rotadas) y respaldo periodico cada 2 horas (`respaldo_periodico`, 24 copias). Los periodicos **no se generan si la base esta danada**, para no desplazar por rotacion a las copias sanas.
- `verificar_integridad()` corre al arrancar el panel y avisa en el log.
- Todo vive en `data/database/backups/`.
- **Copia fuera del servidor**, por dos vias, ambas sobre `copia_para_descarga()` (copia verificada; si la base esta danada falla en vez de entregar un respaldo inutil):
  - **Manual**: boton "Descargar respaldo" en Inicio (`/api/respaldo/descargar`, solo admin). Queda en auditoria.
  - **Automatica, por comando** (`respaldo_externo.py`): el hilo de respaldo periodico ejecuta cada `[respaldo_externo].horas` el comando configurado, con `{archivo}` reemplazado por la ruta del respaldo. Se dejo como comando y no como integracion con un proveedor **para no tener que registrar la aplicacion en Google Cloud ni en Azure** (decision del usuario) y para poder cambiar de destino sin tocar codigo: con `rclone` cubre OneDrive de Office 365, Drive o S3; con `scp`, otro servidor. Se parte con `shlex` y se corre sin `shell=True`, porque el nombre del respaldo lleva espacios. Un fallo del destino solo se avisa por log, nunca tumba el panel, y el modulo se importa de forma diferida.

Para recuperar una base danada: elegir el respaldo sano mas reciente (`PRAGMA quick_check`) o rescatar lo legible copiando tabla por tabla a una base nueva.

## Convenciones del codigo

- Comentarios y mensajes al usuario en **espanol**; identificadores en su mayoria en espanol (`registrar_salidas`, `cerrar_dia`). Mantener el estilo del archivo que tocas.
- `from __future__ import annotations` al inicio de cada modulo; type hints en firmas.
- Solo stdlib + las deps de `pyproject.toml` (pandas, openpyxl, xlrd, reportlab, google-*). No metas frameworks web ni ORMs.
- Nombres de archivos de salida en espanol con dia y mes (ej. `informe diario 09 junio.xlsx`); el mes sale de `MONTHS_ES` en `exporter.py`.
- Moneda colombiana: separador de miles con punto (`format_currency_co`).
- Endpoints de admin: proteger siempre con `self._require_admin()`. Acciones destructivas: `registrar_auditoria(...)` y doble confirmacion en el frontend.
- Los campos de un `.opcion` comparten una caja en `style.css` que lista los `type` uno por uno. Si usas un `type` nuevo, agregalo a ese bloque y al `:focus`, o queda con el estilo por defecto del navegador.
- `.tabla-guias` trae `width: 100%`, que aprieta las columnas en vez de desbordar: una tabla ancha que deba tener scroll horizontal necesita `width: auto; min-width: 100%` (ver `.tabla-nomina`/`.tabla-prestamos`).

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
- Liquidacion semanal de contratistas por encomiendas entregadas y liquidacion laboral en sus cuatro clases (corte anual, retiro voluntario, retiro forzoso con indemnizacion de ley, y pension), todas con prima y vacaciones de ley y almacenadas como soporte de pago.
- Gestion de usuarios con roles y auditoria de acciones destructivas, y cambio de nombre del empleado que arrastra todo su historial.
- Aviso de guias repetidas al registrar salidas, resaltadas en el campo y bloqueadas tambien en el servidor.
- Libro de caja de la oficina: ingresos y egresos digitados, con la nomina, los gastos del cierre desglosados por concepto, los adelantos de salario y los desembolsos de prestamos sumados automaticamente.
- Gastos del cierre con concepto de una lista cerrada (hasta 5 por cierre), descontados del efectivo del repartidor y llevados a contabilidad por concepto.
- Adelantos de salario del cierre y cuotas de prestamos descontados automaticamente de la nomina del mes.
- Sesiones persistentes: un despliegue o un reinicio del VPS ya no expulsa a los usuarios a mitad de la jornada.
- Consulta publica de guias para el cliente final, con el repartidor y su celular cuando la guia va en reparto, o la direccion de la oficina cuando sigue alli. Pagina rediseñada para el publico, legible en celular.
- Suite de 231 tests en verde (213 corren siempre; 18 con un Postgres de pruebas y 9 con Chromium).

## Que se puede mejorar

**Robustez / operacion**
- Despliegue manual por SSH. Un timer de systemd que haga `fetch`/`reset`/`restart` automatizaria el paso mas repetitivo.
- Los reinicios inesperados del VPS siguen siendo un tema de infraestructura con el proveedor. La causa de codigo (conexiones sin cerrar) ya esta corregida, y por eso se decidio **no** conmutar a Supabase: ver "Soporte de Supabase".
- La copia externa automatica avisa sus fallos solo por el log del servicio: si lleva dias sin salir, nadie se entera desde el panel.

**Calidad de codigo**
- `launcher_server.py` supera las 1.300 lineas con toda la logica HTTP en un solo `do_POST`/`do_GET`. Separarlo por modulos (rutas de admin, operador, informes) lo haria mantenible.
- Los tests del servidor HTTP cubren las sesiones (`test_sesiones_persistentes.py`) y el resaltado de salidas en Chromium (`test_salidas_navegador.py`); ambos levantan el panel de verdad. El resto de endpoints se prueba a mano; las regresiones del panel (403 al descargar, cierre general en cero) se habrian detectado extendiendo ese patron.
- Archivos muertos: `launcher/zona.html`, `zona.css`, `zona.js` no estan en `STATIC_FILES` y no se sirven. `editor_gui.py` (Tkinter) quedo obsoleto tras la Zona de Trabajo web y es el unico consumidor de `generate_daily_report`.
- `run_command` lanza un subproceso Python por cada informe; llamar a las funciones directamente seria mas rapido y daria mejores errores.

**Funcionalidad**
- Ingresos y Egresos no genera todavia un informe en Excel ni compara meses; solo se consulta en pantalla.
- El "deshacer" es de un solo nivel y en memoria: se pierde al reiniciar y no cubre acciones de operadores.
- Las fechas de trabajo se refrescan por reloj del navegador; un desfase de zona horaria en el equipo del operador aun podria guardar un cierre con fecha equivocada. Validarlo contra la hora del servidor seria mas seguro.
- No hay paginacion en la Zona de Trabajo: con miles de guias el navegador renderiza toda la tabla.
- La nomina no genera colilla de pago individual por empleado.
- Los abonos a prestamos se registran a mano: la nomina descuenta la cuota del mes, pero no crea el abono que baja el saldo del prestamo.
- En Prestamos el empleado se escribe en un `datalist` cuyo texto **es la clave** del registro: por eso ahi no se muestran apellidos y un error de tipeo crea un empleado fantasma. Deberia guardar el `usuario` y mostrar el nombre, como hace Nomina.
- `renombrar_operador()` arrastra el historial de la base, pero **no** los informes de Excel y PDF ya generados en `data/`, que conservan el nombre viejo.
- El nombre del empleado debe coincidir letra por letra con la columna OPERADOR de las planillas de Envia; no hay validacion que avise cuando deja de coincidir.
