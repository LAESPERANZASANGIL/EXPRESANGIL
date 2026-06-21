from pathlib import Path

import pandas as pd

from gestor_guias.operadores import (
    cerrar_dia,
    documentos_vencidos,
    hash_password,
    parse_guides,
    registrar_novedades,
    registrar_salidas,
    verify_password,
)
from gestor_guias.repository import GuiaRepository


def build_dataframe(guia: str, valor: str, fecha: str = "2026-06-09 00:00:00") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "PLANILLA": "1",
                "SERVICIO": "",
                "GUIA": guia,
                "UNID": "1",
                "TIPO DE SERVICIO": "PT",
                "DESTINATARIO": "Persona",
                "MUNICIPIO": "SAN GIL",
                "VALOR": valor,
                "OPERADOR": "",
                "ESTADO": "",
                "CAUSAL": "",
                "F_INGRESO": fecha,
                "F_ENTREGA": "",
            }
        ]
    )


def test_hash_and_verify_password() -> None:
    stored = hash_password("clave123")

    assert verify_password("clave123", stored)
    assert not verify_password("otra-clave", stored)


def test_documentos_vencidos_detecta_fechas_pasadas() -> None:
    operador = {
        "licencia_vencimiento": "2000-01-01",
        "soat_vencimiento": "2999-01-01",
        "tecnomecanica_vencimiento": "",
    }

    assert documentos_vencidos(operador) == ["Licencia de conduccion"]


def test_documentos_vencidos_sin_fechas_no_bloquea() -> None:
    operador = {
        "licencia_vencimiento": "",
        "soat_vencimiento": "",
        "tecnomecanica_vencimiento": "",
    }

    assert documentos_vencidos(operador) == []


def test_parse_guides_extracts_long_numbers() -> None:
    texto = "100000, 100001\n100002 - texto 12"

    assert parse_guides(texto) == ["100000", "100001", "100002"]


def test_parse_guides_quita_cero_inicial_del_escaner() -> None:
    # El escaner entrega el numero con cero inicial, pero la base lo guarda sin el.
    assert parse_guides("064108678163\n14160044927") == ["64108678163", "14160044927"]


def test_registrar_salidas_acepta_guias_con_cero_inicial(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")
    repository.save_consolidated(build_dataframe("64108678163", "$ 10.000"))

    resultado = registrar_salidas(repository, "OMAR", "064108678163")

    assert resultado == {"recibidas": 1, "actualizadas": 1}
    dataframe = repository.to_dataframe()
    assert list(dataframe["OPERADOR"]) == ["OMAR"]


def test_registrar_salidas_marca_operador_y_estado(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")
    repository.save_consolidated(build_dataframe("100000", "$ 10.000"))
    repository.save_consolidated(build_dataframe("100001", "$ 20.000"))

    resultado = registrar_salidas(repository, "KEVIN", "100000\n100001\n100099")

    assert resultado == {"recibidas": 3, "actualizadas": 2}
    dataframe = repository.to_dataframe()
    assert list(dataframe["OPERADOR"]) == ["KEVIN", "KEVIN"]
    assert list(dataframe["ESTADO"]) == ["R", "R"]


def test_registrar_novedades_solo_afecta_guias_en_r(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")
    repository.save_consolidated(build_dataframe("100000", "$ 10.000"))
    repository.save_consolidated(build_dataframe("100001", "$ 20.000"))
    repository.save_consolidated(build_dataframe("100002", "$ 30.000"))
    registrar_salidas(repository, "KEVIN", "100000\n100001\n100002")

    resultado = registrar_novedades(
        repository,
        "KEVIN",
        "2026-06-09",
        ro_texto="100000",
        n_texto="100001",
        d_texto="",
    )

    assert resultado["ro"] == {"recibidas": 1, "actualizadas": 1}
    assert resultado["n"] == {"recibidas": 1, "actualizadas": 1}
    assert resultado["d"] == {"recibidas": 0, "actualizadas": 0, "errores": []}

    dataframe = repository.to_dataframe().set_index("GUIA")
    assert dataframe.loc["100000", "ESTADO"] == "RO"
    assert dataframe.loc["100001", "ESTADO"] == "N"
    assert dataframe.loc["100002", "ESTADO"] == "R"


def test_registrar_novedades_devolucion_guarda_causal(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")
    repository.save_consolidated(build_dataframe("100000", "$ 10.000"))
    repository.save_consolidated(build_dataframe("100001", "$ 20.000"))
    registrar_salidas(repository, "KEVIN", "100000\n100001")

    resultado = registrar_novedades(
        repository,
        "KEVIN",
        "2026-06-09",
        ro_texto="",
        n_texto="",
        d_texto="100000 10\nguia-sin-causal\n100001,25",
    )

    assert resultado["d"]["recibidas"] == 2
    assert resultado["d"]["actualizadas"] == 2
    assert resultado["d"]["errores"] == ["guia-sin-causal"]

    dataframe = repository.to_dataframe().set_index("GUIA")
    assert dataframe.loc["100000", "ESTADO"] == "D"
    assert dataframe.loc["100000", "CAUSAL"] == "10"
    assert dataframe.loc["100001", "ESTADO"] == "D"
    assert dataframe.loc["100001", "CAUSAL"] == "25"


def test_cerrar_dia_calcula_resumen_y_persiste(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")
    repository.save_consolidated(build_dataframe("100000", "$ 10.000"))
    repository.save_consolidated(build_dataframe("100001", "$ 20.000"))
    repository.save_consolidated(build_dataframe("100002", "$ 30.000"))
    registrar_salidas(repository, "KEVIN", "100000\n100001\n100002")
    registrar_novedades(repository, "KEVIN", "2026-06-09", ro_texto="100000", n_texto="", d_texto="")

    resumen = cerrar_dia(repository, "KEVIN", "2026-06-09", bancos=10_000, nequi=5_000, envia=0)

    assert resumen["gestionadas"] == 3
    assert resumen["ro"] == 1
    assert resumen["n"] == 0
    assert resumen["d"] == 0
    assert resumen["e"] == 2
    assert resumen["recaudado"] == 50_000
    assert resumen["efectivo"] == 35_000

    cierre = repository.obtener_cierre("2026-06-09", "KEVIN")
    assert cierre["recaudado"] == 50_000
    assert cierre["efectivo"] == 35_000
