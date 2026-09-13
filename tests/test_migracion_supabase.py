"""Pruebas de la migracion de SQLite a Postgres.

Las que necesitan una base Postgres se saltan si no hay una disponible:
en Windows el desarrollador normalmente no la tiene. Para correrlas, define
`EXPRESANGIL_TEST_DSN` apuntando a una base de pruebas **vacia y
descartable** (nunca a produccion: la migracion vacia las tablas).
"""

from pathlib import Path
import os
import sqlite3

import pytest

from gestor_guias.migracion_supabase import contar_en_destino, migrar
from gestor_guias.repository import GuiaRepository
from gestor_guias.supabase_db import TABLAS, TABLAS_CON_IDENTITY, VARIABLE_DSN, dsn_configurado

import test_repository as ayudas

DSN_PRUEBAS = os.environ.get("EXPRESANGIL_TEST_DSN", "").strip()
sin_postgres = pytest.mark.skipif(
    not DSN_PRUEBAS, reason="define EXPRESANGIL_TEST_DSN para probar contra Postgres"
)

ESQUEMA = Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "0001_esquema_inicial.sql"


def _base_de_ejemplo(tmp_path: Path) -> Path:
    """Base SQLite con guias, empleados, un prestamo y sus abonos."""
    ruta = tmp_path / "guias.db"
    repository = GuiaRepository(ruta)
    repository.save_consolidated(ayudas.build_dataframe("100", "Cliente"))
    repository.crear_operador("pipe", "hash", "PIPE")
    prestamo = repository.crear_prestamo(
        empleado="PIPE", tipo="PRESTAMO", monto=500000, fecha="2026-01-10", cuotas=5
    )
    repository.registrar_abono(prestamo, "2026-02-10", 100000, "cuota 1")
    repository.registrar_abono(prestamo, "2026-03-10", 100000, "cuota 2")
    return ruta


# --------------------------- Sin base de datos ----------------------------

def test_las_tablas_declaradas_son_las_que_crea_sqlite(tmp_path: Path) -> None:
    """Si se agrega una tabla y se olvida en TABLAS, no se migraria."""
    repository = GuiaRepository(tmp_path / "guias.db")
    repository.initialize()
    with sqlite3.connect(tmp_path / "guias.db") as conexion:
        reales = {
            fila[0]
            for fila in conexion.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }

    assert reales == set(TABLAS)


def test_los_prestamos_van_antes_que_sus_abonos() -> None:
    """`prestamo_abonos` tiene llave foranea a `prestamos`."""
    assert TABLAS.index("prestamos") < TABLAS.index("prestamo_abonos")


def test_el_esquema_cubre_todas_las_tablas() -> None:
    sql = ESQUEMA.read_text(encoding="utf-8")
    for tabla in TABLAS:
        assert f"CREATE TABLE IF NOT EXISTS {tabla} " in sql
        # Hay salarios y cedulas: ninguna tabla puede quedar sin RLS.
        assert f"ALTER TABLE {tabla}" in sql and "ENABLE ROW LEVEL SECURITY" in sql


def test_sin_variable_de_entorno_se_avisa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(VARIABLE_DSN, raising=False)
    assert dsn_configurado() == ""


def test_sin_base_de_origen_avisa(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        migrar(tmp_path / "no_existe.db", dsn="postgresql://x/y")


# --------------------------- Contra Postgres ------------------------------

@sin_postgres
def test_migra_todas_las_filas(tmp_path: Path) -> None:
    origen = _base_de_ejemplo(tmp_path)

    copiadas = migrar(origen, dsn=DSN_PRUEBAS)
    destino = contar_en_destino(DSN_PRUEBAS)

    assert copiadas["guias"] == 1
    assert copiadas["operadores"] == 1
    assert copiadas["prestamo_abonos"] == 2
    # Lo que se dice copiado es lo que quedo realmente en el destino.
    for tabla, cantidad in copiadas.items():
        assert destino[tabla] == cantidad


@sin_postgres
def test_conserva_los_ids_y_el_vinculo_de_los_abonos(tmp_path: Path) -> None:
    """Si Postgres regenerara los ids, los abonos colgarian de otro prestamo."""
    import psycopg

    migrar(_base_de_ejemplo(tmp_path), dsn=DSN_PRUEBAS)

    with psycopg.connect(DSN_PRUEBAS) as conexion:
        filas = conexion.execute(
            "SELECT p.empleado, COUNT(a.id) FROM prestamos p "
            "JOIN prestamo_abonos a ON a.prestamo_id = p.id GROUP BY p.empleado"
        ).fetchall()

    assert filas == [("PIPE", 2)]


@sin_postgres
def test_la_secuencia_queda_lista_para_el_siguiente_registro(tmp_path: Path) -> None:
    """Sin reajustar la secuencia, el proximo prestamo chocaria por id repetido."""
    import psycopg

    migrar(_base_de_ejemplo(tmp_path), dsn=DSN_PRUEBAS)

    with psycopg.connect(DSN_PRUEBAS) as conexion:
        nuevo = conexion.execute(
            "INSERT INTO prestamos (empleado, tipo, monto, fecha) "
            "VALUES ('NUEVO', 'PRESTAMO', 1, '2026-09-13') RETURNING id"
        ).fetchone()[0]

    assert nuevo > 1


@sin_postgres
def test_repetir_la_migracion_no_duplica(tmp_path: Path) -> None:
    origen = _base_de_ejemplo(tmp_path)

    migrar(origen, dsn=DSN_PRUEBAS)
    migrar(origen, dsn=DSN_PRUEBAS)

    assert contar_en_destino(DSN_PRUEBAS)["guias"] == 1


@sin_postgres
def test_las_tablas_con_identity_son_las_que_tienen_id() -> None:
    import psycopg

    with psycopg.connect(DSN_PRUEBAS) as conexion:
        con_id = {
            fila[0]
            for fila in conexion.execute(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema='public' AND column_name='id'"
            )
        }

    assert con_id == set(TABLAS_CON_IDENTITY)
