from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

import pandas as pd


TABLE_NAME = "guias"

# Operador por defecto para guias importadas que aun no tienen seguimiento:
# quedan en bodega ("BODEGA") con el ESTADO vacio hasta que salgan a reparto.
OPERADOR_BODEGA = "BODEGA"

# Estados de gestion del dia: al alcanzarlos se estampa F_ENTREGA con la fecha
# real de la operacion (entregada "E", devolucion "D", novedades "RO"/"N").
# Es la fecha por la que se generan los informes y el resumen del cierre, sin
# importar en que dia se importo la guia.
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

    def save_consolidated(self, dataframe: pd.DataFrame) -> None:
        self.initialize()
        records = []
        for row in dataframe.to_dict(orient="records"):
            guia = row.get("GUIA", "")
            if not guia:
                continue

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
                    row.get("OPERADOR", ""),
                    row.get("ESTADO", ""),
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
            connection.execute(
                "UPDATE guias SET operador = ? WHERE TRIM(COALESCE(operador, '')) = ''",
                (OPERADOR_BODEGA,),
            )
            # Regla: si la guia esta en BODEGA (aun no asignada), su ESTADO va vacio.
            connection.execute(
                "UPDATE guias SET estado = '' WHERE operador = ?",
                (OPERADOR_BODEGA,),
            )

    def list_all(self) -> list[dict]:
        self.initialize()
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT * FROM guias ORDER BY rowid").fetchall()
            return [dict(row) for row in rows]

    def update_tracking_fields(self, guia: str, operador: str, estado: str, causal: str) -> None:
        self.initialize()
        entrega = fecha_entrega(estado)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE guias
                SET operador = ?, estado = ?, causal = ?,
                    ingreso = CASE
                        WHEN ? = '' THEN ''
                        WHEN TRIM(COALESCE(ingreso, '')) = '' THEN ?
                        ELSE ingreso
                    END
                WHERE guia = ?
                """,
                (operador, estado, causal, entrega, entrega, guia),
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
                SET operador = ?, estado = ?, causal = ?,
                    ingreso = CASE
                        WHEN ? = '' THEN ''
                        WHEN TRIM(COALESCE(ingreso, '')) = '' THEN ?
                        ELSE ingreso
                    END
                WHERE guia = ?
                """,
                [(operador, estado, causal, entrega, entrega, guia) for guia in clean_guides],
            )
            return cursor.rowcount

    def clear_all(self) -> None:
        self.initialize()
        with self._connect() as connection:
            connection.execute("DELETE FROM guias")

    def delete_many(self, guias: list[str]) -> int:
        self.initialize()
        clean_guides = [guia.strip() for guia in guias if guia.strip()]
        if not clean_guides:
            return 0

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

        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM guias WHERE fecha LIKE ?", (f"{fecha}%",))
            return cursor.rowcount

    def delete_by_operador(self, operador: str) -> int:
        self.initialize()
        operador = operador.strip()
        if not operador:
            return 0

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

        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM guias WHERE estado = ?", (estado,))
            return cursor.rowcount

    def crear_operador(
        self, usuario: str, password_hash: str, nombre: str, rol: str = "operador"
    ) -> None:
        self.initialize()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO operadores (usuario, password_hash, nombre, rol)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(usuario) DO UPDATE SET
                    password_hash = excluded.password_hash,
                    nombre = excluded.nombre,
                    rol = excluded.rol
                """,
                (usuario, password_hash, nombre, rol),
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
                "SELECT usuario, nombre, rol FROM operadores ORDER BY nombre"
            ).fetchall()
            return [dict(row) for row in rows]

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

    def asignar_salida(self, guias: list[str], operador: str, estado: str) -> int:
        self.initialize()
        clean_guides = [guia.strip() for guia in guias if guia.strip()]
        if not clean_guides:
            return 0

        with self._connect() as connection:
            cursor = connection.executemany(
                "UPDATE guias SET operador = ?, estado = ? WHERE guia = ?",
                [(operador, estado, guia) for guia in clean_guides],
            )
            return cursor.rowcount

    def registrar_novedad(
        self,
        guias: list[str],
        operador: str,
        fecha: str,
        estado_actual: str,
        nuevo_estado: str,
    ) -> int:
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
                WHERE guia = ? AND operador = ? AND estado = ?
                """,
                [
                    (nuevo_estado, entrega, guia, operador, estado_actual)
                    for guia in clean_guides
                ],
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
    ) -> None:
        self.initialize()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO cierres_operador (
                    fecha, operador, gestionadas, ro, n, d, e,
                    recaudado, bancos, nequi, envia, efectivo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    efectivo = excluded.efectivo
                """,
                (fecha, operador, gestionadas, ro, n, d, e, recaudado, bancos, nequi, envia, efectivo),
            )

    def obtener_cierre(self, fecha: str, operador: str) -> dict | None:
        self.initialize()
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM cierres_operador WHERE fecha = ? AND operador = ?",
                (fecha, operador),
            ).fetchone()
            return dict(row) if row else None

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
        return sqlite3.connect(self.database_file)
