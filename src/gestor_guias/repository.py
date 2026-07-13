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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS cierres_generales (
                    fecha TEXT PRIMARY KEY,
                    denominaciones TEXT NOT NULL DEFAULT '{}',
                    efectivo_contado INTEGER NOT NULL DEFAULT 0
                )
                """
            )
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
        entrega = fecha_entrega(estado)
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
        servicio: str | None = None,
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

    # Las guias entregadas (estado E) no se borran con las herramientas de
    # limpieza: solo salen de la zona de trabajo con el cierre mensual
    # (archivar_entregadas), porque alimentan el informe final del mes.
    _PROTEGER_ENTREGADAS = "UPPER(TRIM(estado)) != 'E'"

    def clear_all(self) -> None:
        self.initialize()
        self._backup_antes_de_borrar()
        with self._connect() as connection:
            connection.execute(f"DELETE FROM guias WHERE {self._PROTEGER_ENTREGADAS}")

    def delete_many(self, guias: list[str]) -> int:
        self.initialize()
        clean_guides = [guia.strip() for guia in guias if guia.strip()]
        if not clean_guides:
            return 0

        self._backup_antes_de_borrar()
        with self._connect() as connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                f"SELECT {', '.join(self._COLUMNAS_GUIA)} FROM guias WHERE {where}",
                params,
            ).fetchall()
            return [dict(row) for row in rows]

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
        with self._connect() as connection:
            connection.executemany(
                f"INSERT OR REPLACE INTO guias ({columnas}) VALUES ({marcadores})",
                [tuple(row[col] for col in self._COLUMNAS_GUIA) for row in rows],
            )
            return len(rows)

    def guardar_cierre_general(self, fecha: str, denominaciones: dict[int, int], efectivo_contado: int) -> None:
        """Guarda el conteo de billetes del cierre general del dia (para el informe diario)."""
        self.initialize()
        with self._connect() as connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
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
            ).fetchall()
            return [dict(row) for row in rows]

    def eliminar_entregadas_mes(self, anio: int, mes: int) -> dict:
        """Borra definitivamente las entregadas del mes (archivo + zona de trabajo).

        Es la unica via para eliminar guias E: accion explicita del admin
        desde Entregas del Mes. Hace respaldo antes de borrar.
        """
        self.initialize()
        self._backup_antes_de_borrar()
        prefijo = f"{anio:04d}-{mes:02d}%"
        with self._connect() as connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
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
        with self._connect() as connection:
            # Cierra TODAS las guias del repartidor en reparto, sin importar la
            # fecha de importacion, y estampa F_ENTREGA con la fecha del cierre.
            cursor = connection.execute(
                "UPDATE guias SET estado = ?, ingreso = ? WHERE operador = ? AND estado = ?",
                (nuevo_estado, entrega, operador, estado_actual),
            )
            return cursor.rowcount

    def revertir_cierre_operador(self, operador: str, fecha: str) -> int:
        self.initialize()
        with self._connect() as connection:
            # Se filtra por F_ENTREGA (columna "ingreso"): son las guias que se
            # cerraron ESE dia, sin importar cuando se importaron.
            cursor = connection.execute(
                "UPDATE guias SET estado = 'R', ingreso = '' WHERE operador = ? AND ingreso LIKE ? AND estado = 'E'",
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
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            # Guias que el repartidor gestiono ESE dia: se filtran por F_ENTREGA
            # (fecha de gestion), no por la fecha de importacion.
            rows = connection.execute(
                "SELECT * FROM guias WHERE operador = ? AND ingreso LIKE ?",
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

    def sumar_totales_cierres_dia(self, fecha: str) -> dict:
        self.initialize()
        with self._connect() as connection:
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

    # Cantidad maxima de respaldos automaticos que se conservan. Sin este
    # limite la carpeta backups/ crecia con cada borrado hasta llenar el
    # disco del servidor y SQLite empezaba a fallar con "disk I/O error".
    MAX_BACKUPS = 10

    def _backup_antes_de_borrar(self) -> None:
        # Copia de seguridad de la base completa antes de un borrado masivo,
        # para poder recuperar la informacion si el borrado fue un error.
        if not self.database_file.exists():
            return
        carpeta_backup = self.database_file.parent / "backups"
        carpeta_backup.mkdir(parents=True, exist_ok=True)

        # Vuelca el WAL al archivo principal para que la copia quede completa
        # y el .db-wal no crezca sin limite.
        with self._connect() as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        marca = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        destino = carpeta_backup / f"{self.database_file.stem}_{marca}.db"
        shutil.copy2(self.database_file, destino)

        # Rotacion: conserva solo los respaldos mas recientes.
        respaldos = sorted(carpeta_backup.glob(f"{self.database_file.stem}_*.db"))
        for viejo in respaldos[:-self.MAX_BACKUPS]:
            viejo.unlink(missing_ok=True)
