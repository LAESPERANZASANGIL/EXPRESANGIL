from __future__ import annotations

from contextlib import closing
from datetime import date, datetime
from pathlib import Path
import json
import os
import shutil
import sqlite3

import pandas as pd

from .db import POSTGRES, SQLITE, abrir_postgres, abrir_sqlite, transaccion
from .excel_processor import hoy_colombia


TABLE_NAME = "guias"

# Operador por defecto de las guias recien importadas que aun no se le
# asignan a un repartidor: siguen "en planilla", esperando salida.
OPERADOR_PLANILLADA = "PLANILLADA"

# Operador especial: guias que se quedan en bodega (no salen a reparto).
# No deben quedar con estado "N" al importar ni "R" al registrar salida.
OPERADOR_BODEGA = "BODEGA"

# Estados que representan una gestion del dia (entregada o novedad): al
# asignarlos se sella F_ENTREGA con la fecha correspondiente.
ESTADOS_GESTION = ("E", "D", "RO", "N")


def fecha_entrega(nuevo_estado: str, fecha: str | None = None) -> str:
    """Sello de F_ENTREGA: la fecha (YYYY-MM-DD 00:00:00) si el estado es de gestion, si no vacio."""
    if (nuevo_estado or "").strip().upper() not in ESTADOS_GESTION:
        return ""
    dia = (fecha or "").strip()[:10] or date.today().isoformat()
    return f"{dia} 00:00:00"



