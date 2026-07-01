from datetime import date
from gestor_guias.excel_processor import hoy_colombia
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


def test_import_deja_guias_nuevas_en_planillada_con_estado_vacio(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))
    repository.update_tracking_fields("100", "KEVIN", "E", "")
    repository.save_consolidated(build_dataframe("200", "Persona B"))

    dataframe = repository.to_dataframe().set_index("GUIA")

    # Una guia nueva (sin seguimiento previo) queda "en planilla" en vez de en blanco.
    assert dataframe.loc["200", "OPERADOR"] == "PLANILLADA"
    assert dataframe.loc["200", "ESTADO"] == ""
    # Las guias con seguimiento existente no se tocan.
    assert dataframe.loc["100", "OPERADOR"] == "KEVIN"
    assert dataframe.loc["100", "ESTADO"] == "E"


def test_import_deja_guias_de_bodega_con_estado_vacio(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    dataframe_bodega = build_dataframe("100", "Persona A")
    dataframe_bodega.loc[0, "OPERADOR"] = "BODEGA"
    dataframe_bodega.loc[0, "ESTADO"] = "N"
    repository.save_consolidated(dataframe_bodega)

    dataframe = repository.to_dataframe().set_index("GUIA")

    assert dataframe.loc["100", "OPERADOR"] == "BODEGA"
    assert dataframe.loc["100", "ESTADO"] == ""


def test_import_no_pisa_operador_de_guia_ya_existente_al_reimportar(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))
    repository.update_tracking_fields("100", "KEVIN", "R", "")
    # Reimportar la misma planilla (ej. el usuario vuelve a subir el archivo)
    # no debe pisar el operador/estado ya asignado con "PLANILLADA".
    repository.save_consolidated(build_dataframe("100", "Persona A"))

    dataframe = repository.to_dataframe().set_index("GUIA")

    assert dataframe.loc["100", "OPERADOR"] == "KEVIN"
    assert dataframe.loc["100", "ESTADO"] == "R"


def test_update_guide_details_permite_editar_fecha_y_entrega(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")
    repository.save_consolidated(build_dataframe("100", "Persona A"))

    repository.update_guide_details(
        guia="100",
        planilla="1",
        destinatario="Persona A",
        direccion="",
        municipio="SAN GIL",
        valor="$ -",
        operador="KEVIN",
        estado="E",
        causal="",
        fecha="2026-06-01",
        entrega="2026-06-03",
    )

    registro = repository.obtener_guia("100")
    assert registro["fecha"] == "2026-06-01"
    assert registro["ingreso"] == "2026-06-03"

    # Si no se envia fecha/entrega, se conserva lo que ya tenia la guia.
    repository.update_guide_details(
        guia="100",
        planilla="1",
        destinatario="Persona A",
        direccion="",
        municipio="SAN GIL",
        valor="$ -",
        operador="KEVIN",
        estado="E",
        causal="",
    )
    registro = repository.obtener_guia("100")
    assert registro["fecha"] == "2026-06-01"
    assert registro["ingreso"] == "2026-06-03"


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
        "licencia_vencimiento": "",
        "soat_vencimiento": "",
        "tecnomecanica_vencimiento": "",
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

    asignadas, creadas_sin_planilla = repository.asignar_salida(["100", "200", "999"], "KEVIN", "R")
    dataframe = repository.to_dataframe()

    assert asignadas == 3
    assert creadas_sin_planilla == ["999"]
    assert list(dataframe["OPERADOR"]) == ["KEVIN", "KEVIN", "KEVIN"]
    assert list(dataframe["ESTADO"]) == ["R", "R", "R"]
    assert dataframe.loc[dataframe["GUIA"] == "999", "PLANILLA"].iloc[0] == "Sin planilla"

    fecha = hoy_colombia().isoformat()
    actualizadas = repository.registrar_novedad(["100"], "KEVIN", fecha, "RO")
    dataframe = repository.to_dataframe()

    assert actualizadas == 1
    assert dataframe.loc[dataframe["GUIA"] == "100", "ESTADO"].iloc[0] == "RO"
    assert dataframe.loc[dataframe["GUIA"] == "200", "ESTADO"].iloc[0] == "R"


def test_asignar_salida_actualiza_fecha_de_ingreso_al_dia_actual(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))
    repository.asignar_salida(["100"], "KEVIN", "R")

    dataframe = repository.to_dataframe()

    assert dataframe.loc[dataframe["GUIA"] == "100", "F_INGRESO"].iloc[0] == hoy_colombia().isoformat()


def test_cerrar_dia_operador_y_guardar_cierre(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))
    repository.save_consolidated(build_dataframe("200", "Persona B"))
    repository.asignar_salida(["100", "200"], "KEVIN", "R")

    fecha = hoy_colombia().isoformat()
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


def test_revertir_cierre_operador_devuelve_guias_a_estado_r(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))
    repository.save_consolidated(build_dataframe("200", "Persona B"))
    repository.asignar_salida(["100", "200"], "KEVIN", "R")

    fecha = hoy_colombia().isoformat()
    repository.cerrar_dia_operador("KEVIN", fecha, "R", "E")
    repository.guardar_cierre(
        fecha=fecha, operador="KEVIN", gestionadas=2, ro=0, n=0, d=0, e=2,
        recaudado=0, bancos=0, nequi=0, envia=0, efectivo=0,
    )

    guias_revertidas = repository.revertir_cierre_operador("KEVIN", fecha)
    cierre_eliminado = repository.eliminar_cierre(fecha, "KEVIN")

    assert guias_revertidas == 2
    assert cierre_eliminado is True
    assert repository.obtener_cierre(fecha, "KEVIN") is None
    dataframe = repository.to_dataframe()
    assert list(dataframe["ESTADO"]) == ["R", "R"]


def test_guardar_cierre_persiste_denominaciones_contadas(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.guardar_cierre(
        fecha="2026-06-10", operador="KEVIN", gestionadas=1, ro=0, n=0, d=0, e=1,
        recaudado=10_000, bancos=0, nequi=0, envia=0, efectivo=10_000,
        denominaciones={50_000: 1, 10_000: 2},
    )

    cierre = repository.obtener_cierre("2026-06-10", "KEVIN")
    assert cierre["denominaciones"] == {50_000: 1, 10_000: 2}


def test_sumar_gastos_adelantos_mes(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.guardar_cierre(
        fecha="2026-06-05", operador="KEVIN", gestionadas=1, ro=0, n=0, d=0, e=1,
        recaudado=10_000, bancos=0, nequi=0, envia=0, efectivo=10_000,
        gastos=2_000, adelanto_salario=5_000,
    )
    repository.guardar_cierre(
        fecha="2026-06-15", operador="KEVIN", gestionadas=1, ro=0, n=0, d=0, e=1,
        recaudado=20_000, bancos=0, nequi=0, envia=0, efectivo=20_000,
        gastos=1_000, adelanto_salario=0,
    )
    repository.guardar_cierre(
        fecha="2026-07-01", operador="KEVIN", gestionadas=1, ro=0, n=0, d=0, e=1,
        recaudado=30_000, bancos=0, nequi=0, envia=0, efectivo=30_000,
        gastos=9_000, adelanto_salario=9_000,
    )

    resultado = repository.sumar_gastos_adelantos_mes(2026, 6)

    assert resultado == {"KEVIN": {"gastos": 3_000, "adelanto_salario": 5_000}}


def test_obtener_guia(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "Persona A"))

    encontrada = repository.obtener_guia("100")
    assert encontrada is not None
    assert encontrada["guia"] == "100"

    assert repository.obtener_guia("999") is None
