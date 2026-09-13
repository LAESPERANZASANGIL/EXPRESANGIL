"""Conexion a la base de Expresangil en Supabase (Postgres).

**La cadena de conexion lleva la contraseña y por eso NO va en
`settings.toml`**, que si esta versionado en GitHub: se lee de la variable
de entorno `EXPRESANGIL_DB_DSN`. En el VPS se define en el servicio de
systemd; en Windows, con `setx`.

    postgresql://postgres:CLAVE@db.xxxx.supabase.co:5432/postgres?sslmode=require
"""

from __future__ import annotations

from contextlib import contextmanager
import os

VARIABLE_DSN = "EXPRESANGIL_DB_DSN"

# Las 10 tablas de la aplicacion, en orden de dependencia: `prestamo_abonos`
# apunta a `prestamos`, asi que los prestamos van primero.
TABLAS = (
    "operadores",
    "guias",
    "guias_archivo",
    "cierres_operador",
    "cierres_generales",
    "prestamos",
    "prestamo_abonos",
    "nomina",
    "liquidaciones_semanales",
    "liquidaciones_laborales",
)

# Tablas cuya clave primaria la genera Postgres (IDENTITY). Al migrar hay
# que conservar los ids de SQLite, o los abonos quedarian apuntando a otro
# prestamo, y luego reajustar la secuencia.
TABLAS_CON_IDENTITY = ("prestamos", "prestamo_abonos", "liquidaciones_laborales")


def dsn_configurado() -> str:
    """Cadena de conexion, o cadena vacia si no esta definida."""
    return os.environ.get(VARIABLE_DSN, "").strip()


def exigir_dsn() -> str:
    dsn = dsn_configurado()
    if not dsn:
        raise RuntimeError(
            f"Falta la variable de entorno {VARIABLE_DSN} con la cadena de "
            "conexion a Supabase. No se guarda en settings.toml porque ese "
            "archivo se versiona en GitHub."
        )
    return dsn


@contextmanager
def conectar(dsn: str = ""):
    """Conexion a Postgres que se cierra siempre.

    Mismo criterio que con SQLite: las conexiones que no se cierran fueron
    la causa de las corrupciones en produccion.
    """
    # Import diferido: sin psycopg instalado, el resto de la aplicacion
    # (que hoy sigue sobre SQLite) tiene que seguir arrancando.
    import psycopg

    conexion = psycopg.connect(dsn or exigir_dsn())
    try:
        yield conexion
        conexion.commit()
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()
