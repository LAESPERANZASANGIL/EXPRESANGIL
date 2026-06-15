from __future__ import annotations

from datetime import date, datetime, time
from dataclasses import dataclass
from pathlib import Path
import re

import pandas as pd


REPORT_COLUMNS = {
    "SERVICIO": 2,
    "GUIA": 6,
    "TIPO DE SERVICIO": 13,
    "DESTINATARIO": 23,
    "DIRECCION": 30,
    "MUNICIPIO": 39,
    "UNID": 48,
    "VALOR": 58,
}

REEXPEDIDORES_REPORT_COLUMNS = {
    "SERVICIO": 2,
    "GUIA": 5,
    "TIPO DE SERVICIO": 11,
    "DESTINATARIO": 20,
    "DIRECCION": 27,
    "MUNICIPIO": 35,
    "UNID": 47,
    "VALOR": 57,
}

COLVANES_REPORT_TITLES = {
    "PLANILLA DE REPARTO PARA CONTRATISTAS": REPORT_COLUMNS,
    "PLANILLA DE REPARTO PARA REEXPEDIDORES": REEXPEDIDORES_REPORT_COLUMNS,
}


@dataclass(frozen=True)
class ConsolidationResult:
    active: pd.DataFrame
    movements_copy: pd.DataFrame


def normalize_column_name(value: object) -> str:
    return str(value).strip().upper().replace("\n", " ")


def read_excel_file(path: Path, required_columns: list[str]) -> pd.DataFrame:
    dataframe = pd.read_excel(path, dtype=str)
    dataframe.columns = [normalize_column_name(column) for column in dataframe.columns]

    if "ESTADO MOVIMIENTO" not in dataframe.columns and "ESTADO" in dataframe.columns:
        dataframe["ESTADO MOVIMIENTO"] = dataframe["ESTADO"]

    if "ESTADO" not in dataframe.columns and "ESTADO MOVIMIENTO" in dataframe.columns:
        dataframe["ESTADO"] = ""

    missing = [column for column in required_columns if column not in dataframe.columns]
    if not missing:
        optional_columns = ["ESTADO MOVIMIENTO"] if "ESTADO MOVIMIENTO" in dataframe.columns else []
        return dataframe[required_columns + optional_columns].copy()

    raw_dataframe = pd.read_excel(path, header=None, dtype=object)
    report_columns = detect_report_columns(raw_dataframe)
    if report_columns is not None:
        return read_colvanes_report(raw_dataframe, required_columns, report_columns)

    raise ValueError(f"El archivo {path.name} no contiene estas columnas: {', '.join(missing)}")


def consolidate_excels(paths: list[Path], required_columns: list[str]) -> pd.DataFrame:
    return consolidate_excels_with_movements(paths, required_columns).active


def consolidate_excels_with_movements(paths: list[Path], required_columns: list[str]) -> ConsolidationResult:
    if not paths:
        empty = pd.DataFrame(columns=required_columns)
        return ConsolidationResult(active=empty, movements_copy=empty)

    frames = [read_excel_file(path, required_columns) for path in paths]
    consolidated = pd.concat(frames, ignore_index=True)

    for column in required_columns:
        consolidated[column] = consolidated[column].fillna("").astype(str).str.strip()

    movement_status = get_movement_status(consolidated)
    active_mask = movement_status.eq("N") | movement_status.eq("")
    active = consolidated[active_mask].copy()
    movements_copy = consolidated[~active_mask].copy()

    for column in ("OPERADOR", "ESTADO", "CAUSAL"):
        if column in active.columns:
            active[column] = ""

    active = active[active["GUIA"] != ""]
    active = active.drop_duplicates(subset=["GUIA"], keep="first")
    movements_copy = movements_copy[movements_copy["GUIA"] != ""]
    movements_copy = movements_copy.drop_duplicates(subset=["GUIA"], keep="first")
    return ConsolidationResult(
        active=active[required_columns].reset_index(drop=True),
        movements_copy=movements_copy.reset_index(drop=True),
    )


def get_movement_status(dataframe: pd.DataFrame) -> pd.Series:
    if "ESTADO MOVIMIENTO" in dataframe.columns:
        return dataframe["ESTADO MOVIMIENTO"].fillna("").astype(str).str.strip().str.upper()

    if "ESTADO" in dataframe.columns and dataframe["ESTADO"].fillna("").astype(str).str.strip().ne("").any():
        return dataframe["ESTADO"].fillna("").astype(str).str.strip().str.upper()

    return pd.Series(["N"] * len(dataframe), index=dataframe.index)


