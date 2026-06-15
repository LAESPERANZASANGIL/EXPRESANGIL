from pathlib import Path
from datetime import datetime, time

import pandas as pd
from openpyxl import Workbook

from gestor_guias.excel_processor import consolidate_excels, consolidate_excels_with_movements


REQUIRED_COLUMNS = [
    "PLANILLA",
    "SERVICIO",
    "GUIA",
    "UNID",
    "TIPO DE SERVICIO",
    "DESTINATARIO",
    "MUNICIPIO",
    "VALOR",
    "OPERADOR",
    "ESTADO",
    "CAUSAL",
    "FECHA",
    "INGRESO",
    "DIRECCION",
]


def test_consolidate_clears_tracking_fields_and_removes_duplicate_guides(tmp_path: Path) -> None:
    file_path = tmp_path / "planilla.xlsx"
    dataframe = pd.DataFrame(
        [
            {
                "PLANILLA": "P1",
                "SERVICIO": "S",
                "GUIA": "100",
                "UNID": "1",
                "TIPO DE SERVICIO": "NORMAL",
                "DESTINATARIO": "Persona A",
                "MUNICIPIO": "Bucaramanga",
                "VALOR": "10000",
                "OPERADOR": "Debe limpiarse",
                "ESTADO": "Debe limpiarse",
                "CAUSAL": "Debe limpiarse",
                "FECHA": "2026-06-09",
                "INGRESO": "08:00",
                "DIRECCION": "Calle 1 # 2-3",
                "ESTADO MOVIMIENTO": "N",
            },
            {
                "PLANILLA": "P2",
                "SERVICIO": "S",
                "GUIA": "100",
                "UNID": "1",
                "TIPO DE SERVICIO": "NORMAL",
                "DESTINATARIO": "Persona B",
                "MUNICIPIO": "Bucaramanga",
                "VALOR": "12000",
                "OPERADOR": "Debe limpiarse",
                "ESTADO": "Debe limpiarse",
                "CAUSAL": "Debe limpiarse",
                "FECHA": "2026-06-09",
                "INGRESO": "09:00",
                "DIRECCION": "Calle 4 # 5-6",
                "ESTADO MOVIMIENTO": "N",
            },
        ]
    )
    dataframe.to_excel(file_path, index=False)

    result = consolidate_excels([file_path], REQUIRED_COLUMNS)

    assert len(result) == 1
    assert result.loc[0, "GUIA"] == "100"
    assert result.loc[0, "OPERADOR"] == ""
    assert result.loc[0, "ESTADO"] == ""
    assert result.loc[0, "CAUSAL"] == ""


def test_consolidate_keeps_only_movement_status_n_and_copies_other_statuses(tmp_path: Path) -> None:
    file_path = tmp_path / "planilla_estados.xlsx"
    dataframe = pd.DataFrame(
        [
            {
                "PLANILLA": "P1",
                "SERVICIO": "",
                "GUIA": "100",
                "UNID": "1",
                "TIPO DE SERVICIO": "PT",
                "DESTINATARIO": "Persona A",
                "MUNICIPIO": "San Gil",
                "VALOR": "$ -",
                "OPERADOR": "",
                "ESTADO": "",
                "CAUSAL": "",
                "FECHA": "2026-06-09 00:00:00",
                "INGRESO": "",
                "DIRECCION": "Calle 1 # 2-3",
                "ESTADO MOVIMIENTO": "N",
            },
            {
                "PLANILLA": "P1",
                "SERVICIO": "",
                "GUIA": "200",
                "UNID": "1",
                "TIPO DE SERVICIO": "PT",
                "DESTINATARIO": "Persona B",
                "MUNICIPIO": "San Gil",
                "VALOR": "$ -",
                "OPERADOR": "",
                "ESTADO": "",
                "CAUSAL": "",
                "FECHA": "2026-06-09 00:00:00",
                "INGRESO": "",
                "DIRECCION": "Calle 4 # 5-6",
                "ESTADO MOVIMIENTO": "D",
            },
        ]
    )
    dataframe.to_excel(file_path, index=False)

    result = consolidate_excels_with_movements([file_path], REQUIRED_COLUMNS)

    assert list(result.active["GUIA"]) == ["100"]
    assert list(result.movements_copy["GUIA"]) == ["200"]
    assert list(result.movements_copy["ESTADO MOVIMIENTO"]) == ["D"]


def test_consolidate_colvanes_report_layout(tmp_path: Path) -> None:
    file_path = tmp_path / "reporte_colvanes.xlsx"
    workbook = Workbook()
    worksheet = workbook.active

    worksheet["V2"] = "PLANILLA DE REPARTO PARA CONTRATISTAS"
    worksheet["AO2"] = "Fecha y Hora"
    worksheet["AV2"] = datetime(2026, 6, 9)
    worksheet["BC2"] = time(7, 8)
    worksheet["S3"] = "Planilla Reparto"
    worksheet["U3"] = 979628
    worksheet["AB3"] = "Fecha Planilla"
    worksheet["AC3"] = datetime(2026, 6, 9)
    worksheet["B11"] = "Tipo Embalaje"
    worksheet["G11"] = "PAQUETES"

    worksheet["G18"] = "01-4-158816547"
    worksheet["N18"] = "DE "
    worksheet["X18"] = "SERGIO ANDRES CORZO"
    worksheet["AE18"] = "CALLE 10 # 5-20"
    worksheet["AN18"] = "SAN GIL"
    worksheet["AW18"] = 1
    worksheet["BG18"] = 0

    workbook.save(file_path)

    result = consolidate_excels([file_path], REQUIRED_COLUMNS)

    assert len(result) == 1
    assert result.loc[0, "PLANILLA"] == "979628"
    assert result.loc[0, "SERVICIO"] == ""
    assert result.loc[0, "GUIA"] == "14158816547"
    assert result.loc[0, "UNID"] == "1"
    assert result.loc[0, "TIPO DE SERVICIO"] == "DE"
    assert result.loc[0, "DESTINATARIO"] == "SERGIO ANDRES CORZO"
    assert result.loc[0, "DIRECCION"] == "CALLE 10 # 5-20"
    assert result.loc[0, "MUNICIPIO"] == "SAN GIL"
    assert result.loc[0, "VALOR"] == "$ -"
    assert result.loc[0, "FECHA"] == "2026-06-09 00:00:00"
    assert result.loc[0, "INGRESO"] == ""
