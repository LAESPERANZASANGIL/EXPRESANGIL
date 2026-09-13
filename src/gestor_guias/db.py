"""Capa de dialecto para hablar con SQLite o con Postgres (Supabase).

`repository.py` es el unico acceso a datos y son 66 metodos: duplicarlo en
un archivo paralelo para Postgres garantizaria que los dos se
desincronizaran con el primer cambio. En vez de eso, el repositorio escribe
SQL en un subconjunto portable y esta capa traduce lo que cada motor
entiende distinto:

- Marcadores: SQLite usa `?`, Postgres usa `%s`.
- `INSERT OR REPLACE` de SQLite se vuelve `ON CONFLICT (pk) DO UPDATE`.
- Las filas se devuelven siempre como diccionarios.
- El id recien insertado: `lastrowid` en SQLite, `RETURNING id` en Postgres.

Lo que NO se traduce, porque es propio de SQLite y no tiene sentido en
Postgres, son los `PRAGMA` y los respaldos por archivo: en Supabase la
integridad y las copias las administra el propio servicio.
"""

from __future__ import annotations

from contextlib import closing, contextmanager
import re
import sqlite3

SQLITE = "sqlite"
POSTGRES = "postgres"

# Clave primaria de cada tabla, para traducir `INSERT OR REPLACE`.
CLAVES_PRIMARIAS = {
    "guias": ("guia",),
    "guias_archivo": ("guia",),
    "operadores": ("usuario",),
    "cierres_operador": ("fecha", "operador"),
    "cierres_generales": ("fecha",),
    "nomina": ("periodo", "empleado"),
    "liquidaciones_semanales": ("semana_inicio", "empleado"),
}

_INSERT_OR_REPLACE = re.compile(
    r"INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]*)\)", re.IGNORECASE | re.DOTALL
)


def traducir_marcadores(sql: str) -> str:
    """Cambia los `?` de SQLite por los `%s` de Postgres.

    Dos cuidados, comprobados contra psycopg:

    - Un `?` dentro de una cadena literal es un signo de interrogacion, no
      un marcador: se deja como esta.
    - Un `%` literal **si** hay que escaparlo como `%%`, tambien dentro de
      comillas: psycopg revisa toda la consulta y un `LIKE '%b%'` sin
      escapar falla con "only '%s', '%b', '%t' are allowed as placeholders".
    """
    resultado: list[str] = []
    comilla: str | None = None
    for caracter in sql:
        if caracter == "%":
            # Siempre, dentro o fuera de comillas.
            resultado.append("%%")
        elif comilla:
            resultado.append(caracter)
            if caracter == comilla:
                comilla = None
        elif caracter in ("'", '"'):
            comilla = caracter
            resultado.append(caracter)
        elif caracter == "?":
            resultado.append("%s")
        else:
            resultado.append(caracter)
    return "".join(resultado)


def traducir_insert_or_replace(sql: str) -> str:
    """`INSERT OR REPLACE` de SQLite -> `ON CONFLICT ... DO UPDATE` de Postgres.

    Postgres no tiene `INSERT OR REPLACE`; el equivalente necesita saber por
    que columnas hay conflicto, de ahi `CLAVES_PRIMARIAS`.
    """
    coincidencia = _INSERT_OR_REPLACE.search(sql)
    if coincidencia is None:
        return sql

    tabla = coincidencia.group(1)
    columnas = [c.strip() for c in coincidencia.group(2).split(",") if c.strip()]
    clave = CLAVES_PRIMARIAS.get(tabla)
    if clave is None:
        raise ValueError(
            f"No se conoce la clave primaria de '{tabla}': agregala a "
            "CLAVES_PRIMARIAS para poder traducir INSERT OR REPLACE."
        )

    actualizables = [c for c in columnas if c not in clave]
    asignaciones = ", ".join(f"{c} = EXCLUDED.{c}" for c in actualizables)
    sql = sql.replace(coincidencia.group(0), f"INSERT INTO {tabla} ({coincidencia.group(2)})", 1)
    conflicto = f" ON CONFLICT ({', '.join(clave)}) DO "
    conflicto += f"UPDATE SET {asignaciones}" if actualizables else "NOTHING"
    return sql.rstrip().rstrip(";") + conflicto


