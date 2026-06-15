from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl.styles import Font, PatternFill
import pandas as pd


MONTHS_ES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


def output_filename(target_date: date) -> str:
    return f"{target_date.day:02d} {MONTHS_ES[target_date.month]}.xlsx"


def export_dataframe(dataframe: pd.DataFrame, output_dir: Path, target_date: date) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_filename(target_date)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False, sheet_name="Hoja1")
        worksheet = writer.sheets["Hoja1"]
        apply_master_format(worksheet)

    return output_path


def export_movements_copy(dataframe: pd.DataFrame, output_dir: Path, target_date: date) -> Path | None:
    if dataframe.empty:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"movimientos otros estado {output_filename(target_date)}"

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        dataframe.to_excel(writer, index=False, sheet_name="Movimientos")
        worksheet = writer.sheets["Movimientos"]
        apply_master_format(worksheet)

    return output_path


def apply_master_format(worksheet) -> None:
    header_fill = PatternFill(fill_type="solid", fgColor="4472C4")
    data_fill = PatternFill(fill_type="solid", fgColor="D9E1F2")
    header_font = Font(bold=True)

    widths = {
        "A": 13,
        "B": 13,
        "C": 13,
        "D": 13,
        "E": 18,
        "F": 35,
        "G": 13,
        "H": 13,
        "I": 13,
        "J": 13,
        "K": 13,
        "L": 20,
        "M": 13,
        "N": 35,
    }

    for column, width in widths.items():
        worksheet.column_dimensions[column].width = width

    for cell in worksheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = cell.alignment.copy(horizontal="left")

    for row in worksheet.iter_rows(min_row=2, max_row=worksheet.max_row, max_col=worksheet.max_column):
        for cell in row:
            cell.fill = data_fill
            cell.alignment = cell.alignment.copy(horizontal="left")
