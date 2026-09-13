"""El repositorio debe comportarse igual en SQLite y en Postgres.

La capa de dialecto traduce el SQL, pero lo que importa es que el negocio
de un resultado identico en los dos motores. Cada prueba corre dos veces:
contra un archivo SQLite y, si hay `EXPRESANGIL_TEST_DSN`, contra Postgres.
"""

from pathlib import Path
import os

import pandas as pd
import pytest

from gestor_guias.config import load_settings
from gestor_guias.db import transaccion
from gestor_guias.repository import GuiaRepository
from gestor_guias.supabase_db import TABLAS

DSN_PRUEBAS = os.environ.get("EXPRESANGIL_TEST_DSN", "").strip()

MOTORES = [
    pytest.param("sqlite", id="sqlite"),
    pytest.param(
        "postgres",
        id="postgres",
        marks=pytest.mark.skipif(
            not DSN_PRUEBAS, reason="define EXPRESANGIL_TEST_DSN para probar Postgres"
        ),
    ),
]


@pytest.fixture(params=MOTORES)
def repositorio(request, tmp_path: Path) -> GuiaRepository:
    if request.param == "sqlite":
        return GuiaRepository(tmp_path / "guias.db")

    repository = GuiaRepository(tmp_path / "no_se_usa.db", dsn=DSN_PRUEBAS)
    # Base compartida: se deja limpia antes de cada prueba.
    with transaccion(repository._connect()) as conexion:
        conexion.execute(f"TRUNCATE {', '.join(TABLAS)}")
    return repository


def _guia(numero: str) -> dict:
    fila = {columna: "" for columna in load_settings().excel.columns}
    fila.update(
        GUIA=numero,
        DESTINATARIO=f"Cliente {numero}",
        VALOR="7000",
        MUNICIPIO="SAN GIL",
        F_INGRESO="2026-09-13",
        SERVICIO="CE",
        UNID="1",
    )
    return fila


def test_importar_y_listar(repositorio: GuiaRepository) -> None:
    repositorio.save_consolidated(pd.DataFrame([_guia("200"), _guia("201")]))

    assert repositorio.to_dataframe()["GUIA"].tolist() == ["200", "201"]


def test_reimportar_la_misma_guia_la_actualiza_sin_duplicar(
    repositorio: GuiaRepository,
) -> None:
    """El `INSERT OR REPLACE` traducido debe actualizar, no fallar ni duplicar."""
    repositorio.save_consolidated(pd.DataFrame([_guia("200")]))
    cambiada = _guia("200")
    cambiada["DESTINATARIO"] = "Cliente corregido"
    repositorio.save_consolidated(pd.DataFrame([cambiada]))

    filas = repositorio.to_dataframe()
    assert len(filas) == 1
    assert filas.iloc[0]["DESTINATARIO"] == "Cliente corregido"


def test_operadores_y_roles(repositorio: GuiaRepository) -> None:
    repositorio.crear_operador("pipe", "hash", "PIPE")
    repositorio.crear_operador("jefe", "hash", "JEFE", rol="admin")

    assert [o["usuario"] for o in repositorio.listar_operadores()] == ["jefe", "pipe"]
    assert repositorio.obtener_operador("pipe")["nombre"] == "PIPE"
    assert repositorio.contar_admins() == 1


def test_salida_novedad_y_entrega(repositorio: GuiaRepository) -> None:
    repositorio.save_consolidated(
        pd.DataFrame([_guia("200"), _guia("201"), _guia("202")])
    )
    repositorio.crear_operador("pipe", "hash", "PIPE")

    asignadas, faltantes = repositorio.asignar_salida(["200", "201"], "PIPE", "R")
    repositorio.update_tracking_fields("202", "PIPE", "RO", "")
    repositorio.update_tracking_fields("200", "PIPE", "E", "")

    assert (asignadas, faltantes) == (2, [])
    estados = {f["GUIA"]: f["ESTADO"] for f in repositorio.to_dataframe().to_dict("records")}
    assert estados == {"200": "E", "201": "R", "202": "RO"}


def test_prestamos_y_abonos_conservan_su_vinculo(repositorio: GuiaRepository) -> None:
    """El id lo da `lastrowid` o `RETURNING`, segun el motor."""
    repositorio.crear_operador("pipe", "hash", "PIPE")
    prestamo = repositorio.crear_prestamo(
        empleado="PIPE", tipo="PRESTAMO", monto=500000, fecha="2026-01-10", cuotas=5
    )
    abono = repositorio.registrar_abono(prestamo, "2026-02-10", 100000, "cuota 1")

    assert isinstance(prestamo, int) and prestamo > 0
    assert isinstance(abono, int) and abono > 0
    assert [p["id"] for p in repositorio.listar_prestamos()] == [prestamo]
    assert repositorio.obtener_prestamo(prestamo)["empleado"] == "PIPE"


def test_renombrar_arrastra_el_historial(repositorio: GuiaRepository) -> None:
    repositorio.save_consolidated(pd.DataFrame([_guia("200")]))
    repositorio.crear_operador("pipe", "hash", "PIPE")
    repositorio.update_tracking_fields("200", "PIPE", "E", "")
    repositorio.crear_prestamo(
        empleado="PIPE", tipo="PRESTAMO", monto=1000, fecha="2026-01-10", cuotas=1
    )

    resultado = repositorio.renombrar_operador("pipe", "FELIPE")

    assert resultado["nombre_anterior"] == "PIPE"
    assert resultado["cambios"] == {"guias": 1, "prestamos": 1}
    assert repositorio.to_dataframe().iloc[0]["OPERADOR"] == "FELIPE"


def test_archivar_entregadas_y_consultar_el_mes(repositorio: GuiaRepository) -> None:
    repositorio.save_consolidated(pd.DataFrame([_guia("200"), _guia("201")]))
    repositorio.crear_operador("pipe", "hash", "PIPE")
    repositorio.update_tracking_fields("200", "PIPE", "E", "")

    archivadas = repositorio.archivar_entregadas()

    assert archivadas == 1
    # La entregada sale de la zona de trabajo pero sigue consultable.
    assert repositorio.to_dataframe()["GUIA"].tolist() == ["201"]
    assert len(repositorio.entregadas_mes(2026, 9)) == 1


def test_la_guia_entregada_no_se_borra(repositorio: GuiaRepository) -> None:
    """Regla del negocio: las `E` estan protegidas contra borrado."""
    repositorio.save_consolidated(pd.DataFrame([_guia("200"), _guia("201")]))
    repositorio.crear_operador("pipe", "hash", "PIPE")
    repositorio.update_tracking_fields("200", "PIPE", "E", "")

    repositorio.delete_by_estado("E")

    assert "200" in repositorio.to_dataframe()["GUIA"].tolist()


def test_la_base_responde(repositorio: GuiaRepository) -> None:
    assert repositorio.verificar_integridad() == "ok"