def adaptar(sql: str, motor: str) -> str:
    """Deja el SQL listo para el motor indicado."""
    if motor == SQLITE:
        return sql
    return traducir_marcadores(traducir_insert_or_replace(sql))


class Conexion:
    """Envoltura sobre la conexion del motor, con una interfaz comun.

    Devuelve siempre filas como diccionarios: `repository.py` las consume
    por nombre de columna, y asi da igual el motor de abajo.
    """

    def __init__(self, conexion, motor: str) -> None:
        self._conexion = conexion
        self.motor = motor

    @property
    def es_postgres(self) -> bool:
        return self.motor == POSTGRES

    def execute(self, sql: str, parametros=()):
        return self._conexion.execute(adaptar(sql, self.motor), parametros)

    def executemany(self, sql: str, secuencia):
        """Devuelve el cursor en los dos motores: hay quien lee `rowcount`."""
        sentencia = adaptar(sql, self.motor)
        if self.motor == SQLITE:
            return self._conexion.executemany(sentencia, secuencia)
        # El cursor no se cierra aqui a proposito: `rowcount` se consulta
        # despues de volver. Se libera al cerrar la conexion.
        cursor = self._conexion.cursor()
        cursor.executemany(sentencia, secuencia)
        return cursor

    def consultar(self, sql: str, parametros=()) -> list[dict]:
        """Todas las filas, como diccionarios."""
        cursor = self.execute(sql, parametros)
        filas = cursor.fetchall()
        if self.motor == SQLITE:
            return [dict(fila) for fila in filas]
        columnas = [d[0] for d in cursor.description]
        return [dict(zip(columnas, fila)) for fila in filas]

    def consultar_una(self, sql: str, parametros=()) -> dict | None:
        filas = self.consultar(sql, parametros)
        return filas[0] if filas else None

    def insertar_devolviendo_id(self, sql: str, parametros=()) -> int:
        """Id de la fila recien insertada, en cualquiera de los dos motores."""
        if self.motor == SQLITE:
            return int(self.execute(sql, parametros).lastrowid)
        cursor = self.execute(sql.rstrip().rstrip(";") + " RETURNING id", parametros)
        return int(cursor.fetchone()[0])

    def commit(self) -> None:
        self._conexion.commit()

    def rollback(self) -> None:
        self._conexion.rollback()

    def close(self) -> None:
        self._conexion.close()


def abrir_sqlite(ruta) -> Conexion:
    conexion = sqlite3.connect(ruta, timeout=30)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA journal_mode=WAL")
    # synchronous=FULL: cada transaccion se confirma al disco antes de darla
    # por buena. Con el valor por defecto un reinicio inesperado del servidor
    # puede dejar la base corrupta, que es justo lo que pasaba.
    conexion.execute("PRAGMA synchronous=FULL")
    conexion.execute("PRAGMA foreign_keys=ON")
    return Conexion(conexion, SQLITE)


def abrir_postgres(dsn: str) -> Conexion:
    """Conexion a Postgres, compatible con el pooler de Supabase.

    `prepare_threshold=None` desactiva las sentencias preparadas. Hacen
    falta desactivarlas porque el pooler en modo transaccion (el puerto
    6543, el unico camino IPv4 en muchos VPS) no las soporta y la conexion
    empieza a fallar con "prepared statement already exists". Aqui no se
    pierde nada: cada operacion abre su propia conexion, asi que una
    sentencia preparada no se llegaria a reutilizar.
    """
    import psycopg

    return Conexion(psycopg.connect(dsn, prepare_threshold=None), POSTGRES)


@contextmanager
def transaccion(conexion: Conexion):
    """Confirma al salir bien, deshace al fallar y **siempre cierra**.

    Las conexiones que no se cerraban fueron la causa de las corrupciones en
    produccion; el cierre no es opcional en ningun motor.
    """
    with closing(conexion):
        try:
            yield conexion
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