class GuiaRepository:
    """Unico acceso a datos. Habla SQLite o Postgres segun como se construya.

    Con `dsn` (o con la variable de entorno `EXPRESANGIL_DB_DSN`) trabaja
    contra Supabase; sin ella, contra el archivo SQLite de siempre. El SQL
    se escribe en un subconjunto portable y `db.py` traduce lo que cada
    motor entiende distinto.
    """

    def __init__(self, database_file: Path, dsn: str = "") -> None:
        self.database_file = Path(database_file)
        self.dsn = (dsn or os.environ.get("EXPRESANGIL_DB_DSN", "")).strip()
        self.motor = POSTGRES if self.dsn else SQLITE
        if self.motor == SQLITE:
            self.database_file.parent.mkdir(parents=True, exist_ok=True)

    @property
    def es_postgres(self) -> bool:
        return self.motor == POSTGRES

    def initialize(self) -> None:
        """Crea las tablas y agrega las columnas que falten (solo SQLite).

        En Postgres el esquema lo gobierna `supabase/migrations/`: aplicar
        migraciones desde la aplicacion, en cada llamada y desde varios
        procesos a la vez, es justo lo que no se quiere en una base
        compartida.
        """
        if self.es_postgres:
            return

        with transaccion(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS guias (
                    guia TEXT PRIMARY KEY,
                    planilla TEXT,
                    servicio TEXT,
                    unid TEXT,
                    tipo_de_servicio TEXT,
                    destinatario TEXT,
                    direccion TEXT,
                    municipio TEXT,
                    valor TEXT,
                    operador TEXT,
                    estado TEXT,
                    causal TEXT,
                    fecha TEXT,
                    ingreso TEXT
                )
                """
            )
            columnas_guias = {row[1] for row in connection.execute("PRAGMA table_info(guias)")}
            if "direccion" not in columnas_guias:
                connection.execute("ALTER TABLE guias ADD COLUMN direccion TEXT")
            if "orden_salida" not in columnas_guias:
                # Guarda el orden en que cada guia fue registrada como salida,
                # para poder listarlas en ese mismo orden en el informe de salidas.
                connection.execute("ALTER TABLE guias ADD COLUMN orden_salida INTEGER NOT NULL DEFAULT 0")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS operadores (
                    usuario TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    rol TEXT NOT NULL DEFAULT 'operador'
                )
                """
            )
            columnas = {row[1] for row in connection.execute("PRAGMA table_info(operadores)")}
            if "rol" not in columnas:
                connection.execute(
                    "ALTER TABLE operadores ADD COLUMN rol TEXT NOT NULL DEFAULT 'operador'"
                )
            for columna in ("licencia_vencimiento", "soat_vencimiento", "tecnomecanica_vencimiento"):
                if columna not in columnas:
                    connection.execute(f"ALTER TABLE operadores ADD COLUMN {columna} TEXT NOT NULL DEFAULT ''")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cierres_operador (
                    fecha TEXT NOT NULL,
                    operador TEXT NOT NULL,
                    gestionadas INTEGER NOT NULL,
                    ro INTEGER NOT NULL,
                    n INTEGER NOT NULL,
                    d INTEGER NOT NULL,
                    e INTEGER NOT NULL,
                    recaudado INTEGER NOT NULL,
                    bancos INTEGER NOT NULL,
                    nequi INTEGER NOT NULL,
                    envia INTEGER NOT NULL,
                    efectivo INTEGER NOT NULL,
                    PRIMARY KEY (fecha, operador)
                )
                """
            )
            columnas_cierre = {row[1] for row in connection.execute("PRAGMA table_info(cierres_operador)")}
            for columna in ("gastos", "adelanto_salario"):
                if columna not in columnas_cierre:
                    connection.execute(
                        f"ALTER TABLE cierres_operador ADD COLUMN {columna} INTEGER NOT NULL DEFAULT 0"
                    )
            if "denominaciones" not in columnas_cierre:
                connection.execute(
                    "ALTER TABLE cierres_operador ADD COLUMN denominaciones TEXT NOT NULL DEFAULT '{}'"
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cierres_generales (
                    fecha TEXT PRIMARY KEY,
                    denominaciones TEXT NOT NULL DEFAULT '{}',
                    efectivo_contado INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            # Prestamos y adelantos de nomina. tipo: PRESTAMO (cobra 2%
            # mensual sobre el saldo) o ADELANTO (sin interes, se descuenta
            # de la nomina del mes).
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS prestamos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    monto INTEGER NOT NULL,
                    fecha TEXT NOT NULL,
                    forma_pago TEXT NOT NULL DEFAULT '',
                    cuotas INTEGER NOT NULL DEFAULT 1,
                    observaciones TEXT NOT NULL DEFAULT '',
                    estado TEXT NOT NULL DEFAULT 'ACTIVO'
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS prestamo_abonos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prestamo_id INTEGER NOT NULL,
                    fecha TEXT NOT NULL,
                    monto INTEGER NOT NULL,
                    concepto TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS nomina (
                    periodo TEXT NOT NULL,
                    empleado TEXT NOT NULL,
                    salario_base INTEGER NOT NULL DEFAULT 0,
                    dias_trabajados INTEGER NOT NULL DEFAULT 30,
                    auxilio_transporte INTEGER NOT NULL DEFAULT 0,
                    bonificaciones INTEGER NOT NULL DEFAULT 0,
                    salud INTEGER NOT NULL DEFAULT 0,
                    pension INTEGER NOT NULL DEFAULT 0,
                    descuento_prestamos INTEGER NOT NULL DEFAULT 0,
                    otros_descuentos INTEGER NOT NULL DEFAULT 0,
                    total_pagar INTEGER NOT NULL DEFAULT 0,
                    observaciones TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (periodo, empleado)
                )
                """
            )
            # Liquidacion semanal de los contratistas por servicios: se les
            # paga por encomienda entregada (estado E) en la semana.
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS liquidaciones_semanales (
                    semana_inicio TEXT NOT NULL,
                    empleado TEXT NOT NULL,
                    entregas INTEGER NOT NULL DEFAULT 0,
                    valor_encomienda INTEGER NOT NULL DEFAULT 0,
                    subtotal INTEGER NOT NULL DEFAULT 0,
                    descuento_prestamos INTEGER NOT NULL DEFAULT 0,
                    otros_descuentos INTEGER NOT NULL DEFAULT 0,
                    total_pagar INTEGER NOT NULL DEFAULT 0,
                    forma_pago TEXT NOT NULL DEFAULT '',
                    observaciones TEXT NOT NULL DEFAULT '',
                    registrada_en TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (semana_inicio, empleado)
                )
                """
            )
            # Liquidacion laboral definitiva al retirar a un empleado.
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS liquidaciones_laborales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado TEXT NOT NULL,
                    tipo_liquidacion TEXT NOT NULL DEFAULT 'RETIRO_VOLUNTARIO',
                    fecha_ingreso TEXT NOT NULL,
                    fecha_retiro TEXT NOT NULL,
                    dias_trabajados INTEGER NOT NULL DEFAULT 0,
                    salario_base INTEGER NOT NULL DEFAULT 0,
                    auxilio_transporte INTEGER NOT NULL DEFAULT 0,
                    cesantias INTEGER NOT NULL DEFAULT 0,
                    cesantias_pagadas INTEGER NOT NULL DEFAULT 0,
                    cesantias_consignadas INTEGER NOT NULL DEFAULT 0,
                    intereses_cesantias INTEGER NOT NULL DEFAULT 0,
                    prima INTEGER NOT NULL DEFAULT 0,
                    vacaciones INTEGER NOT NULL DEFAULT 0,
                    indemnizacion INTEGER NOT NULL DEFAULT 0,
                    otros_descuentos INTEGER NOT NULL DEFAULT 0,
                    total_pagar INTEGER NOT NULL DEFAULT 0,
                    observaciones TEXT NOT NULL DEFAULT '',
                    registrada_en TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS movimientos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    categoria TEXT NOT NULL DEFAULT '',
                    descripcion TEXT NOT NULL DEFAULT '',
                    valor INTEGER NOT NULL DEFAULT 0,
                    forma_pago TEXT NOT NULL DEFAULT '',
                    registrado_por TEXT NOT NULL DEFAULT '',
                    registrado_en TEXT NOT NULL DEFAULT ''
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sesiones (
                    token_hash TEXT PRIMARY KEY,
                    usuario TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    rol TEXT NOT NULL,
                    creada_en TEXT NOT NULL,
                    expira_en TEXT NOT NULL
                )
                """
            )

            columnas_liq = {
                row[1] for row in connection.execute("PRAGMA table_info(liquidaciones_laborales)")
            }
            if "tipo_liquidacion" not in columnas_liq:
                connection.execute(
                    "ALTER TABLE liquidaciones_laborales "
                    "ADD COLUMN tipo_liquidacion TEXT NOT NULL DEFAULT 'RETIRO_VOLUNTARIO'"
                )
            for columna in ("cesantias_pagadas", "cesantias_consignadas"):
                if columna not in columnas_liq:
                    connection.execute(
                        f"ALTER TABLE liquidaciones_laborales "
                        f"ADD COLUMN {columna} INTEGER NOT NULL DEFAULT 0"
                    )

            # Datos de empleado y de nomina, sobre la tabla de operadores.
            for columna, tipo in (
                ("salario_base", "INTEGER NOT NULL DEFAULT 0"),
                ("auxilio_transporte", "INTEGER NOT NULL DEFAULT 0"),
                ("cedula", "TEXT NOT NULL DEFAULT ''"),
                ("cargo", "TEXT NOT NULL DEFAULT ''"),
                ("apellidos", "TEXT NOT NULL DEFAULT ''"),
                ("fecha_ingreso", "TEXT NOT NULL DEFAULT ''"),
                ("fecha_retiro", "TEXT NOT NULL DEFAULT ''"),
                ("tipo_contrato", "TEXT NOT NULL DEFAULT 'NOMINA'"),
                ("valor_encomienda", "INTEGER NOT NULL DEFAULT 0"),
                ("celular", "TEXT NOT NULL DEFAULT ''"),
            ):
                if columna not in columnas:
                    connection.execute(f"ALTER TABLE operadores ADD COLUMN {columna} {tipo}")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS guias_archivo (
                    guia TEXT PRIMARY KEY,
                    planilla TEXT,
                    servicio TEXT,
                    unid TEXT,
                    tipo_de_servicio TEXT,
                    destinatario TEXT,
                    direccion TEXT,
                    municipio TEXT,
                    valor TEXT,
                    operador TEXT,
                    estado TEXT,
                    causal TEXT,
                    fecha TEXT,
                    ingreso TEXT,
                    orden_salida INTEGER NOT NULL DEFAULT 0,
                    archivado_en TEXT NOT NULL DEFAULT ''
                )
                """
            )

    def save_consolidated(self, dataframe: pd.DataFrame) -> None:
        self.initialize()
        guias = [row for row in dataframe["GUIA"].astype(str) if row]
        with transaccion(self._connect()) as connection:
            placeholders = ",".join("?" * len(guias)) if guias else ""
            existentes = (
                {
                    row[0]
                    for row in connection.execute(
                        f"SELECT guia FROM guias WHERE guia IN ({placeholders})", guias
                    ).fetchall()
                }
                if guias
                else set()
            )

        records = []
        for row in dataframe.to_dict(orient="records"):
            guia = row.get("GUIA", "")
            if not guia:
                continue

            operador = row.get("OPERADOR", "")
            # Una guia que llega por primera vez (no estaba en la base) y sin
            # operador asignado queda "en planilla" en vez de en blanco; si ya
            # existia, se conserva lo que tenga (no se pisa con este valor).
            if not operador and guia not in existentes:
                operador = OPERADOR_PLANILLADA

            # Las guias de BODEGA no salen a reparto: no se les asigna estado.
            estado = "" if operador.strip().upper() == OPERADOR_BODEGA else row.get("ESTADO", "")

            records.append(
                (
                    guia,
                    row.get("PLANILLA", ""),
                    row.get("SERVICIO", ""),
                    row.get("UNID", ""),
                    row.get("TIPO DE SERVICIO", ""),
                    row.get("DESTINATARIO", ""),
                    row.get("DIRECCION", ""),
                    row.get("MUNICIPIO", ""),
                    row.get("VALOR", ""),
                    operador,
                    estado,
                    row.get("CAUSAL", ""),
                    row.get("F_INGRESO", ""),
                    row.get("F_ENTREGA", ""),
                )
            )

        with transaccion(self._connect()) as connection:
            connection.executemany(
                """
                INSERT INTO guias (
                    guia, planilla, servicio, unid, tipo_de_servicio,
                    destinatario, direccion, municipio, valor, operador, estado,
                    causal, fecha, ingreso
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guia) DO UPDATE SET
                    planilla = excluded.planilla,
                    servicio = excluded.servicio,
                    unid = excluded.unid,
                    tipo_de_servicio = excluded.tipo_de_servicio,
                    destinatario = excluded.destinatario,
                    direccion = excluded.direccion,
                    municipio = excluded.municipio,
                    valor = excluded.valor,
                    operador = CASE
                        WHEN excluded.operador != '' THEN excluded.operador
                        ELSE guias.operador
                    END,
                    estado = CASE
                        WHEN excluded.estado != '' THEN excluded.estado
                        ELSE guias.estado
                    END,
                    causal = CASE
                        WHEN excluded.causal != '' THEN excluded.causal
                        ELSE guias.causal
                    END,
                    fecha = excluded.fecha,
                    ingreso = excluded.ingreso
                """,
                records,
            )

    def list_all(self) -> list[dict]:
        self.initialize()
        with transaccion(self._connect()) as connection:
            # `rowid` es un implicito de SQLite que Postgres no tiene. Se
            # ordena por guia: es determinista en los dos motores y el orden
            # de insercion no significa nada para el negocio (la Zona de
            # Trabajo y los informes reordenan por su cuenta).
            return connection.consultar("SELECT * FROM guias ORDER BY guia")

    def obtener_guia(self, guia: str) -> dict | None:
        self.initialize()
        with transaccion(self._connect()) as connection:
            return connection.consultar_una(
                "SELECT * FROM guias WHERE guia = ?", (guia,)
            )

    def update_tracking_fields(self, guia: str, operador: str, estado: str, causal: str) -> None:
        self.initialize()
        entrega = fecha_entrega(estado)
        with transaccion(self._connect()) as connection:
            connection.execute(
                """
                UPDATE guias
                SET operador = ?, estado = ?, causal = ?, ingreso = ?
                WHERE guia = ?
                """,
                (operador, estado, causal, hoy_colombia().isoformat(), guia),
            )

    def update_guide_details(
        self,
        guia: str,
        planilla: str,
        destinatario: str,
        direccion: str,
        municipio: str,
        valor: str,
        operador: str,
        estado: str,
        causal: str,
        fecha: str | None = None,
        entrega: str | None = None,
        servicio: str | None = None,
    ) -> None:
        self.initialize()
        # F_INGRESO (columna "fecha") y F_ENTREGA (columna "ingreso") solo se
        # tocan si el editor envia un valor explicito; en caso contrario se
        # conserva el que ya tenia la guia.
        with transaccion(self._connect()) as connection:
            connection.execute(
                """
                UPDATE guias
                SET planilla = ?, destinatario = ?, direccion = ?, municipio = ?,
                    valor = ?, operador = ?, estado = ?, causal = ?,
                    fecha = COALESCE(?, fecha),
                    ingreso = COALESCE(?, ingreso),
                    servicio = COALESCE(?, servicio)
                WHERE guia = ?
                """,
                (
                    planilla, destinatario, direccion, municipio, valor,
                    operador, estado, causal, fecha, entrega, servicio or None, guia,
                ),
            )

    def update_many_tracking_fields(
        self,
        guias: list[str],
        operador: str,
        estado: str,
        causal: str,
    ) -> int:
        self.initialize()
        clean_guides = [guia.strip() for guia in guias if guia.strip()]
        if not clean_guides:
            return 0

        entrega = fecha_entrega(estado)
        with transaccion(self._connect()) as connection:
            cursor = connection.executemany(
                """
                UPDATE guias
                SET operador = ?, estado = ?, causal = ?, ingreso = ?
                WHERE guia = ?
                """,
                [
                    (operador, estado, causal, hoy_colombia().isoformat(), guia)
                    for guia in clean_guides
                ],
            )
            return cursor.rowcount

    # Las guias entregadas (estado E) no se borran con las herramientas de
    # limpieza: solo salen de la zona de trabajo con el cierre mensual
    # (archivar_entregadas), porque alimentan el informe final del mes.
    _PROTEGER_ENTREGADAS = "UPPER(TRIM(estado)) != 'E'"

    def clear_all(self) -> None:
        self.initialize()
        self._backup_antes_de_borrar()
        with transaccion(self._connect()) as connection:
            connection.execute(f"DELETE FROM guias WHERE {self._PROTEGER_ENTREGADAS}")

    def delete_many(self, guias: list[str]) -> int:
        self.initialize()
        clean_guides = [guia.strip() for guia in guias if guia.strip()]
        if not clean_guides:
            return 0

        self._backup_antes_de_borrar()
        with transaccion(self._connect()) as connection:
            cursor = connection.executemany(
                f"DELETE FROM guias WHERE guia = ? AND {self._PROTEGER_ENTREGADAS}",
                [(guia,) for guia in clean_guides],
            )
            return cursor.rowcount

    def delete_by_fecha(self, fecha: str) -> int:
        self.initialize()
        fecha = fecha.strip()
        if not fecha:
            return 0

        self._backup_antes_de_borrar()
        with transaccion(self._connect()) as connection:
            cursor = connection.execute(
                f"DELETE FROM guias WHERE fecha LIKE ? AND {self._PROTEGER_ENTREGADAS}",
                (f"{fecha}%",),
            )
            return cursor.rowcount

    def delete_by_operador(self, operador: str) -> int:
        self.initialize()
        operador = operador.strip()
        if not operador:
            return 0

        self._backup_antes_de_borrar()
        with transaccion(self._connect()) as connection:
            cursor = connection.execute(
                f"DELETE FROM guias WHERE UPPER(TRIM(operador)) = UPPER(?) AND {self._PROTEGER_ENTREGADAS}",
                (operador,),
            )
            return cursor.rowcount

    def delete_by_estado(self, estado: str) -> int:
        self.initialize()
        estado = estado.strip()
        if not estado:
            return 0

        self._backup_antes_de_borrar()
        with transaccion(self._connect()) as connection:
            cursor = connection.execute(
                f"DELETE FROM guias WHERE estado = ? AND {self._PROTEGER_ENTREGADAS}",
                (estado,),
            )
            return cursor.rowcount

    # Columnas completas de la tabla guias, para snapshots de deshacer.
    _COLUMNAS_GUIA = (
        "guia", "planilla", "servicio", "unid", "tipo_de_servicio",
        "destinatario", "direccion", "municipio", "valor", "operador",
        "estado", "causal", "fecha", "ingreso", "orden_salida",
    )

    def snapshot_guias(self, where: str, params: tuple) -> list[dict]:
        """Copia completa de las guias que cumplen la condicion (para deshacer)."""
        self.initialize()
        with transaccion(self._connect()) as connection:
            return connection.consultar(
                f"SELECT {', '.join(self._COLUMNAS_GUIA)} FROM guias WHERE {where}",
                params,
            )

    def snapshot_por_guias(self, guias: list[str]) -> list[dict]:
        clean = [guia.strip() for guia in guias if guia.strip()]
        if not clean:
            return []
        placeholders = ",".join("?" * len(clean))
        return self.snapshot_guias(f"guia IN ({placeholders})", tuple(clean))

    def restaurar_guias(self, rows: list[dict]) -> int:
        """Reescribe guias completas desde un snapshot (deshacer)."""
        if not rows:
            return 0
        self.initialize()
        columnas = ", ".join(self._COLUMNAS_GUIA)
        marcadores = ", ".join("?" * len(self._COLUMNAS_GUIA))
        with transaccion(self._connect()) as connection:
            connection.executemany(
                f"INSERT OR REPLACE INTO guias ({columnas}) VALUES ({marcadores})",
                [tuple(row[col] for col in self._COLUMNAS_GUIA) for row in rows],
            )
            return len(rows)

    def guardar_cierre_general(self, fecha: str, denominaciones: dict[int, int], efectivo_contado: int) -> None:
        """Guarda el conteo de billetes del cierre general del dia (para el informe diario)."""
        self.initialize()
        with transaccion(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO cierres_generales (fecha, denominaciones, efectivo_contado)
                VALUES (?, ?, ?)
                ON CONFLICT(fecha) DO UPDATE SET
                    denominaciones = excluded.denominaciones,
                    efectivo_contado = excluded.efectivo_contado
                """,
                (fecha, json.dumps({str(d): int(c) for d, c in denominaciones.items()}), int(efectivo_contado)),
            )

    def obtener_cierre_general(self, fecha: str) -> dict | None:
        self.initialize()
        with transaccion(self._connect()) as connection:
            row = connection.execute(
                "SELECT denominaciones, efectivo_contado FROM cierres_generales WHERE fecha = ?",
                (fecha,),
            ).fetchone()
            if row is None:
                return None
            return {
                "denominaciones": {int(d): int(c) for d, c in json.loads(row[0] or "{}").items()},
                "efectivo_contado": row[1],
            }

    def listar_empleados_nomina(self, tipo_contrato: str = "") -> list[dict]:
        """Empleados con sus datos laborales y de nomina.

        Con `tipo_contrato` filtra por NOMINA o SERVICIOS.
        """
        self.initialize()
        condicion = "WHERE UPPER(TRIM(tipo_contrato)) = UPPER(?)" if tipo_contrato else ""
        parametros = (tipo_contrato.strip(),) if tipo_contrato else ()
        with transaccion(self._connect()) as connection:
            return connection.consultar(
                f"""
                SELECT usuario, nombre, apellidos, rol, cedula, cargo, celular,
                       fecha_ingreso, fecha_retiro, tipo_contrato,
                       salario_base, auxilio_transporte, valor_encomienda
                FROM operadores {condicion} ORDER BY nombre
                """,
                parametros,
            )

    def obtener_operador_por_nombre(self, nombre: str) -> dict | None:
        """Busca un empleado por el nombre con el que aparece en las guias.

        La columna OPERADOR de `guias` guarda el nombre para mostrar, no el
        usuario de login, por eso la consulta publica busca asi.
        """
        self.initialize()
        nombre = str(nombre or "").strip()
        if not nombre:
            return None
        with transaccion(self._connect()) as connection:
            return connection.consultar_una(
                """
                SELECT usuario, nombre, apellidos, celular, cargo
                FROM operadores WHERE UPPER(TRIM(nombre)) = UPPER(?)
                """,
                (nombre,),
            )

    def actualizar_datos_empleado(self, usuario: str, datos: dict) -> bool:
        """Actualiza los datos laborales del empleado (no toca la contrasena)."""
        self.initialize()
        campos = (
            "apellidos", "cedula", "cargo", "celular", "fecha_ingreso", "fecha_retiro",
            "tipo_contrato", "salario_base", "auxilio_transporte", "valor_encomienda",
        )
        numericos = {"salario_base", "auxilio_transporte", "valor_encomienda"}
        valores = [
            int(datos.get(campo, 0) or 0) if campo in numericos else str(datos.get(campo, "") or "")
            for campo in campos
        ]
        with transaccion(self._connect()) as connection:
            cursor = connection.execute(
                f"UPDATE operadores SET {', '.join(f'{c} = ?' for c in campos)} WHERE usuario = ?",
                (*valores, usuario),
            )
            return cursor.rowcount > 0

    def contar_entregas_periodo(self, desde: str, hasta: str) -> dict[str, int]:
        """Encomiendas entregadas (E) por operador entre dos fechas (F_ENTREGA).

        Cuenta tanto las guias vivas como las ya archivadas, para que una
        liquidacion vieja siga dando el mismo resultado.
        """
        self.initialize()
        conteo: dict[str, int] = {}
        with transaccion(self._connect()) as connection:
            for tabla in ("guias", "guias_archivo"):
                filas = connection.execute(
                    f"""
                    SELECT operador, COUNT(*) FROM {tabla}
                    WHERE UPPER(TRIM(estado)) = 'E'
                      AND substr(ingreso, 1, 10) >= ? AND substr(ingreso, 1, 10) <= ?
                    GROUP BY operador
                    """,
                    (desde, hasta),
                ).fetchall()
                for operador, cantidad in filas:
                    conteo[operador] = conteo.get(operador, 0) + int(cantidad)
        return conteo

    # ------------------------------------------------------------------
    # Liquidaciones (semanal de servicios y laboral definitiva)
    # ------------------------------------------------------------------

    def guardar_liquidacion_semanal(self, semana_inicio: str, empleado: str, datos: dict) -> None:
        self.initialize()
        campos = (
            "entregas", "valor_encomienda", "subtotal",
            "descuento_prestamos", "otros_descuentos", "total_pagar",
        )
        with transaccion(self._connect()) as connection:
            connection.execute(
                f"""
                INSERT INTO liquidaciones_semanales
                    (semana_inicio, empleado, {', '.join(campos)}, forma_pago, observaciones, registrada_en)
                VALUES (?, ?, {', '.join('?' * len(campos))}, ?, ?, ?)
                ON CONFLICT(semana_inicio, empleado) DO UPDATE SET
                    {', '.join(f'{c} = excluded.{c}' for c in campos)},
                    forma_pago = excluded.forma_pago,
                    observaciones = excluded.observaciones,
                    registrada_en = excluded.registrada_en
                """,
                (
                    semana_inicio,
                    empleado,
                    *(int(datos.get(campo, 0) or 0) for campo in campos),
                    str(datos.get("forma_pago", "")),
                    str(datos.get("observaciones", "")),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def listar_liquidaciones_semanales(self, semana_inicio: str = "", empleado: str = "") -> list[dict]:
        self.initialize()
        condiciones, parametros = [], []
        if semana_inicio:
            condiciones.append("semana_inicio = ?")
            parametros.append(semana_inicio)
        if empleado:
            condiciones.append("UPPER(TRIM(empleado)) = UPPER(?)")
            parametros.append(empleado.strip())
        where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
        with transaccion(self._connect()) as connection:
            return connection.consultar(
                f"SELECT * FROM liquidaciones_semanales {where} ORDER BY semana_inicio DESC, empleado",
                parametros,
            )

    def guardar_liquidacion_laboral(self, datos: dict) -> int:
        self.initialize()
        campos = (
            "empleado", "tipo_liquidacion", "fecha_ingreso", "fecha_retiro", "dias_trabajados",
            "salario_base", "auxilio_transporte", "cesantias",
            "cesantias_pagadas", "cesantias_consignadas", "intereses_cesantias",
            "prima", "vacaciones", "indemnizacion", "otros_descuentos",
            "total_pagar", "observaciones",
        )
        textos = {"empleado", "tipo_liquidacion", "fecha_ingreso", "fecha_retiro", "observaciones"}
        with transaccion(self._connect()) as connection:
            return connection.insertar_devolviendo_id(
                f"""
                INSERT INTO liquidaciones_laborales ({', '.join(campos)}, registrada_en)
                VALUES ({', '.join('?' * len(campos))}, ?)
                """,
                (
                    *(
                        str(datos.get(campo, "") or "") if campo in textos
                        else int(datos.get(campo, 0) or 0)
                        for campo in campos
                    ),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def listar_liquidaciones_laborales(self, empleado: str = "") -> list[dict]:
        self.initialize()
        condicion = "WHERE UPPER(TRIM(empleado)) = UPPER(?)" if empleado else ""
        parametros = (empleado.strip(),) if empleado else ()
        with transaccion(self._connect()) as connection:
            return connection.consultar(
                f"SELECT * FROM liquidaciones_laborales {condicion} ORDER BY fecha_retiro DESC, id DESC",
                parametros,
            )

    # ------------------------------------------------------------------
    # Prestamos y adelantos de nomina
    # ------------------------------------------------------------------

    def crear_prestamo(
        self,
        empleado: str,
        tipo: str,
        monto: int,
        fecha: str,
        forma_pago: str = "",
        cuotas: int = 1,
        observaciones: str = "",
    ) -> int:
        self.initialize()
        with transaccion(self._connect()) as connection:
            return connection.insertar_devolviendo_id(
                """
                INSERT INTO prestamos (empleado, tipo, monto, fecha, forma_pago, cuotas, observaciones)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (empleado, tipo, int(monto), fecha, forma_pago, max(1, int(cuotas)), observaciones),
            )

    def listar_prestamos(self, empleado: str = "", solo_activos: bool = False) -> list[dict]:
        self.initialize()
        condiciones, parametros = ["estado != 'ANULADO'"], []
        if empleado:
            condiciones.append("UPPER(TRIM(empleado)) = UPPER(?)")
            parametros.append(empleado.strip())
        if solo_activos:
            condiciones.append("estado = 'ACTIVO'")
        with transaccion(self._connect()) as connection:
            return connection.consultar(
                f"SELECT * FROM prestamos WHERE {' AND '.join(condiciones)} ORDER BY fecha DESC, id DESC",
                parametros,
            )

    def obtener_prestamo(self, prestamo_id: int) -> dict | None:
        self.initialize()
        with transaccion(self._connect()) as connection:
            return connection.consultar_una("SELECT * FROM prestamos WHERE id = ?", (prestamo_id,))

    def anular_prestamo(self, prestamo_id: int) -> bool:
        self.initialize()
        with transaccion(self._connect()) as connection:
            cursor = connection.execute(
                "UPDATE prestamos SET estado = 'ANULADO' WHERE id = ?", (prestamo_id,)
            )
            return cursor.rowcount > 0

    def marcar_estado_prestamo(self, prestamo_id: int, estado: str) -> None:
        self.initialize()
        with transaccion(self._connect()) as connection:
            connection.execute("UPDATE prestamos SET estado = ? WHERE id = ?", (estado, prestamo_id))

    def registrar_abono(self, prestamo_id: int, fecha: str, monto: int, concepto: str = "") -> int:
        self.initialize()
        with transaccion(self._connect()) as connection:
            return connection.insertar_devolviendo_id(
                "INSERT INTO prestamo_abonos (prestamo_id, fecha, monto, concepto) VALUES (?, ?, ?, ?)",
                (prestamo_id, fecha, int(monto), concepto),
            )

    def listar_abonos(self, prestamo_id: int) -> list[dict]:
        self.initialize()
        with transaccion(self._connect()) as connection:
            return connection.consultar(
                "SELECT * FROM prestamo_abonos WHERE prestamo_id = ? ORDER BY fecha, id",
                (prestamo_id,),
            )

    def eliminar_abono(self, abono_id: int) -> bool:
        self.initialize()
        with transaccion(self._connect()) as connection:
            cursor = connection.execute("DELETE FROM prestamo_abonos WHERE id = ?", (abono_id,))
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Nomina
    # ------------------------------------------------------------------

    def guardar_nomina(self, periodo: str, empleado: str, datos: dict) -> None:
        self.initialize()
        campos = (
            "salario_base", "dias_trabajados", "auxilio_transporte", "bonificaciones",
            "salud", "pension", "descuento_prestamos", "otros_descuentos", "total_pagar",
        )
        with transaccion(self._connect()) as connection:
            connection.execute(
                f"""
                INSERT INTO nomina (periodo, empleado, {', '.join(campos)}, observaciones)
                VALUES (?, ?, {', '.join('?' * len(campos))}, ?)
                ON CONFLICT(periodo, empleado) DO UPDATE SET
                    {', '.join(f'{campo} = excluded.{campo}' for campo in campos)},
                    observaciones = excluded.observaciones
                """,
                (
                    periodo,
                    empleado,
                    *(int(datos.get(campo, 0) or 0) for campo in campos),
                    str(datos.get("observaciones", "")),
                ),
            )

    def listar_nomina(self, periodo: str) -> list[dict]:
        self.initialize()
        with transaccion(self._connect()) as connection:
            return connection.consultar(
                "SELECT * FROM nomina WHERE periodo = ? ORDER BY empleado", (periodo,)
            )

    def eliminar_nomina(self, periodo: str, empleado: str) -> bool:
        self.initialize()
        with transaccion(self._connect()) as connection:
            cursor = connection.execute(
                "DELETE FROM nomina WHERE periodo = ? AND empleado = ?", (periodo, empleado)
            )
            return cursor.rowcount > 0

    def actualizar_datos_nomina_operador(
        self, usuario: str, salario_base: int, auxilio_transporte: int, cedula: str, cargo: str
    ) -> bool:
        self.initialize()
        with transaccion(self._connect()) as connection:
            cursor = connection.execute(
                """
                UPDATE operadores
                SET salario_base = ?, auxilio_transporte = ?, cedula = ?, cargo = ?
                WHERE usuario = ?
                """,
                (int(salario_base), int(auxilio_transporte), cedula, cargo, usuario),
            )
            return cursor.rowcount > 0

    # ------------------------ Ingresos y egresos --------------------------
    #
    # Libro de caja de la oficina. **Todo se digita**, salvo dos egresos que
    # ya viven en la base y se traen solos para no teclearlos dos veces:
    # la nomina liquidada del mes y los gastos que cada repartidor reporta
    # en su cierre.
    #
    # Lo que a proposito NO entra solo:
    # - El **recaudo** no es ingreso de la oficina: es plata del cliente que
    #   se le entrega a Envia. El ingreso real (la comision) se digita.
    # - Los **adelantos y prestamos** no son gasto: es plata que vuelve, y
    #   ademas se descuenta de la nomina, que si entra. Contarlos seria
    #   restar el mismo dinero dos veces.

    TIPOS_MOVIMIENTO = ("INGRESO", "EGRESO")

    def crear_movimiento(self, datos: dict) -> int:
        """Registra un movimiento digitado y devuelve su id."""
        tipo = str(datos.get("tipo", "")).strip().upper()
        if tipo not in self.TIPOS_MOVIMIENTO:
            raise ValueError("El tipo debe ser INGRESO o EGRESO.")
        valor = int(datos.get("valor", 0) or 0)
        if valor <= 0:
            raise ValueError("El valor debe ser mayor que cero.")
        fecha = str(datos.get("fecha", "")).strip()[:10]
        if not fecha:
            raise ValueError("La fecha es obligatoria.")

        self.initialize()
        with transaccion(self._connect()) as connection:
            return connection.insertar_devolviendo_id(
                """
                INSERT INTO movimientos
                    (fecha, tipo, categoria, descripcion, valor, forma_pago,
                     registrado_por, registrado_en)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fecha,
                    tipo,
                    str(datos.get("categoria", "") or "").strip().upper(),
                    str(datos.get("descripcion", "") or "").strip(),
                    valor,
                    str(datos.get("forma_pago", "") or "").strip().upper(),
                    str(datos.get("registrado_por", "") or "").strip(),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

    def listar_movimientos(self, anio: int, mes: int) -> list[dict]:
        """Movimientos digitados del mes, del mas reciente al mas viejo."""
        self.initialize()
        prefijo = f"{int(anio):04d}-{int(mes):02d}"
        with transaccion(self._connect()) as connection:
            return connection.consultar(
                "SELECT * FROM movimientos WHERE fecha LIKE ? ORDER BY fecha DESC, id DESC",
                (prefijo + "%",),
            )

    def eliminar_movimiento(self, movimiento_id: int) -> bool:
        self.initialize()
        with transaccion(self._connect()) as connection:
            cursor = connection.execute(
                "DELETE FROM movimientos WHERE id = ?", (int(movimiento_id),)
            )
            return int(cursor.rowcount or 0) > 0

    def egresos_automaticos_mes(self, anio: int, mes: int) -> list[dict]:
        """Nomina y gastos del mes, que ya estan registrados en otra parte.

        Se devuelven como movimientos para que el informe los sume igual que
        los digitados, pero **no se guardan** en `movimientos`: la fuente de
        verdad sigue siendo la nomina y el cierre de cada repartidor.
        """
        self.initialize()
        periodo = f"{int(anio):04d}-{int(mes):02d}"
        automaticos: list[dict] = []

        with transaccion(self._connect()) as connection:
            nomina = connection.consultar_una(
                "SELECT COALESCE(SUM(total_pagar), 0) AS total FROM nomina WHERE periodo = ?",
                (periodo,),
            )
            gastos = connection.consultar_una(
                "SELECT COALESCE(SUM(gastos), 0) AS total FROM cierres_operador "
                "WHERE fecha LIKE ?",
                (periodo + "%",),
            )

        total_nomina = int((nomina or {}).get("total") or 0)
        if total_nomina:
            automaticos.append(
                {
                    "fecha": periodo,
                    "tipo": "EGRESO",
                    "categoria": "NOMINA",
                    "descripcion": f"Nomina liquidada de {periodo}",
                    "valor": total_nomina,
                    "forma_pago": "",
                    "automatico": True,
                }
            )

        total_gastos = int((gastos or {}).get("total") or 0)
        if total_gastos:
            automaticos.append(
                {
                    "fecha": periodo,
                    "tipo": "EGRESO",
                    "categoria": "GASTOS",
                    "descripcion": "Gastos reportados por los repartidores en su cierre",
                    "valor": total_gastos,
                    "forma_pago": "",
                    "automatico": True,
                }
            )
        return automaticos

    def resumen_ingresos_egresos(self, anio: int, mes: int) -> dict:
        """Estado del mes: lo digitado mas la nomina y los gastos."""
        digitados = self.listar_movimientos(anio, mes)
        automaticos = self.egresos_automaticos_mes(anio, mes)
        movimientos = [{**m, "automatico": False} for m in digitados] + automaticos

        ingresos = sum(m["valor"] for m in movimientos if m["tipo"] == "INGRESO")
        egresos = sum(m["valor"] for m in movimientos if m["tipo"] == "EGRESO")

        por_categoria: dict[str, dict[str, int]] = {}
        for movimiento in movimientos:
            categoria = movimiento.get("categoria") or "SIN CATEGORIA"
            fila = por_categoria.setdefault(categoria, {"INGRESO": 0, "EGRESO": 0})
            fila[movimiento["tipo"]] += movimiento["valor"]

        return {
            "movimientos": movimientos,
            "ingresos": ingresos,
            "egresos": egresos,
            "saldo": ingresos - egresos,
            "por_categoria": por_categoria,
        }

    # ------------------------------ Sesiones ------------------------------
    #
    # Viven en la base y no en memoria para que un despliegue o un reinicio
    # del VPS no expulse a todo el mundo. **Se guarda el hash del token, no
    # el token**: los respaldos salen del servidor (boton de descarga y copia
    # externa), y una copia no debe entregar sesiones vivas a quien la tenga.

    def crear_sesion(
        self, token_hash: str, usuario: str, nombre: str, rol: str, expira_en: str
    ) -> None:
        """Abre la sesion y cierra las anteriores de ese mismo usuario."""
        self.initialize()
        with transaccion(self._connect()) as connection:
            connection.execute("DELETE FROM sesiones WHERE usuario = ?", (usuario,))
            connection.execute(
                """
                INSERT INTO sesiones (token_hash, usuario, nombre, rol, creada_en, expira_en)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    token_hash,
                    usuario,
                    nombre,
                    rol,
                    datetime.now().isoformat(timespec="seconds"),
                    expira_en,
                ),
            )

    def obtener_sesion(self, token_hash: str, ahora: str) -> dict | None:
        """Sesion vigente, o None si no existe o ya vencio.

        La vencida se borra al encontrarla: asi la tabla no crece sola.
        """
        self.initialize()
        with transaccion(self._connect()) as connection:
            sesion = connection.consultar_una(
                "SELECT usuario, nombre, rol, creada_en, expira_en FROM sesiones "
                "WHERE token_hash = ?",
                (token_hash,),
            )
            if sesion is None:
                return None
            if str(sesion["expira_en"]) <= ahora:
                connection.execute("DELETE FROM sesiones WHERE token_hash = ?", (token_hash,))
                return None
            return sesion

    def eliminar_sesion(self, token_hash: str) -> None:
        self.initialize()
        with transaccion(self._connect()) as connection:
            connection.execute("DELETE FROM sesiones WHERE token_hash = ?", (token_hash,))

    def limpiar_sesiones_vencidas(self, ahora: str) -> int:
        self.initialize()
        with transaccion(self._connect()) as connection:
            cursor = connection.execute("DELETE FROM sesiones WHERE expira_en <= ?", (ahora,))
            return int(cursor.rowcount or 0)

    def renombrar_operador(self, usuario: str, nombre_nuevo: str) -> dict:
        """Cambia el nombre del empleado y arrastra todo su historial.

        Las guias, los cierres, los prestamos, la nomina y las liquidaciones
        guardan el **nombre** del empleado, no su usuario de login: si el
        nombre cambia sin tocarlos, el historial se le desprende y deja de
        aparecer en sus informes. Devuelve cuantas filas se reasignaron en
        cada tabla, para poder avisarlo en pantalla.
        """
        self.initialize()
        nombre_nuevo = str(nombre_nuevo or "").strip().upper()
        if not nombre_nuevo:
            raise ValueError("El nombre no puede quedar vacio.")

        # (tabla, columna que guarda el nombre del empleado)
        referencias = (
            ("guias", "operador"),
            ("guias_archivo", "operador"),
            ("cierres_operador", "operador"),
            ("prestamos", "empleado"),
            ("nomina", "empleado"),
            ("liquidaciones_semanales", "empleado"),
            ("liquidaciones_laborales", "empleado"),
        )
        with transaccion(self._connect()) as connection:
            fila = connection.consultar_una(
                "SELECT nombre FROM operadores WHERE usuario = ?", (usuario,)
            )
            if fila is None:
                raise ValueError("No se encontro el empleado.")
            nombre_anterior = str(fila["nombre"] or "").strip()
            if nombre_anterior.upper() == nombre_nuevo:
                return {"nombre_anterior": nombre_anterior, "cambios": {}}

            ocupado = connection.consultar_una(
                """
                SELECT usuario FROM operadores
                WHERE UPPER(TRIM(nombre)) = ? AND usuario <> ?
                """,
                (nombre_nuevo, usuario),
            )
            if ocupado is not None:
                raise ValueError(
                    f"El nombre '{nombre_nuevo}' ya lo usa '{ocupado['usuario']}'."
                )

            connection.execute(
                "UPDATE operadores SET nombre = ? WHERE usuario = ?",
                (nombre_nuevo, usuario),
            )
            cambios: dict[str, int] = {}
            if nombre_anterior:
                for tabla, columna in referencias:
                    cursor = connection.execute(
                        f"UPDATE {tabla} SET {columna} = ? "
                        f"WHERE UPPER(TRIM({columna})) = UPPER(?)",
                        (nombre_nuevo, nombre_anterior),
                    )
                    if cursor.rowcount:
                        cambios[tabla] = cursor.rowcount
            return {"nombre_anterior": nombre_anterior, "cambios": cambios}

    def entregadas_mes(self, anio: int, mes: int) -> list[dict]:
        """Guias entregadas (E) del mes, por fecha de entrega (F_ENTREGA).

        Une el archivo historico con las que siguen en la zona de trabajo
        (entregadas hoy, aun sin archivar). Si una guia esta en ambos lados,
        gana la version de la zona de trabajo por ser la mas reciente.
        """
        self.initialize()
        prefijo = f"{anio:04d}-{mes:02d}%"
        columnas = (
            "guia, planilla, servicio, unid, tipo_de_servicio, destinatario, "
            "direccion, municipio, valor, operador, estado, causal, fecha, ingreso"
        )
        with transaccion(self._connect()) as connection:
            return connection.consultar(
                f"""
                SELECT {columnas} FROM guias_archivo
                WHERE UPPER(TRIM(estado)) = 'E' AND ingreso LIKE ?
                  AND guia NOT IN (
                      SELECT guia FROM guias
                      WHERE UPPER(TRIM(estado)) = 'E' AND ingreso LIKE ?
                  )
                UNION ALL
                SELECT {columnas} FROM guias
                WHERE UPPER(TRIM(estado)) = 'E' AND ingreso LIKE ?
                ORDER BY operador, ingreso, guia
                """,
                (prefijo, prefijo, prefijo),
            )

    def eliminar_entregadas_mes(self, anio: int, mes: int) -> dict:
        """Borra definitivamente las entregadas del mes (archivo + zona de trabajo).

        Es la unica via para eliminar guias E: accion explicita del admin
        desde Entregas del Mes. Hace respaldo antes de borrar.
        """
        self.initialize()
        self._backup_antes_de_borrar()
        prefijo = f"{anio:04d}-{mes:02d}%"
        with transaccion(self._connect()) as connection:
            cursor_archivo = connection.execute(
                "DELETE FROM guias_archivo WHERE ingreso LIKE ?",
                (prefijo,),
            )
            cursor_zona = connection.execute(
                "DELETE FROM guias WHERE UPPER(TRIM(estado)) = 'E' AND ingreso LIKE ?",
                (prefijo,),
            )
            return {
                "archivo": cursor_archivo.rowcount,
                "zona": cursor_zona.rowcount,
            }

    def archivar_entregadas(self) -> int:
        """Mueve todas las guias en estado E a guias_archivo (cierre mensual).

        Devuelve la cantidad de guias archivadas. Si una guia ya existia en el
        archivo (reimportada y entregada de nuevo), se reemplaza con la version
        mas reciente.
        """
        self.initialize()
        self._backup_antes_de_borrar()
        marca = datetime.now().isoformat(timespec="seconds")
        with transaccion(self._connect()) as connection:
            cursor = connection.execute(
                """
                INSERT OR REPLACE INTO guias_archivo (
                    guia, planilla, servicio, unid, tipo_de_servicio,
                    destinatario, direccion, municipio, valor, operador,
                    estado, causal, fecha, ingreso, orden_salida, archivado_en
                )
                SELECT guia, planilla, servicio, unid, tipo_de_servicio,
                       destinatario, direccion, municipio, valor, operador,
                       estado, causal, fecha, ingreso, orden_salida, ?
                FROM guias WHERE UPPER(TRIM(estado)) = 'E'
                """,
                (marca,),
            )
            archivadas = cursor.rowcount
            connection.execute("DELETE FROM guias WHERE UPPER(TRIM(estado)) = 'E'")
            return archivadas

    def crear_operador(
        self,
        usuario: str,
        password_hash: str,
        nombre: str,
        rol: str = "operador",
        licencia_vencimiento: str = "",
        soat_vencimiento: str = "",
        tecnomecanica_vencimiento: str = "",
    ) -> None:
        self.initialize()
        with transaccion(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO operadores (
                    usuario, password_hash, nombre, rol,
                    licencia_vencimiento, soat_vencimiento, tecnomecanica_vencimiento
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(usuario) DO UPDATE SET
                    password_hash = excluded.password_hash,
                    nombre = excluded.nombre,
                    rol = excluded.rol,
                    licencia_vencimiento = excluded.licencia_vencimiento,
                    soat_vencimiento = excluded.soat_vencimiento,
                    tecnomecanica_vencimiento = excluded.tecnomecanica_vencimiento
                """,
                (
                    usuario,
                    password_hash,
                    nombre,
                    rol,
                    licencia_vencimiento,
                    soat_vencimiento,
                    tecnomecanica_vencimiento,
                ),
            )

    def obtener_operador(self, usuario: str) -> dict | None:
        self.initialize()
        with transaccion(self._connect()) as connection:
            return connection.consultar_una(
                "SELECT * FROM operadores WHERE usuario = ?", (usuario,)
            )

    def listar_operadores(self) -> list[dict]:
        self.initialize()
        with transaccion(self._connect()) as connection:
            return connection.consultar(
                """
                SELECT usuario, nombre, rol,
                       licencia_vencimiento, soat_vencimiento, tecnomecanica_vencimiento
                FROM operadores ORDER BY nombre
                """
            )

    def listar_operadores_en_guias(self) -> list[str]:
        # Los nombres de operador en la columna OPERADOR de guias no siempre
        # coinciden con un usuario de login en la tabla operadores (por
        # ejemplo PLANILLADA o un repartidor sin acceso al panel), por eso se
        # listan aparte para los selectores de informes.
        self.initialize()
        with transaccion(self._connect()) as connection:
            rows = connection.execute(
                "SELECT DISTINCT operador FROM guias WHERE TRIM(operador) != '' ORDER BY operador"
            ).fetchall()
            return [row[0] for row in rows]

    def contar_admins(self) -> int:
        self.initialize()
        with transaccion(self._connect()) as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM operadores WHERE rol = 'admin'"
            ).fetchone()
            return row[0]

    def eliminar_operador(self, usuario: str) -> int:
        self.initialize()
        with transaccion(self._connect()) as connection:
            cursor = connection.execute("DELETE FROM operadores WHERE usuario = ?", (usuario,))
            return cursor.rowcount

    def asignar_salida(self, guias: list[str], operador: str, estado: str) -> tuple[int, list[str]]:
        # Las guias que llegan en la lista pero no estan en el consolidado
        # (no vinieron en ninguna planilla) se crean igual, asignadas al
        # repartidor que las registro, marcando planilla = "Sin planilla"
        # para que sigan siendo visibles en su informe de salidas.
        self.initialize()
        clean_guides = [guia.strip() for guia in guias if guia.strip()]
        if not clean_guides:
            return 0, []

        with transaccion(self._connect()) as connection:
            placeholders = ",".join("?" * len(clean_guides))
            encontradas = {
                row["guia"]
                for row in connection.consultar(
                    f"SELECT guia FROM guias WHERE guia IN ({placeholders})", clean_guides
                )
            }
            no_encontradas = [guia for guia in clean_guides if guia not in encontradas]
            encontradas_en_orden = [guia for guia in clean_guides if guia in encontradas]

            siguiente_orden = (
                connection.execute("SELECT COALESCE(MAX(orden_salida), 0) FROM guias").fetchone()[0] + 1
            )

            hoy = hoy_colombia().isoformat()
            cursor = connection.executemany(
                """
                UPDATE guias SET operador = ?, estado = ?, orden_salida = ?,
                    fecha = CASE WHEN fecha LIKE ? THEN fecha ELSE ? END
                WHERE guia = ?
                """,
                [
                    (operador, estado, siguiente_orden + indice, f"{hoy}%", hoy, guia)
                    for indice, guia in enumerate(encontradas_en_orden)
                ],
            )
            actualizadas = cursor.rowcount

            if no_encontradas:
                connection.executemany(
                    """
                    INSERT INTO guias (
                        guia, planilla, servicio, unid, tipo_de_servicio,
                        destinatario, direccion, municipio, valor, operador, estado,
                        causal, fecha, ingreso, orden_salida
                    )
                    VALUES (?, 'Sin planilla', '', '', '', '', '', '', '0', ?, ?, '', ?, '', ?)
                    """,
                    [
                        (guia, operador, estado, hoy, siguiente_orden + len(encontradas_en_orden) + indice)
                        for indice, guia in enumerate(no_encontradas)
                    ],
                )
                actualizadas += len(no_encontradas)

            return actualizadas, no_encontradas

    def registrar_novedad(
        self,
        guias: list[str],
        operador: str,
        fecha: str,
        nuevo_estado: str,
    ) -> int:
        # No se filtra por estado actual: una novedad debe poder registrarse
        # sin importar en que estado haya quedado la guia (R, E, otra
        # novedad...), incluso si el operador ya cerro el dia.
        self.initialize()
        clean_guides = [guia.strip() for guia in guias if guia.strip()]
        if not clean_guides:
            return 0

        entrega = fecha_entrega(nuevo_estado, fecha)
        with transaccion(self._connect()) as connection:
            # Sin filtro por F_INGRESO: la novedad aplica a las guias activas del
            # repartidor aunque se hayan importado dias antes. F_ENTREGA = hoy.
            cursor = connection.executemany(
                """
                UPDATE guias SET estado = ?, ingreso = ?
                WHERE guia = ? AND operador = ?
                """,
                [(nuevo_estado, entrega, guia, operador) for guia in clean_guides],
            )
            return cursor.rowcount

    def registrar_devolucion(
        self,
        items: list[tuple[str, str]],
        operador: str,
        fecha: str,
        nuevo_estado: str,
    ) -> int:
        # No se filtra por estado actual, por la misma razon que registrar_novedad.
        self.initialize()
        clean_items = [(guia.strip(), causal.strip()) for guia, causal in items if guia.strip()]
        if not clean_items:
            return 0

        entrega = fecha_entrega(nuevo_estado, fecha)
        with transaccion(self._connect()) as connection:
            cursor = connection.executemany(
                """
                UPDATE guias SET estado = ?, causal = ?, ingreso = ?
                WHERE guia = ? AND operador = ?
                """,
                [(nuevo_estado, causal, entrega, guia, operador) for guia, causal in clean_items],
            )
            return cursor.rowcount

    def cerrar_dia_operador(self, operador: str, fecha: str, estado_actual: str, nuevo_estado: str) -> int:
        self.initialize()
        entrega = fecha_entrega(nuevo_estado, fecha)
        with transaccion(self._connect()) as connection:
            # Cierra TODAS las guias del repartidor en reparto, sin importar la
            # fecha de importacion, y estampa F_ENTREGA con la fecha del cierre.
            cursor = connection.execute(
                "UPDATE guias SET estado = ?, ingreso = ? WHERE operador = ? AND estado = ?",
                (nuevo_estado, entrega, operador, estado_actual),
            )
            return cursor.rowcount

    def revertir_cierre_operador(self, operador: str, fecha: str) -> int:
        self.initialize()
        with transaccion(self._connect()) as connection:
            # Se filtra por F_ENTREGA (columna "ingreso"): son las guias que se
            # cerraron ESE dia, sin importar cuando se importaron.
            cursor = connection.execute(
                "UPDATE guias SET estado = 'R', ingreso = '' WHERE operador = ? AND ingreso LIKE ? AND estado = 'E'",
                (operador, f"{fecha}%"),
            )
            return cursor.rowcount

    def eliminar_cierre(self, fecha: str, operador: str) -> bool:
        self.initialize()
        with transaccion(self._connect()) as connection:
            cursor = connection.execute(
                "DELETE FROM cierres_operador WHERE fecha = ? AND operador = ?",
                (fecha, operador),
            )
            return cursor.rowcount > 0

    def revertir_cierres_dia(self, fecha: str) -> dict:
        self.initialize()
        with transaccion(self._connect()) as connection:
            cursor_guias = connection.execute(
                "UPDATE guias SET estado = 'R', ingreso = '' WHERE ingreso LIKE ? AND estado = 'E'",
                (f"{fecha}%",),
            )
            cursor_cierres = connection.execute(
                "DELETE FROM cierres_operador WHERE fecha = ?",
                (fecha,),
            )
            return {
                "guias_revertidas": cursor_guias.rowcount,
                "cierres_eliminados": cursor_cierres.rowcount,
            }

    def guias_de_operador(self, operador: str, fecha: str) -> list[dict]:
        self.initialize()
        with transaccion(self._connect()) as connection:
            # Guias que el repartidor gestiono ESE dia: se filtran por F_ENTREGA
            # (fecha de gestion), no por la fecha de importacion.
            return connection.consultar(
                "SELECT * FROM guias WHERE operador = ? AND ingreso LIKE ?",
                (operador, f"{fecha}%"),
            )

    def guias_en_salida(self, operador: str, estado: str) -> list[dict]:
        # No filtra por fecha de planilla: una guia puede haber llegado en
        # dias distintos y salir hoy con el operador, por eso se busca solo
        # por operador y estado actual. Se ordena por orden_salida para
        # respetar el orden en que el operador la registro en el campo "Salidas".
        self.initialize()
        with transaccion(self._connect()) as connection:
            return connection.consultar(
                "SELECT * FROM guias WHERE operador = ? AND estado = ? ORDER BY orden_salida",
                (operador, estado),
            )

    def guardar_cierre(
        self,
        fecha: str,
        operador: str,
        gestionadas: int,
        ro: int,
        n: int,
        d: int,
        e: int,
        recaudado: int,
        bancos: int,
        nequi: int,
        envia: int,
        efectivo: int,
        gastos: int = 0,
        adelanto_salario: int = 0,
        denominaciones: dict[int, int] | None = None,
    ) -> None:
        self.initialize()
        denominaciones_json = json.dumps(denominaciones or {})
        with transaccion(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO cierres_operador (
                    fecha, operador, gestionadas, ro, n, d, e,
                    recaudado, bancos, nequi, envia, efectivo, gastos, adelanto_salario,
                    denominaciones
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fecha, operador) DO UPDATE SET
                    gestionadas = excluded.gestionadas,
                    ro = excluded.ro,
                    n = excluded.n,
                    d = excluded.d,
                    e = excluded.e,
                    recaudado = excluded.recaudado,
                    bancos = excluded.bancos,
                    nequi = excluded.nequi,
                    envia = excluded.envia,
                    efectivo = excluded.efectivo,
                    gastos = excluded.gastos,
                    adelanto_salario = excluded.adelanto_salario,
                    denominaciones = excluded.denominaciones
                """,
                (
                    fecha, operador, gestionadas, ro, n, d, e, recaudado,
                    bancos, nequi, envia, efectivo, gastos, adelanto_salario,
                    denominaciones_json,
                ),
            )

    def obtener_cierre(self, fecha: str, operador: str) -> dict | None:
        self.initialize()
        with transaccion(self._connect()) as connection:
            cierre = connection.consultar_una(
                "SELECT * FROM cierres_operador WHERE fecha = ? AND operador = ?",
                (fecha, operador),
            )
            if not cierre:
                return None
            try:
                cierre["denominaciones"] = {
                    int(denominacion): int(cantidad)
                    for denominacion, cantidad in json.loads(cierre["denominaciones"] or "{}").items()
                }
            except (json.JSONDecodeError, ValueError):
                cierre["denominaciones"] = {}
            return cierre

    def operadores_con_cierre(self, fecha: str) -> list[str]:
        self.initialize()
        with transaccion(self._connect()) as connection:
            rows = connection.execute(
                "SELECT DISTINCT operador FROM cierres_operador WHERE fecha = ?",
                (fecha,),
            ).fetchall()
            return [row[0] for row in rows]

    def sumar_totales_cierres_dia(self, fecha: str) -> dict:
        self.initialize()
        with transaccion(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT
                    COALESCE(SUM(recaudado), 0) AS recaudado,
                    COALESCE(SUM(bancos), 0)    AS bancos,
                    COALESCE(SUM(nequi), 0)     AS nequi,
                    COALESCE(SUM(envia), 0)     AS envia,
                    COALESCE(SUM(gastos), 0)    AS gastos,
                    COALESCE(SUM(adelanto_salario), 0) AS adelanto_salario,
                    COALESCE(SUM(efectivo), 0)  AS efectivo
                FROM cierres_operador WHERE fecha = ?
                """,
                (fecha,),
            ).fetchone()
            return {
                "recaudado": row[0],
                "bancos": row[1],
                "nequi": row[2],
                "envia": row[3],
                "gastos": row[4],
                "adelanto_salario": row[5],
                "efectivo": row[6],
            }

    def sumar_envia_dia(self, fecha: str) -> int:
        self.initialize()
        with transaccion(self._connect()) as connection:
            total = connection.execute(
                "SELECT SUM(envia) FROM cierres_operador WHERE fecha = ?",
                (fecha,),
            ).fetchone()[0]
            return total or 0

    def sumar_gastos_adelantos_mes(self, anio: int, mes: int) -> dict[str, dict]:
        self.initialize()
        prefijo = f"{anio:04d}-{mes:02d}"
        with transaccion(self._connect()) as connection:
            rows = connection.consultar(
                "SELECT operador, SUM(gastos) AS gastos, SUM(adelanto_salario) AS adelanto_salario "
                "FROM cierres_operador WHERE fecha LIKE ? GROUP BY operador",
                (prefijo + "%",),
            )
            return {
                row["operador"]: {
                    "gastos": row["gastos"] or 0,
                    "adelanto_salario": row["adelanto_salario"] or 0,
                }
                for row in rows
            }

    def to_dataframe(self) -> pd.DataFrame:
        rows = self.list_all()
        columns = [
            "PLANILLA",
            "SERVICIO",
            "GUIA",
            "UNID",
            "TIPO DE SERVICIO",
            "DESTINATARIO",
            "DIRECCION",
            "MUNICIPIO",
            "VALOR",
            "OPERADOR",
            "ESTADO",
            "CAUSAL",
            "F_INGRESO",
            "F_ENTREGA",
        ]
        data = [
            {
                "PLANILLA": row["planilla"],
                "SERVICIO": row["servicio"],
                "GUIA": row["guia"],
                "UNID": row["unid"],
                "TIPO DE SERVICIO": row["tipo_de_servicio"],
                "DESTINATARIO": row["destinatario"],
                "DIRECCION": row["direccion"],
                "MUNICIPIO": row["municipio"],
                "VALOR": row["valor"],
                "OPERADOR": row["operador"],
                "ESTADO": row["estado"],
                "CAUSAL": row["causal"],
                "F_INGRESO": row["fecha"],
                "F_ENTREGA": row["ingreso"],
            }
            for row in rows
        ]
        return pd.DataFrame(data, columns=columns)

    def _connect(self):
        """Conexion al motor que corresponda, ya envuelta por `db.Conexion`."""
        if self.es_postgres:
            return abrir_postgres(self.dsn)
        return abrir_sqlite(self.database_file)

    def _connect_sqlite_crudo(self) -> sqlite3.Connection:
        """Conexion sqlite3 sin envolver, para lo que solo existe en SQLite.

        Los `PRAGMA` de integridad y la API de respaldo por archivo no tienen
        equivalente en Postgres: alli de eso se encarga Supabase.
        """
        if self.es_postgres:
            raise RuntimeError(
                "Esta operacion es propia de SQLite; con Supabase la integridad "
                "y los respaldos los administra el servicio."
            )
        conexion = sqlite3.connect(self.database_file, timeout=30)
        conexion.execute("PRAGMA journal_mode=WAL")
        # synchronous=FULL: cada transaccion se confirma al disco antes de
        # darla por buena. Con el valor por defecto (NORMAL) un apagon o un
        # reinicio inesperado del servidor puede dejar la base corrupta
        # ("database disk image is malformed"), que es justo lo que pasaba.
        conexion.execute("PRAGMA synchronous=FULL")
        conexion.execute("PRAGMA foreign_keys=ON")
        return conexion

    def verificar_integridad(self) -> str:
        """Devuelve 'ok' si la base esta sana, o el detalle del dano.

        El dano por escritura interrumpida es justo lo que se deja atras al
        pasar a Postgres administrado; con Supabase solo se comprueba que la
        base responda.
        """
        if self.es_postgres:
            try:
                with transaccion(self._connect()) as connection:
                    connection.execute("SELECT 1")
                return "ok"
            except Exception as error:  # noqa: BLE001 - fallo de red o credenciales
                return str(error)

        self.database_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.database_file.exists():
            return "ok"
        try:
            with closing(self._connect_sqlite_crudo()) as conexion, conexion:
                return str(conexion.execute("PRAGMA integrity_check").fetchone()[0])
        except sqlite3.DatabaseError as error:
            return str(error)

    # Cantidad maxima de respaldos automaticos que se conservan. Sin este
    # limite la carpeta backups/ crecia con cada borrado hasta llenar el
    # disco del servidor y SQLite empezaba a fallar con "disk I/O error".
    MAX_BACKUPS = 10

    # Respaldos periodicos (cada pocas horas, ver launcher_server): se
    # conservan mas copias que las de borrado para poder volver a un punto
    # cercano en el tiempo si la base se dana.
    MAX_BACKUPS_PERIODICOS = 24

    def respaldo_periodico(self) -> Path | None:
        """Copia consistente de la base en caliente, con rotacion propia.

        Usa la API de backup de SQLite (no un copiado de archivo), que
        produce una copia integra aunque la base este en uso.

        Si la base de origen esta danada NO se genera copia ni se rota: de
        lo contrario los respaldos sanos se irian reemplazando por copias
        corruptas y al cabo de unas horas no quedaria ninguno util.
        """
        if not self.database_file.exists():
            return None

        estado = self.verificar_integridad()
        if estado != "ok":
            print(
                "AVISO: se omite el respaldo periodico porque la base esta danada "
                f"({estado}). Los respaldos sanos existentes se conservan."
            )
            return None

        carpeta_backup = self.database_file.parent / "backups"
        carpeta_backup.mkdir(parents=True, exist_ok=True)

        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = carpeta_backup / f"periodico_{marca}.db"
        with closing(self._connect_sqlite_crudo()) as origen, origen:
            copia = sqlite3.connect(destino)
            try:
                origen.backup(copia)
            finally:
                copia.close()

        # Comprobacion final: una copia que no pase el chequeo no sirve de
        # nada y no debe ocupar un lugar en la rotacion.
        with closing(sqlite3.connect(destino)) as revision:
            if str(revision.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
                destino.unlink(missing_ok=True)
                print("AVISO: el respaldo periodico salio danado y se descarto.")
                return None

        respaldos = sorted(carpeta_backup.glob("periodico_*.db"))
        for viejo in respaldos[:-self.MAX_BACKUPS_PERIODICOS]:
            viejo.unlink(missing_ok=True)
        return destino

    def copia_para_descarga(self, destino: Path) -> None:
        """Copia integra de la base en `destino`, lista para llevarse fuera.

        Todos los respaldos viven en el mismo disco del servidor: si ese
        disco falla se pierden todos a la vez. Esta copia existe para que el
        administrador pueda guardarla en otra parte.

        Usa la API de backup de SQLite, que produce una copia consistente
        con la base en uso, y la verifica antes de entregarla: un respaldo
        danado da una falsa sensacion de seguridad, que es peor que no
        tener ninguno.
        """
        if not self.database_file.exists():
            raise FileNotFoundError("Todavia no existe la base de datos.")

        estado = self.verificar_integridad()
        if estado != "ok":
            raise sqlite3.DatabaseError(
                f"La base de datos esta danada ({estado}); no se genera la copia."
            )

        destino.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect_sqlite_crudo()) as origen, origen:
            copia = sqlite3.connect(destino)
            try:
                origen.backup(copia)
            finally:
                copia.close()

        with closing(sqlite3.connect(destino)) as revision:
            if str(revision.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
                destino.unlink(missing_ok=True)
                raise sqlite3.DatabaseError("La copia salio danada y se descarto.")

    def _backup_antes_de_borrar(self) -> None:
        # Copia de seguridad de la base completa antes de un borrado masivo,
        # para poder recuperar la informacion si el borrado fue un error.
        if not self.database_file.exists():
            return
        carpeta_backup = self.database_file.parent / "backups"
        carpeta_backup.mkdir(parents=True, exist_ok=True)

        # Vuelca el WAL al archivo principal para que la copia quede completa
        # y el .db-wal no crezca sin limite.
        with closing(self._connect_sqlite_crudo()) as conexion, conexion:
            conexion.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        marca = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        destino = carpeta_backup / f"{self.database_file.stem}_{marca}.db"
        shutil.copy2(self.database_file, destino)

        # Rotacion: conserva solo los respaldos mas recientes.
        respaldos = sorted(carpeta_backup.glob(f"{self.database_file.stem}_*.db"))
        for viejo in respaldos[:-self.MAX_BACKUPS]:
            viejo.unlink(missing_ok=True)
