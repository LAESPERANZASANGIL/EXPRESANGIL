from datetime import date
from pathlib import Path

import pandas as pd

from gestor_guias.recaudo import generate_recaudo_report
from gestor_guias.relacion_ce_rr import generate_relacion_ce_rr_report
from gestor_guias.repository import GuiaRepository
from gestor_guias.reports import generate_operator_report_pdf


def build_dataframe(guia: str, operador: str, estado: str, valor: str, servicio: str = "") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "PLANILLA": "1",
                "SERVICIO": servicio,
                "GUIA": guia,
                "UNID": "1",
                "TIPO DE SERVICIO": "PT",
                "DESTINATARIO": "Persona",
                "MUNICIPIO": "SAN GIL",
                "VALOR": valor,
                "OPERADOR": operador,
                "ESTADO": estado,
                "CAUSAL": "",
                "F_INGRESO": "2026-06-10 00:00:00",
                "F_ENTREGA": "",
            }
        ]
    )


def test_generate_operator_report_pdf(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "", "", "10000"))
    repository.update_tracking_fields("100", "OMAR", "E", "")

    repository.save_consolidated(build_dataframe("200", "", "", "20000"))
    repository.update_tracking_fields("200", "OMAR", "R", "")

    output_path = generate_operator_report_pdf(repository, tmp_path / "output", date(2026, 6, 10))

    assert output_path.exists()
    assert output_path.suffix == ".pdf"
    assert output_path.stat().st_size > 0


def test_generate_operator_report_pdf_no_data(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    output_path = generate_operator_report_pdf(repository, tmp_path / "output", date(2026, 6, 10))

    assert output_path.exists()


def test_generate_recaudo_report(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "", "", "10000"))
    repository.update_tracking_fields("100", "OMAR", "E", "")

    repository.save_consolidated(build_dataframe("200", "", "", "20000"))
    repository.update_tracking_fields("200", "OMAR", "R", "")

    output_path = generate_recaudo_report(repository, tmp_path / "output", date(2026, 6, 10))

    assert output_path.exists()
    assert output_path.suffix == ".xlsx"


def test_generate_recaudo_report_no_data(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    output_path = generate_recaudo_report(repository, tmp_path / "output", date(2026, 6, 10))

    assert output_path.exists()


def test_generate_relacion_ce_rr_report(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "", "", "15000", "RR"))
    repository.update_tracking_fields("100", "JOHAN ORTIZ", "E", "")

    repository.save_consolidated(build_dataframe("200", "", "", "19900", "CE"))
    repository.update_tracking_fields("200", "JOHAN ORTIZ", "E", "")

    repository.save_consolidated(build_dataframe("300", "", "", "20000", "PT"))
    repository.update_tracking_fields("300", "JOHAN ORTIZ", "E", "")

    repository.save_consolidated(build_dataframe("400", "", "", "30000", "RR"))
    repository.update_tracking_fields("400", "JOHAN ORTIZ", "R", "")

    output_path = generate_relacion_ce_rr_report(repository, tmp_path / "output", date(2026, 6, 10))

    assert output_path.exists()
    assert output_path.suffix == ".pdf"
    assert output_path.stat().st_size > 0


def test_generate_relacion_ce_rr_report_no_data(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    output_path = generate_relacion_ce_rr_report(repository, tmp_path / "output", date(2026, 6, 10))

    assert output_path.exists()
