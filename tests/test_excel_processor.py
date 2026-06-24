from pathlib import Path
from datetime import datetime, time

import pandas as pd
from openpyxl import Workbook

from gestor_guias.excel_processor import (
    consolidate_excels,
    consolidate_excels_with_movements,
    format_pesos,
)


REQUIRED_COLUMNS = [
    "PLANILLA",
    "SERVICIO",
    "GUIA",
    "UNID",
    "TIPO DE SERVICIO",
    "DESTINATARIO",
    "DIRECCION",
    "MUNICIPIO",
    "VALOR",
    "OPERADOR",
    "ESTADO",
    "CAUSAL",
    "F_INGRESO",
    "F_ENTREGA",
]


def test_consolidate_marca_rr_cuando_hay_valor_y_servicio_vacio(tmp_path: Path) -> None:
    file_path = tmp_path / "planilla.xlsx"
    dataframe = pd.DataFrame(
        [
            {
                "PLANILLA": "P1",
                "SERVICIO": "",
                "GUIA": "100",
                "UNID": "1",
                "TIPO DE SERVICIO": "NORMAL",
                "DESTINATARIO": "Persona A",
                "MUNICIPIO": "Bucaramanga",
                "VALOR": "10000",
                "OPERADOR": "",
                "ESTADO": "",
                "CAUSAL": "",
                "F_INGRESO": "2026-06-09",
                "F_ENTREGA": "",
            },
            {
                "PLANILLA": "P1",
                "SERVICIO": "CE",
                "GUIA": "200",
                "UNID": "1",
                "TIPO DE SERVICIO": "NORMAL",
                "DESTINATARIO": "Persona B",
                "MUNICIPIO": "Bucaramanga",
                "VALOR": "20000",
                "OPERADOR": "",
                "ESTADO": "",
                "CAUSAL": "",
                "F_INGRESO": "2026-06-09",
                "F_ENTREGA": "",
            },
            {
                "PLANILLA": "P1",
                "SERVICIO": "",
                "GUIA": "300",
                "UNID": "1",
                "TIPO DE SERVICIO": "NORMAL",
                "DESTINATARIO": "Persona C",
                "MUNICIPIO": "Bucaramanga",
                "VALOR": "",
                "OPERADOR": "",
                "ESTADO": "",
                "CAUSAL": "",
                "F_INGRESO": "2026-06-09",
                "F_ENTREGA": "",
            },
        ]
    )
    dataframe.to_excel(file_path, index=False)

    result = consolidate_excels([file_path], REQUIRED_COLUMNS).set_index("GUIA")

    assert result.loc["100", "SERVICIO"] == "RR"
    assert result.loc["200", "SERVICIO"] == "CE"
    assert result.loc["300", "SERVICIO"] == ""


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
                "F_INGRESO": "2026-06-09",
                "F_ENTREGA": "08:00",
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
                "F_INGRESO": "2026-06-09",
                "F_ENTREGA": "09:00",
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
                "F_INGRESO": "2026-06-09 00:00:00",
                "F_ENTREGA": "",
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
                "F_INGRESO": "2026-06-09 00:00:00",
                "F_ENTREGA": "",
                "ESTADO MOVIMIENTO": "D",
            },
        ]
    )
    dataframe.to_excel(file_path, index=False)

    result = consolidate_excels_with_movements([file_path], REQUIRED_COLUMNS)

    assert list(result.active["GUIA"]) == ["100"]
    assert list(result.movements_copy["GUIA"]) == ["200"]
    assert list(result.movements_copy["ESTADO MOVIMIENTO"]) == ["D"]


def test_format_pesos() -> None:
    assert format_pesos("142900") == "$ 142.900"
    assert format_pesos("142900.0") == "$ 142.900"
    assert format_pesos("$ 142.900") == "$ 142.900"
    assert format_pesos("1500000") == "$ 1.500.000"
    assert format_pesos("0") == "$ -"
    assert format_pesos("") == "$ -"
    assert format_pesos("$ -") == "$ -"


def test_consolidate_initial_operations_format_preserves_tracking(tmp_path: Path) -> None:
    file_path = tmp_path / "formato_inicial.xlsx"
    dataframe = pd.DataFrame(
        [
            {
                "PLANILLA": "979628",
                "S": "RR",
                "GUIA": "014158816547",
                "UN": "1",
                "TI": "DE",
                "DESTINATARIO": "SERGIO ANDRES CORZO",
                "MUNICIPIO": "SAN GIL",
                "VALOR": "$ -",
                "OPERADOR": "OMAR",
                "EST": "D",
                "CAU": "31",
                "F_INGRESO": "11/06/2026",
            },
            {
                "PLANILLA": "978411",
                "S": "",
                "GUIA": "034057184716",
                "UN": "1",
                "TI": "MT",
                "DESTINATARIO": "TECNI MOTOS JOHN",
                "MUNICIPIO": "SAN GIL",
                "VALOR": "$ -",
                "OPERADOR": "MARGARITA",
                "EST": "E",
                "CAU": "",
                "F_INGRESO": "10/06/2026",
            },
        ]
    )
    dataframe.to_excel(file_path, index=False)

    result = consolidate_excels_with_movements([file_path], REQUIRED_COLUMNS)

    assert list(result.active["GUIA"]) == ["14158816547", "34057184716"]
    assert list(result.active["OPERADOR"]) == ["OMAR", "MARGARITA"]
    assert list(result.active["ESTADO"]) == ["D", "E"]
    assert list(result.active["CAUSAL"]) == ["31", ""]
    assert list(result.active["F_INGRESO"]) == ["2026-06-11 00:00:00", "2026-06-10 00:00:00"]
    assert list(result.active["F_ENTREGA"]) == ["", ""]
    assert result.movements_copy.empty


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
    worksheet["AE18"] = "CALLE 5 # 10-20"
    worksheet["AN18"] = "SAN GIL"
    worksheet["AW18"] = 1
    worksheet["BG18"] = 0

    workbook.save(file_path)

    result = consolidate_excels([file_path], REQUIRED_COLUMNS, import_date="2026-06-13")

    assert len(result) == 1
    assert result.loc[0, "PLANILLA"] == "979628"
    assert result.loc[0, "SERVICIO"] == ""
    assert result.loc[0, "GUIA"] == "14158816547"
    assert result.loc[0, "UNID"] == "1"
    assert result.loc[0, "TIPO DE SERVICIO"] == "DE"
    assert result.loc[0, "DESTINATARIO"] == "SERGIO ANDRES CORZO"
    assert result.loc[0, "DIRECCION"] == "CALLE 5 # 10-20"
    assert result.loc[0, "MUNICIPIO"] == "SAN GIL"
    assert result.loc[0, "VALOR"] == "$ -"
    # F_INGRESO es la fecha de importacion (no la "Fecha Planilla" del reporte).
    assert result.loc[0, "F_INGRESO"] == "2026-06-13 00:00:00"
    assert result.loc[0, "F_ENTREGA"] == ""
