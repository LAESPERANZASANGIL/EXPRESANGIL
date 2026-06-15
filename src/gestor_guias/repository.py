from __future__ import annotations

from pathlib import Path
import sqlite3

import pandas as pd


TABLE_NAME = "guias"


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
                    municipio TEXT,
                    valor TEXT,
                    operador TEXT,
                    estado TEXT,
                    causal TEXT,
                    fecha TEXT,
                    ingreso TEXT,
                    direccion TEXT
                )
                """
            )
            existing_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(guias)").fetchall()
            }
            if "direccion" not in existing_columns:
                connection.execute("ALTER TABLE guias ADD COLUMN direccion TEXT")

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
                    row.get("MUNICIPIO", ""),
                    row.get("VALOR", ""),
                    row.get("OPERADOR", ""),
                    row.get("ESTADO", ""),
                    row.get("CAUSAL", ""),
                    row.get("FECHA", ""),
                    row.get("INGRESO", ""),
                    row.get("DIRECCION", ""),
                )
            )

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO guias (
                    guia, planilla, servicio, unid, tipo_de_servicio,
                    destinatario, municipio, valor, operador, estado,
                    causal, fecha, ingreso, direccion
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guia) DO UPDATE SET
                    planilla = excluded.planilla,
                    servicio = excluded.servicio,
                    unid = excluded.unid,
                    tipo_de_servicio = excluded.tipo_de_servicio,
                    destinatario = excluded.destinatario,
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
                    ingreso = excluded.ingreso,
                    direccion = excluded.direccion
                """,
                records,
            )

    def list_all(self) -> list[dict]:
        self.initialize()
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT * FROM guias ORDER BY rowid").fetchall()
            return [dict(row) for row in rows]

    def update_tracking_fields(self, guia: str, operador: str, estado: str, causal: str) -> None:
        self.initialize()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE guias
                SET operador = ?, estado = ?, causal = ?
                WHERE guia = ?
                """,
                (operador, estado, causal, guia),
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
                SET operador = ?, estado = ?, causal = ?
                WHERE guia = ?
                """,
                [(operador, estado, causal, guia) for guia in clean_guides],
            )
            return cursor.rowcount

    def clear_all(self) -> None:
        self.initialize()
        with self._connect() as connection:
            connection.execute("DELETE FROM guias")

    def to_dataframe(self) -> pd.DataFrame:
        rows = self.list_all()
        columns = [
            "PLANILLA",
            "SERVICIO",
            "GUIA",
            "UNID",
            "TIPO DE SERVICIO",
            "DESTINATARIO",
            "MUNICIPIO",
            "VALOR",
            "OPERADOR",
            "ESTADO",
            "CAUSAL",
            "FECHA",
            "INGRESO",
            "DIRECCION",
        ]
        data = [
            {
                "PLANILLA": row["planilla"],
                "SERVICIO": row["servicio"],
                "GUIA": row["guia"],
                "UNID": row["unid"],
                "TIPO DE SERVICIO": row["tipo_de_servicio"],
                "DESTINATARIO": row["destinatario"],
                "MUNICIPIO": row["municipio"],
                "VALOR": row["valor"],
                "OPERADOR": row["operador"],
                "ESTADO": row["estado"],
                "CAUSAL": row["causal"],
                "FECHA": row["fecha"],
                "INGRESO": row["ingreso"],
                "DIRECCION": row["direccion"] or "",
            }
            for row in rows
        ]
        return pd.DataFrame(data, columns=columns)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_file)
