from __future__ import annotations

from datetime import date
from pathlib import Path
import re

from openpyxl.styles import Font, PatternFill
import pandas as pd

from .exporter import MONTHS_ES


def generate_reports(source_file: Path, output_dir: Path, target_date: date) -> Path:
    detail = pd.read_excel(source_file, dtype=str).fillna("")
    dataframe = normalize_dataframe(detail)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"informes {target_date.day:02d} {MONTHS_ES[target_date.month]}.xlsx"

    general = build_general_summary(dataframe)
    by_operator = build_operator_summary(dataframe)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        general.to_excel(writer, index=False, sheet_name="GENERAL")
        by_operator.to_excel(writer, index=False, sheet_name="POR OPERADOR")
        detail.to_excel(writer, index=False, sheet_name="DETALLE")

        for sheet_name in writer.sheets:
            apply_report_format(writer.sheets[sheet_name])

    return output_path


def normalize_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    dataframe = dataframe.copy()
    for column in dataframe.columns:
        dataframe[column] = dataframe[column].fillna("").astype(str).str.strip()

    dataframe["OPERADOR"] = dataframe["OPERADOR"].replace("", "SIN OPERADOR")
    dataframe["ESTADO"] = dataframe["ESTADO"].replace("", "SIN ESTADO")
    dataframe["CAUSAL"] = dataframe["CAUSAL"].replace("", "SIN CAUSAL")
    dataframe["VALOR_NUMERICO"] = dataframe["VALOR"].apply(value_to_number)
    dataframe["UNID_NUMERICA"] = pd.to_numeric(dataframe["UNID"], errors="coerce").fillna(0).astype(int)
    return dataframe


def build_general_summary(dataframe: pd.DataFrame) -> pd.DataFrame:
    rows = [
        {"CONCEPTO": "TOTAL GUIAS", "VALOR": len(dataframe)},
        {"CONCEPTO": "TOTAL UNIDADES", "VALOR": int(dataframe["UNID_NUMERICA"].sum())},
        {"CONCEPTO": "TOTAL VALOR", "VALOR": int(dataframe["VALOR_NUMERICO"].sum())},
        {"CONCEPTO": "", "VALOR": ""},
        {"CONCEPTO": "GUIAS POR ESTADO", "VALOR": ""},
    ]

    for estado, cantidad in dataframe.groupby("ESTADO").size().sort_values(ascending=False).items():
        rows.append({"CONCEPTO": estado, "VALOR": int(cantidad)})

    rows.append({"CONCEPTO": "", "VALOR": ""})
    rows.append({"CONCEPTO": "GUIAS POR MUNICIPIO", "VALOR": ""})
    for municipio, cantidad in dataframe.groupby("MUNICIPIO").size().sort_values(ascending=False).items():
        rows.append({"CONCEPTO": municipio, "VALOR": int(cantidad)})

    return pd.DataFrame(rows)


def build_operator_summary(dataframe: pd.DataFrame) -> pd.DataFrame:
    summary = (
        dataframe.groupby("OPERADOR", as_index=False)
        .agg(
            GUIAS=("GUIA", "count"),
            UNIDADES=("UNID_NUMERICA", "sum"),
            VALOR=("VALOR_NUMERICO", "sum"),
        )
        .sort_values("GUIAS", ascending=False)
    )
    return summary


def value_to_number(value: object) -> int:
    text = str(value).strip()
    if not text or text == "$ -":
        return 0
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0


def apply_report_format(worksheet) -> None:
    header_fill = PatternFill(fill_type="solid", fgColor="4472C4")
    data_fill = PatternFill(fill_type="solid", fgColor="D9E1F2")
    header_font = Font(bold=True)

    for cell in worksheet[1]:
        cell.fill = header_fill
        cell.font = header_font

    for row in worksheet.iter_rows(min_row=2, max_row=worksheet.max_row, max_col=worksheet.max_column):
        for cell in row:
            cell.fill = data_fill

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions

    for column_cells in worksheet.columns:
        max_length = max(len(str(cell.value or "")) for cell in column_cells)
        worksheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 38)
