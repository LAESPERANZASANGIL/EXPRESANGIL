from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import json
import shutil
import sqlite3

import pandas as pd

from .excel_processor import hoy_colombia


TABLE_NAME = "guias"

# Operador por defecto de las guias recien importadas que aun no se le
# asignan a un repartidor: siguen "en planilla", esperando salida.
OPERADOR_PLANILLADA = "PLANILLADA"

# Operador especial: guias que se quedan en bodega (no salen a reparto).
# No deben quedar con estado "N" al importar ni "R" al registrar salida.
OPERADOR_BODEGA = "BODEGA"



class GuiaRepository:
    def __init__(self, database_file: Path) -> None:
        self.database_file = database_file
        self.database_file.parent.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> None:
        with self._connect() as connection:
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

    def save_consolidated(self, dataframe: pd.DataFrame) -> None:
        self.initialize()
        guias = [row for row in dataframe["GUIA"].astype(str) if row]
        with self._connect() as connection:
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

        with self._connect() as connection:
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
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT * FROM guias ORDER BY rowid").fetchall()
            return [dict(row) for row in rows]

    def obtener_guia(self, guia: str) -> dict | None:
        self.initialize()
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM guias WHERE guia = ?", (guia,)
            ).fetchone()
            return dict(row) if row else None

    def update_tracking_fields(self, guia: str, operador: str, estado: str, causal: str) -> None:
        self.initialize()
        with self._connect() as connection:
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
    ) -> None:
        self.initialize()
        # F_INGRESO (columna "fecha") y F_ENTREGA (columna "ingreso") solo se
        # tocan si el editor envia un valor explicito; en caso contrario se
        # conserva el que ya tenia la guia.
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE guias
                SET planilla = ?, destinatario = ?, direccion = ?, municipio = ?,
                    valor = ?, operador = ?, estado = ?, causal = ?,
                    fecha = COALESCE(?, fecha),
                    ingreso = COALESCE(?, ingreso)
                WHERE guia = ?
                """,
                (
                    planilla, destinatario, direccion, municipio, valor,
                    operador, estado, causal, fecha, entrega, guia,
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

        with self._connect() as connection:
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

    def clear_all(self) -> None:
        self.initialize()
        self._backup_antes_de_borrar()
        with self._connect() as connection:
            connection.execute("DELETE FROM guias")

    def delete_many(self, guias: list[str]) -> int:
        self.initialize()
        clean_guides = [guia.strip() for guia in guias if guia.strip()]
        if not clean_guides:
            return 0

        self._backup_antes_de_borrar()
        with self._connect() as connection:
            cursor = connection.executemany(
                "DELETE FROM guias WHERE guia = ?",
                [(guia,) for guia in clean_guides],
            )
            return cursor.rowcount

    def delete_by_fecha(self, fecha: str) -> int:
        self.initialize()
        fecha = fecha.strip()
        if not fecha:
            return 0

        self._backup_antes_de_borrar()
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM guias WHERE fecha LIKE ?", (f"{fecha}%",))
            return cursor.rowcount

    def delete_by_operador(self, operador: str) -> int:
        self.initialize()
        operador = operador.strip()
        if not operador:
            return 0

        self._backup_antes_de_borrar()
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM guias WHERE UPPER(TRIM(operador)) = UPPER(?)",
                (operador,),
            )
            return cursor.rowcount

    def delete_by_estado(self, estado: str) -> int:
        self.initialize()
        estado = estado.strip()
        if not estado:
            return 0

        self._backup_antes_de_borrar()
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM guias WHERE estado = ?", (estado,))
            return cursor.rowcount

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
        with self._connect() as connection:
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
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM operadores WHERE usuario = ?", (usuario,)
            ).fetchone()
            return dict(row) if row else None

    def listar_operadores(self) -> list[dict]:
        self.initialize()
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT usuario, nombre, rol,
                       licencia_vencimiento, soat_vencimiento, tecnomecanica_vencimiento
                FROM operadores ORDER BY nombre
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def listar_operadores_en_guias(self) -> list[str]:
        # Los nombres de operador en la columna OPERADOR de guias no siempre
        # coinciden con un usuario de login en la tabla operadores (por
        # ejemplo PLANILLADA o un repartidor sin acceso al panel), por eso se
        # listan aparte para los selectores de informes.
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT operador FROM guias WHERE TRIM(operador) != '' ORDER BY operador"
            ).fetchall()
            return [row[0] for row in rows]

    def contar_admins(self) -> int:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) FROM operadores WHERE rol = 'admin'"
            ).fetchone()
            return row[0]

    def eliminar_operador(self, usuario: str) -> int:
        self.initialize()
        with self._connect() as connection:
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

        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            placeholders = ",".join("?" * len(clean_guides))
            encontradas = {
                row["guia"]
                for row in connection.execute(
                    f"SELECT guia FROM guias WHERE guia IN ({placeholders})", clean_guides
                ).fetchall()
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
                    VALUES (?, 'Sin planilla', '', '', '', '', '', '', '0', ?, ?, '', ?, ?, ?)
                    """,
                    [
                        (guia, operador, estado, hoy, hoy, siguiente_orden + len(encontradas_en_orden) + indice)
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

        with self._connect() as connection:
            cursor = connection.executemany(
                """
                UPDATE guias SET estado = ?, ingreso = ?
                WHERE guia = ? AND operador = ?
                """,
                [(nuevo_estado, fecha, guia, operador) for guia in clean_guides],
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

        with self._connect() as connection:
            cursor = connection.executemany(
                """
                UPDATE guias SET estado = ?, causal = ?, ingreso = ?
                WHERE guia = ? AND operador = ?
                """,
                [(nuevo_estado, causal, fecha, guia, operador) for guia, causal in clean_items],
            )
            return cursor.rowcount

    def cerrar_dia_operador(self, operador: str, fecha: str, estado_actual: str, nuevo_estado: str) -> int:
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE guias SET estado = ?, ingreso = ? WHERE operador = ? AND fecha LIKE ? AND estado = ?",
                (nuevo_estado, fecha, operador, f"{fecha}%", estado_actual),
            )
            return cursor.rowcount

    def revertir_cierre_operador(self, operador: str, fecha: str) -> int:
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE guias SET estado = 'R', ingreso = '' WHERE operador = ? AND fecha LIKE ? AND estado = 'E'",
                (operador, f"{fecha}%"),
            )
            return cursor.rowcount

    def eliminar_cierre(self, fecha: str, operador: str) -> bool:
        self.initialize()
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM cierres_operador WHERE fecha = ? AND operador = ?",
                (fecha, operador),
            )
            return cursor.rowcount > 0

    def revertir_cierres_dia(self, fecha: str) -> dict:
        self.initialize()
        with self._connect() as connection:
            cursor_guias = connection.execute(
                "UPDATE guias SET estado = 'R', ingreso = '' WHERE fecha LIKE ? AND estado = 'E'",
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
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM guias WHERE operador = ? AND fecha LIKE ?",
                (operador, f"{fecha}%"),
            ).fetchall()
            return [dict(row) for row in rows]

    def guias_en_salida(self, operador: str, estado: str) -> list[dict]:
        # No filtra por fecha de planilla: una guia puede haber llegado en
        # dias distintos y salir hoy con el operador, por eso se busca solo
        # por operador y estado actual. Se ordena por orden_salida para
        # respetar el orden en que el operador la registro en el campo "Salidas".
        self.initialize()
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM guias WHERE operador = ? AND estado = ? ORDER BY orden_salida",
                (operador, estado),
            ).fetchall()
            return [dict(row) for row in rows]

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
        with self._connect() as connection:
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
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM cierres_operador WHERE fecha = ? AND operador = ?",
                (fecha, operador),
            ).fetchone()
            if not row:
                return None
            cierre = dict(row)
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
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT DISTINCT operador FROM cierres_operador WHERE fecha = ?",
                (fecha,),
            ).fetchall()
            return [row[0] for row in rows]

    def sumar_envia_dia(self, fecha: str) -> int:
        self.initialize()
        with self._connect() as connection:
            total = connection.execute(
                "SELECT SUM(envia) FROM cierres_operador WHERE fecha = ?",
                (fecha,),
            ).fetchone()[0]
            return total or 0

    def sumar_gastos_adelantos_mes(self, anio: int, mes: int) -> dict[str, dict]:
        self.initialize()
        prefijo = f"{anio:04d}-{mes:02d}"
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT operador, SUM(gastos) AS gastos, SUM(adelanto_salario) AS adelanto_salario "
                "FROM cierres_operador WHERE fecha LIKE ? GROUP BY operador",
                (prefijo + "%",),
            ).fetchall()
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

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_file, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _backup_antes_de_borrar(self) -> None:
        # Copia de seguridad de la base completa antes de un borrado masivo,
        # para poder recuperar la informacion si el borrado fue un error.
        if not self.database_file.exists():
            return
        carpeta_backup = self.database_file.parent / "backups"
        carpeta_backup.mkdir(parents=True, exist_ok=True)
        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = carpeta_backup / f"{self.database_file.stem}_{marca}.db"
        shutil.copy2(self.database_file, destino)
