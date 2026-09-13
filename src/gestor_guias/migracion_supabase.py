"""Copia los datos de la base SQLite a la base de Supabase (Postgres).

Primera fase de la mudanza: el aplicativo sigue funcionando sobre SQLite y
esta migracion deja los datos en Supabase para poder verificarlos antes de
conmutar. Se puede correr las veces que haga falta.

Nada se borra de SQLite: el origen queda intacto.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from .supabase_db import TABLAS, TABLAS_CON_IDENTITY, conectar


def _columnas_sqlite(conexion: sqlite3.Connection, tabla: str) -> list[str]:
    return [fila[1] for fila in conexion.execute(f"PRAGMA table_info({tabla})")]


def _tabla_existe(conexion: sqlite3.Connection, tabla: str) -> bool:
    fila = conexion.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)
    ).fetchone()
    return fila is not None


def migrar(base_sqlite: Path, dsn: str = "", vaciar: bool = True) -> dict[str, int]:
    """Copia todas las tablas y devuelve cuantas filas quedaron en cada una.

    Con `vaciar` (por defecto) la tabla destino se limpia antes de copiar,
    para que repetir la migracion no duplique ni deje filas viejas de una
    corrida anterior. Todo ocurre en **una sola transaccion**: si algo falla
    a mitad de camino, Supabase queda como estaba y no a medias.
    """
    base_sqlite = Path(base_sqlite)
    if not base_sqlite.is_file():
        raise FileNotFoundError(f"No existe la base de origen {base_sqlite}.")

    copiadas: dict[str, int] = {}
    with closing(sqlite3.connect(base_sqlite)) as origen, conectar(dsn) as destino:
        origen.row_factory = sqlite3.Row
        cursor = destino.cursor()

        if vaciar:
            # En orden inverso por las llaves foraneas (abonos antes que prestamos).
            for tabla in reversed(TABLAS):
                cursor.execute(f"DELETE FROM {tabla}")

        for tabla in TABLAS:
            if not _tabla_existe(origen, tabla):
                copiadas[tabla] = 0
                continue

            columnas = _columnas_sqlite(origen, tabla)
            filas = origen.execute(f"SELECT * FROM {tabla}").fetchall()
            if not filas:
                copiadas[tabla] = 0
                continue

            lista = ", ".join(columnas)
            marcas = ", ".join(["%s"] * len(columnas))
            sentencia = f"INSERT INTO {tabla} ({lista}) VALUES ({marcas})"
            if tabla in TABLAS_CON_IDENTITY:
                # Conserva los ids del origen: `prestamo_abonos` apunta a
                # `prestamos.id`, y si Postgres los regenerara, los abonos
                # quedarian colgando de otro prestamo.
                sentencia = (
                    f"INSERT INTO {tabla} ({lista}) OVERRIDING SYSTEM VALUE "
                    f"VALUES ({marcas})"
                )

            cursor.executemany(sentencia, [tuple(fila) for fila in filas])
            copiadas[tabla] = len(filas)

        # Las secuencias de IDENTITY no avanzan solas al insertar ids
        # explicitos: sin esto, el primer prestamo nuevo chocaria con uno ya
        # migrado por clave duplicada.
        for tabla in TABLAS_CON_IDENTITY:
            cursor.execute(
                f"SELECT setval(pg_get_serial_sequence('{tabla}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {tabla}), 1), "
                f"(SELECT COUNT(*) FROM {tabla}) > 0)"
            )

    return copiadas


def contar_en_destino(dsn: str = "") -> dict[str, int]:
    """Filas por tabla en Supabase, para comprobar que la copia cuadra."""
    conteos: dict[str, int] = {}
    with conectar(dsn) as conexion:
        cursor = conexion.cursor()
        for tabla in TABLAS:
            cursor.execute(f"SELECT COUNT(*) FROM {tabla}")
            conteos[tabla] = int(cursor.fetchone()[0])
    return conteos
