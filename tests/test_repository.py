from pathlib import Path

import pandas as pd

from gestor_guias.repository import GuiaRepository


def build_dataframe(guia: str, destinatario: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "PLANILLA": "1",
                "SERVICIO": "",
                "GUIA": guia,
                "UNID": "1",
                "TIPO DE SERVICIO": "PT",
                "DESTINATARIO": destinatario,
                "MUNICIPIO": "SAN GIL",
                "VALOR": "$ -",
                "OPERADOR": "",
                "ESTADO": "",
                "CAUSAL": "",
                "F_INGRESO": "2026-06-09 00:00:00",
                "F_ENTREGA": "",
            }
        ]
    )


def test_import_preserves_existing_data_and_tracking_fields(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))
    repository.update_tracking_fields("100", "Operador 1", "Entregado", "Sin causal")
    repository.save_consolidated(build_dataframe("200", "Persona B"))

    dataframe = repository.to_dataframe()

    assert list(dataframe["GUIA"]) == ["100", "200"]
    assert dataframe.loc[0, "OPERADOR"] == "Operador 1"
    assert dataframe.loc[0, "ESTADO"] == "Entregado"
    assert dataframe.loc[0, "CAUSAL"] == "Sin causal"


def test_import_asigna_bodega_y_estado_r_por_defecto(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))
    repository.update_tracking_fields("100", "KEVIN", "E", "")
    repository.save_consolidated(build_dataframe("200", "Persona B"))

    dataframe = repository.to_dataframe().set_index("GUIA")

    assert dataframe.loc["200", "OPERADOR"] == "BODEGA"
    assert dataframe.loc["200", "ESTADO"] == "R"
    # Las guias con seguimiento existente no se tocan.
    assert dataframe.loc["100", "OPERADOR"] == "KEVIN"
    assert dataframe.loc["100", "ESTADO"] == "E"


def test_clear_all_removes_saved_data(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))
    repository.clear_all()

    assert repository.to_dataframe().empty


def test_update_many_tracking_fields(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))
    repository.save_consolidated(build_dataframe("200", "Persona B"))

    updated = repository.update_many_tracking_fields(
        ["100", "200"],
        "Operador Masivo",
        "Entregado",
        "Sin causal",
    )
    dataframe = repository.to_dataframe()

    assert updated == 2
    assert list(dataframe["OPERADOR"]) == ["Operador Masivo", "Operador Masivo"]
    assert list(dataframe["ESTADO"]) == ["Entregado", "Entregado"]
    assert list(dataframe["CAUSAL"]) == ["Sin causal", "Sin causal"]


def test_delete_many(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))
    repository.save_consolidated(build_dataframe("200", "Persona B"))

    deleted = repository.delete_many(["100"])
    dataframe = repository.to_dataframe()

    assert deleted == 1
    assert list(dataframe["GUIA"]) == ["200"]


def test_delete_by_fecha(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))

    other = build_dataframe("200", "Persona B")
    other["F_INGRESO"] = "2026-06-10 00:00:00"
    repository.save_consolidated(other)

    deleted = repository.delete_by_fecha("2026-06-09")
    dataframe = repository.to_dataframe()

    assert deleted == 1
    assert list(dataframe["GUIA"]) == ["200"]


def test_delete_by_operador_ignores_case(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))
    repository.save_consolidated(build_dataframe("200", "Persona B"))
    repository.update_tracking_fields("100", "KEVIN", "E", "")

    deleted = repository.delete_by_operador("kevin")
    dataframe = repository.to_dataframe()

    assert deleted == 1
    assert list(dataframe["GUIA"]) == ["200"]


def test_delete_by_estado(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))
    repository.save_consolidated(build_dataframe("200", "Persona B"))
    repository.update_tracking_fields("100", "Operador 1", "Entregado", "")

    deleted = repository.delete_by_estado("Entregado")
    dataframe = repository.to_dataframe()

    assert deleted == 1
    assert list(dataframe["GUIA"]) == ["200"]


def test_operadores_crud(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.crear_operador("kevin", "hash1", "KEVIN")
    assert repository.obtener_operador("kevin") == {
        "usuario": "kevin",
        "password_hash": "hash1",
        "nombre": "KEVIN",
        "rol": "operador",
    }

    repository.crear_operador("kevin", "hash2", "KEVIN ACTUALIZADO")
    assert repository.obtener_operador("kevin")["nombre"] == "KEVIN ACTUALIZADO"
    assert repository.obtener_operador("kevin")["password_hash"] == "hash2"

    repository.crear_operador("ana", "hash3", "ANA")
    assert [item["usuario"] for item in repository.listar_operadores()] == ["ana", "kevin"]

    assert repository.contar_admins() == 0
    repository.crear_operador("jefe", "hash4", "JEFE", rol="admin")
    assert repository.obtener_operador("jefe")["rol"] == "admin"
    assert repository.contar_admins() == 1

    assert repository.eliminar_operador("ana") == 1
    assert repository.obtener_operador("ana") is None


def test_asignar_salida_y_registrar_novedad(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))
    repository.save_consolidated(build_dataframe("200", "Persona B"))

    asignadas = repository.asignar_salida(["100", "200"], "KEVIN", "R")
    dataframe = repository.to_dataframe()

    assert asignadas == 2
    assert list(dataframe["OPERADOR"]) == ["KEVIN", "KEVIN"]
    assert list(dataframe["ESTADO"]) == ["R", "R"]

    fecha = "2026-06-09"
    actualizadas = repository.registrar_novedad(["100"], "KEVIN", fecha, "R", "RO")
    dataframe = repository.to_dataframe()

    assert actualizadas == 1
    assert dataframe.loc[dataframe["GUIA"] == "100", "ESTADO"].iloc[0] == "RO"
    assert dataframe.loc[dataframe["GUIA"] == "200", "ESTADO"].iloc[0] == "R"


def test_cerrar_dia_operador_y_guardar_cierre(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))
    repository.save_consolidated(build_dataframe("200", "Persona B"))
    repository.asignar_salida(["100", "200"], "KEVIN", "R")

    fecha = "2026-06-09"
    convertidas = repository.cerrar_dia_operador("KEVIN", fecha, "R", "E")
    dataframe = repository.to_dataframe()

    assert convertidas == 2
    assert list(dataframe["ESTADO"]) == ["E", "E"]

    guias = repository.guias_de_operador("KEVIN", fecha)
    assert len(guias) == 2

    repository.guardar_cierre(
        fecha=fecha,
        operador="KEVIN",
        gestionadas=2,
        ro=0,
        n=0,
        d=0,
        e=2,
        recaudado=0,
        bancos=0,
        nequi=0,
        envia=0,
        efectivo=0,
    )
    cierre = repository.obtener_cierre(fecha, "KEVIN")
    assert cierre["gestionadas"] == 2
    assert cierre["e"] == 2


def test_obtener_guia(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))

    encontrada = repository.obtener_guia("100")
    assert encontrada is not None
    assert encontrada["guia"] == "100"

    assert repository.obtener_guia("999") is None