def detect_report_columns(dataframe: pd.DataFrame) -> dict[str, int] | None:
    values = dataframe.fillna("").astype(str).to_numpy().ravel()
    upper_values = {value.strip().upper() for value in values}
    for title, columns in COLVANES_REPORT_TITLES.items():
        if title in upper_values:
            return columns
    return None


def read_colvanes_report(
    dataframe: pd.DataFrame, required_columns: list[str], report_columns: dict[str, int]
) -> pd.DataFrame:
    planilla = clean_value(find_value_after_label(dataframe, "Planilla Reparto"))
    tipo_servicio = clean_value(find_value_after_label(dataframe, "Tipo Embalaje"))
    fecha = format_date(find_value_after_label(dataframe, "Fecha Planilla"))
    ingreso = format_time(find_second_value_after_label(dataframe, "Fecha y Hora"))

    records = []
    for _, row in dataframe.iloc[15:].iterrows():
        raw_guia = clean_value(get_position(row, report_columns["GUIA"]))
        if not is_guide_number(raw_guia):
            continue

        records.append(
            {
                "PLANILLA": planilla,
                "SERVICIO": clean_value(get_position(row, report_columns["SERVICIO"])),
                "GUIA": normalize_guide(raw_guia),
                "UNID": clean_value(get_position(row, report_columns["UNID"])),
                "TIPO DE SERVICIO": clean_value(get_position(row, report_columns["TIPO DE SERVICIO"])),
                "DESTINATARIO": clean_value(get_position(row, report_columns["DESTINATARIO"])),
                "DIRECCION": clean_value(get_position(row, report_columns["DIRECCION"])),
                "MUNICIPIO": clean_value(get_position(row, report_columns["MUNICIPIO"])),
                "VALOR": normalize_value(get_position(row, report_columns["VALOR"])),
                "OPERADOR": "",
                "ESTADO": "",
                "CAUSAL": "",
                "FECHA": format_consolidated_date(fecha),
                "INGRESO": "",
                "ESTADO MOVIMIENTO": "N",
            }
        )

    return pd.DataFrame(records, columns=required_columns + ["ESTADO MOVIMIENTO"])


def find_value_after_label(dataframe: pd.DataFrame, label: str) -> object:
    row_index, column_index = find_label_position(dataframe, label)
    row = dataframe.iloc[row_index]
    for value in row.iloc[column_index + 1 :]:
        if has_value(value):
            return value
    return ""


def find_second_value_after_label(dataframe: pd.DataFrame, label: str) -> object:
    row_index, column_index = find_label_position(dataframe, label)
    row = dataframe.iloc[row_index]
    found = []
    for value in row.iloc[column_index + 1 :]:
        if has_value(value):
            found.append(value)
        if len(found) == 2:
            return found[1]
    return found[0] if found else ""


def find_label_position(dataframe: pd.DataFrame, label: str) -> tuple[int, int]:
    normalized_label = label.strip().upper()
    for row_index in range(len(dataframe)):
        for column_index, value in enumerate(dataframe.iloc[row_index]):
            if clean_value(value).upper() == normalized_label:
                return row_index, column_index
    return 0, -1


def get_position(row: pd.Series, index: int) -> object:
    if index >= len(row):
        return ""
    return row.iloc[index]


def has_value(value: object) -> bool:
    return clean_value(value) != ""


def clean_value(value: object) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def format_date(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return clean_value(value)


def format_time(value: object) -> str:
    if isinstance(value, datetime):
        return value.time().strftime("%H:%M:%S")
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    return clean_value(value)


def is_guide_number(value: str) -> bool:
    return bool(re.fullmatch(r"\d{2}-\d-\d+", value))


def normalize_guide(value: str) -> str:
    guide = value.replace("-", "").strip()
    return guide[1:] if guide.startswith("0") else guide


def normalize_value(value: object) -> str:
    text = clean_value(value)
    if text in {"", "0", "0.0"}:
        return "$ -"
    return text


def format_consolidated_date(value: str) -> str:
    if not value:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return f"{value} 00:00:00"
    return value
