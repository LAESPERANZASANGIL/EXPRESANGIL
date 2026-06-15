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
                "FECHA": "2026-06-09 00:00:00",
                "INGRESO": "",
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
