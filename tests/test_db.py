"""Pruebas de la capa de dialecto entre SQLite y Postgres.

La traduccion se prueba sola (sin base) y, cuando hay Postgres disponible,
las mismas sentencias se ejecutan de verdad en los dos motores: que traduzca
bonito no sirve de nada si el motor luego la rechaza.
"""

from pathlib import Path
import os

import pytest

from gestor_guias.db import (
    POSTGRES,
    SQLITE,
    abrir_postgres,
    abrir_sqlite,
    adaptar,
    traducir_insert_or_replace,
    traducir_marcadores,
    transaccion,
)

DSN_PRUEBAS = os.environ.get("EXPRESANGIL_TEST_DSN", "").strip()
sin_postgres = pytest.mark.skipif(
    not DSN_PRUEBAS, reason="define EXPRESANGIL_TEST_DSN para probar contra Postgres"
)


# ------------------------------ Traduccion --------------------------------

def test_los_marcadores_cambian_a_los_de_postgres() -> None:
    assert traducir_marcadores("SELECT * FROM g WHERE a = ? AND b = ?") == (
        "SELECT * FROM g WHERE a = %s AND b = %s"
    )


def test_una_interrogacion_dentro_de_comillas_no_es_marcador() -> None:
    """`'x?y'` es texto, no un parametro."""
    assert traducir_marcadores("SELECT * FROM g WHERE a = 'x?y' AND b = ?") == (
        "SELECT * FROM g WHERE a = 'x?y' AND b = %s"
    )


def test_el_porcentaje_literal_se_escapa() -> None:
    """Sin escapar, psycopg rechaza la consulta entera."""
    assert traducir_marcadores("SELECT 1 WHERE x LIKE '%b%'") == (
        "SELECT 1 WHERE x LIKE '%%b%%'"
    )


def test_en_sqlite_no_se_toca_nada() -> None:
    sql = "INSERT OR REPLACE INTO guias (guia, estado) VALUES (?, ?)"
    assert adaptar(sql, SQLITE) == sql


def test_insert_or_replace_se_vuelve_on_conflict() -> None:
    traducido = adaptar(
        "INSERT OR REPLACE INTO guias (guia, estado, valor) VALUES (?, ?, ?)", POSTGRES
    )

    assert traducido.startswith("INSERT INTO guias (guia, estado, valor)")
    assert "ON CONFLICT (guia) DO UPDATE SET" in traducido
    # La clave primaria no se actualiza a si misma.
    assert "guia = EXCLUDED.guia" not in traducido
    assert "estado = EXCLUDED.estado" in traducido


def test_insert_or_replace_con_clave_compuesta() -> None:
    traducido = adaptar(
        "INSERT OR REPLACE INTO cierres_operador (fecha, operador, e) VALUES (?, ?, ?)",
        POSTGRES,
    )

    assert "ON CONFLICT (fecha, operador) DO UPDATE SET e = EXCLUDED.e" in traducido


def test_una_tabla_desconocida_avisa_en_vez_de_generar_sql_roto() -> None:
    with pytest.raises(ValueError, match="clave primaria"):
        traducir_insert_or_replace("INSERT OR REPLACE INTO inventada (a) VALUES (?)")


# --------------------- Misma sentencia en los dos motores ------------------

ESQUEMA = Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "0001_esquema_inicial.sql"


def _crear_guias_en_sqlite(tmp_path: Path):
    conexion = abrir_sqlite(tmp_path / "g.db")
    conexion.execute(
        "CREATE TABLE guias (guia TEXT PRIMARY KEY, estado TEXT, valor TEXT)"
    )
    return conexion


def test_sqlite_devuelve_las_filas_como_diccionarios(tmp_path: Path) -> None:
    with transaccion(_crear_guias_en_sqlite(tmp_path)) as conexion:
        conexion.execute("INSERT INTO guias (guia, estado) VALUES (?, ?)", ("100", "E"))
        filas = conexion.consultar("SELECT guia, estado FROM guias")

    assert filas == [{"guia": "100", "estado": "E"}]


@sin_postgres
def test_postgres_devuelve_las_filas_como_diccionarios() -> None:
    with transaccion(abrir_postgres(DSN_PRUEBAS)) as conexion:
        conexion.execute("DELETE FROM guias")
        conexion.execute("INSERT INTO guias (guia, estado) VALUES (?, ?)", ("100", "E"))
        filas = conexion.consultar("SELECT guia, estado FROM guias")

    assert filas == [{"guia": "100", "estado": "E"}]


@sin_postgres
def test_insert_or_replace_se_comporta_igual_en_los_dos_motores(tmp_path: Path) -> None:
    """Repetir la misma guia debe actualizarla, no fallar por clave repetida."""
    sentencia = "INSERT OR REPLACE INTO guias (guia, estado) VALUES (?, ?)"

    resultados = []
    for conexion in (_crear_guias_en_sqlite(tmp_path), abrir_postgres(DSN_PRUEBAS)):
        with transaccion(conexion) as abierta:
            if abierta.es_postgres:
                abierta.execute("DELETE FROM guias")
            abierta.execute(sentencia, ("100", "R"))
            abierta.execute(sentencia, ("100", "E"))
            resultados.append(abierta.consultar("SELECT guia, estado FROM guias"))

    assert resultados[0] == resultados[1] == [{"guia": "100", "estado": "E"}]


@sin_postgres
def test_el_id_insertado_se_obtiene_igual_en_los_dos_motores(tmp_path: Path) -> None:
    """En SQLite es `lastrowid`; en Postgres hay que pedir `RETURNING id`."""
    conexion = abrir_sqlite(tmp_path / "g.db")
    conexion.execute(
        "CREATE TABLE prestamos (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "empleado TEXT NOT NULL, tipo TEXT NOT NULL, monto INTEGER NOT NULL, fecha TEXT NOT NULL)"
    )
    inserta = (
        "INSERT INTO prestamos (empleado, tipo, monto, fecha) VALUES (?, ?, ?, ?)"
    )
    datos = ("PIPE", "PRESTAMO", 1000, "2026-09-13")

    ids = []
    for abierta in (conexion, abrir_postgres(DSN_PRUEBAS)):
        with transaccion(abierta) as activa:
            if activa.es_postgres:
                activa.execute("DELETE FROM prestamo_abonos")
                activa.execute("DELETE FROM prestamos")
            ids.append(activa.insertar_devolviendo_id(inserta, datos))

    assert all(isinstance(identificador, int) and identificador > 0 for identificador in ids)


@sin_postgres
def test_un_fallo_deshace_toda_la_transaccion() -> None:
    """Si algo revienta a mitad, no puede quedar media operacion escrita."""
    with pytest.raises(RuntimeError):
        with transaccion(abrir_postgres(DSN_PRUEBAS)) as conexion:
            conexion.execute("DELETE FROM guias")
            conexion.execute("INSERT INTO guias (guia, estado) VALUES (?, ?)", ("999", "E"))
            raise RuntimeError("algo salio mal")

    with transaccion(abrir_postgres(DSN_PRUEBAS)) as conexion:
        assert conexion.consultar("SELECT guia FROM guias WHERE guia = ?", ("999",)) == []
