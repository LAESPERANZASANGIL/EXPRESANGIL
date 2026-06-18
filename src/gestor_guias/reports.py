from __future__ import annotations

from datetime import date
from pathlib import Path
import re

from openpyxl.styles import Alignment, Font, PatternFill
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .exporter import MONTHS_ES
from .repository import GuiaRepository


DETAIL_COLUMNS = [
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

# Estado que indica que la guia fue entregada y su valor recaudado.
ESTADO_RECAUDO = "E"


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
    return build_breakdown(dataframe, "OPERADOR")


def build_breakdown(dataframe: pd.DataFrame, column: str) -> pd.DataFrame:
    return (
        dataframe.groupby(column, as_index=False)
        .agg(
            GUIAS=("GUIA", "count"),
            UNIDADES=("UNID_NUMERICA", "sum"),
            VALOR=("VALOR_NUMERICO", "sum"),
        )
        .sort_values("GUIAS", ascending=False)
    )


def filter_by_date(dataframe: pd.DataFrame, target_date: date) -> pd.DataFrame:
    if "F_INGRESO" not in dataframe.columns:
        return dataframe.iloc[0:0]

    prefix = target_date.isoformat()
    return dataframe[dataframe["F_INGRESO"].astype(str).str.startswith(prefix)]


def generate_operator_report(
    repository: GuiaRepository, output_dir: Path, target_date: date | None = None
) -> Path:
    dataframe = normalize_dataframe(repository.to_dataframe())
    if target_date is not None:
        dataframe = filter_by_date(dataframe, target_date)

    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f" {target_date.day:02d} {MONTHS_ES[target_date.month]}" if target_date else ""
    output_path = output_dir / f"informe por operador{suffix}.xlsx"

    summary = build_breakdown(dataframe, "OPERADOR")

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary.to_excel(writer, index=False, sheet_name="POR OPERADOR")
        for sheet_name in writer.sheets:
            apply_report_format(writer.sheets[sheet_name])

    return output_path


# Meta diaria de guias entregadas por operador para calcular la efectividad.
META_DIARIA_GUIAS = 52


def format_currency_co(value: int) -> str:
    return f"$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def efectividad_color(porcentaje: float) -> colors.Color:
    if porcentaje >= 100:
        return colors.HexColor("#C6E0B4")
    if porcentaje >= 70:
        return colors.HexColor("#FFE699")
    return colors.HexColor("#F8CBAD")


def generate_operator_report_pdf(repository: GuiaRepository, output_dir: Path, target_date: date) -> Path:
    dataframe = normalize_dataframe(repository.to_dataframe())
    daily = filter_by_date(dataframe, target_date)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"informe por operador {target_date.day:02d} {MONTHS_ES[target_date.month]}.pdf"

    fecha_label = f"{MONTHS_ES[target_date.month].upper()} {target_date.day} DE {target_date.year}"

    styles = getSampleStyleSheet()
    title_style = styles["Title"].clone("CardTitle")
    title_style.textColor = colors.white
    title_style.alignment = 1

    elements: list = []

    if daily.empty:
        operators: list[str] = []
    else:
        totals = daily.groupby("OPERADOR")["GUIA"].count()
        recaudo = (
            daily[daily["ESTADO"].str.upper() == ESTADO_RECAUDO]
            .groupby("OPERADOR")["VALOR_NUMERICO"]
            .sum()
        )
        entregadas = (
            daily[daily["ESTADO"].str.upper() == ESTADO_RECAUDO]
            .groupby("OPERADOR")["GUIA"]
            .count()
        )
        operators = sorted(totals.index, key=lambda operador: totals[operador], reverse=True)

    if not operators:
        elements.append(Paragraph("Sin registros para esta fecha", styles["Normal"]))
    else:
        for operador in operators:
            gestionadas = int(totals.get(operador, 0))
            entregadas_count = int(entregadas.get(operador, 0))
            devolucion_count = gestionadas - entregadas_count
            recaudado = int(recaudo.get(operador, 0))
            efectividad = (entregadas_count / META_DIARIA_GUIAS) * 100

            title_paragraph = Paragraph(
                f"INFORME POR OPERADOR<br/>{operador}<br/>{fecha_label}",
                title_style,
            )

            rows = [
                [title_paragraph, ""],
                ["GUIAS GESTIONADAS", gestionadas],
                [f"GUIAS ENTREGADAS ({ESTADO_RECAUDO})", entregadas_count],
                ["GUIAS EN DEVOLUCION", devolucion_count],
                [f"VALOR RECAUDADO ({ESTADO_RECAUDO})", format_currency_co(recaudado)],
                [f"EFECTIVIDAD DEL DIA (META {META_DIARIA_GUIAS})", f"{efectividad:.1f} %"],
            ]

            table = Table(rows, colWidths=[8 * cm, 6 * cm])
            table.setStyle(
                TableStyle(
                    [
                        ("SPAN", (0, 0), (-1, 0)),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")),
                        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                        ("TOPPADDING", (0, 0), (-1, 0), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                        ("FONTNAME", (0, 1), (-1, -1), "Helvetica-Bold"),
                        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                        ("BACKGROUND", (0, 4), (-1, 4), colors.HexColor("#FFFF00")),
                        ("BACKGROUND", (0, 5), (-1, 5), efectividad_color(efectividad)),
                        ("GRID", (0, 1), (-1, -1), 0.5, colors.grey),
                        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
                        ("TOPPADDING", (0, 1), (-1, -1), 6),
                    ]
                )
            )

            elements.append(table)
            elements.append(Spacer(1, 14))

    doc = SimpleDocTemplate(str(output_path), pagesize=letter, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    doc.build(elements)

    return output_path


def generate_daily_report(repository: GuiaRepository, output_dir: Path, target_date: date) -> Path:
    dataframe = normalize_dataframe(repository.to_dataframe())
    daily = filter_by_date(dataframe, target_date)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"informe del dia {target_date.day:02d} {MONTHS_ES[target_date.month]}.xlsx"

    by_estado = build_breakdown(daily, "ESTADO")
    by_municipio = build_breakdown(daily, "MUNICIPIO")
    by_operador = build_breakdown(daily, "OPERADOR")
    detail = daily[DETAIL_COLUMNS]

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        by_estado.to_excel(writer, index=False, sheet_name="POR ESTADO")
        by_municipio.to_excel(writer, index=False, sheet_name="POR MUNICIPIO")
        by_operador.to_excel(writer, index=False, sheet_name="POR OPERADOR")
        detail.to_excel(writer, index=False, sheet_name="DETALLE")

        for sheet_name in writer.sheets:
            apply_report_format(writer.sheets[sheet_name])

        resumen_sheet = writer.book.create_sheet("RESUMEN", 0)
        build_resumen_sheet(resumen_sheet, daily, target_date)

    return output_path


# Estilos del bloque RESUMEN del Informe Diario.
RESUMEN_DARK_FILL = PatternFill(fill_type="solid", fgColor="1F3864")
RESUMEN_TITLE_FONT = Font(bold=True, size=14, color="FFFFFF")
RESUMEN_HEADER_FONT = Font(bold=True, color="FFFFFF")
RESUMEN_LABEL_FONT = Font(bold=True)
RESUMEN_CURRENCY_FORMAT = '"$" #,##0.00'


def build_resumen_sheet(worksheet, daily: pd.DataFrame, target_date: date) -> None:
    fecha_label = f"{MONTHS_ES[target_date.month].upper()} {target_date.day} DE {target_date.year}"

    worksheet.merge_cells("A1:B1")
    title_cell = worksheet["A1"]
    title_cell.value = "INFORME DIARIO"
    title_cell.fill = RESUMEN_DARK_FILL
    title_cell.font = RESUMEN_TITLE_FONT
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    worksheet.row_dimensions[1].height = 22

    worksheet.merge_cells("A2:B2")
    fecha_cell = worksheet["A2"]
    fecha_cell.value = fecha_label
    fecha_cell.fill = RESUMEN_DARK_FILL
    fecha_cell.font = RESUMEN_HEADER_FONT
    fecha_cell.alignment = Alignment(horizontal="center", vertical="center")

    total_unidades = int(daily["UNID_NUMERICA"].sum()) if not daily.empty else 0
    total_valor = int(daily["VALOR_NUMERICO"].sum()) if not daily.empty else 0

    row = 3
    for label, value, is_currency in (
        ("TOTAL GUIAS", len(daily), False),
        ("TOTAL UNIDADES", total_unidades, False),
        ("TOTAL VALOR", total_valor, True),
    ):
        label_cell = worksheet.cell(row=row, column=1, value=label)
        label_cell.font = RESUMEN_LABEL_FONT
        value_cell = worksheet.cell(row=row, column=2, value=value)
        value_cell.alignment = Alignment(horizontal="right")
        if is_currency:
            value_cell.number_format = RESUMEN_CURRENCY_FORMAT
        row += 1

    row += 1
    row = _write_resumen_breakdown(worksheet, row, "GUIAS POR ESTADO", daily, "ESTADO")
    row += 1
    row = _write_resumen_breakdown(worksheet, row, "GUIAS POR MUNICIPIO", daily, "MUNICIPIO")

    row += 1
    if daily.empty:
        recaudado = 0
    else:
        recaudado = int(
            daily[daily["ESTADO"].str.upper() == ESTADO_RECAUDO]["VALOR_NUMERICO"].sum()
        )

    label_cell = worksheet.cell(row=row, column=1, value=f"VALOR RECAUDADO ({ESTADO_RECAUDO}) $")
    label_cell.fill = RESUMEN_DARK_FILL
    label_cell.font = RESUMEN_HEADER_FONT
    label_cell.alignment = Alignment(horizontal="left", vertical="center")

    value_cell = worksheet.cell(row=row, column=2, value=recaudado)
    value_cell.fill = RESUMEN_DARK_FILL
    value_cell.font = RESUMEN_HEADER_FONT
    value_cell.alignment = Alignment(horizontal="right", vertical="center")
    value_cell.number_format = RESUMEN_CURRENCY_FORMAT

    worksheet.column_dimensions["A"].width = 26
    worksheet.column_dimensions["B"].width = 18


def _write_resumen_breakdown(worksheet, row: int, title: str, daily: pd.DataFrame, column: str) -> int:
    worksheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
    title_cell = worksheet.cell(row=row, column=1, value=title)
    title_cell.fill = RESUMEN_DARK_FILL
    title_cell.font = RESUMEN_HEADER_FONT
    title_cell.alignment = Alignment(horizontal="left", vertical="center")
    row += 1

    if daily.empty:
        return row

    for key, cantidad in daily.groupby(column).size().sort_values(ascending=False).items():
        worksheet.cell(row=row, column=1, value=key)
        value_cell = worksheet.cell(row=row, column=2, value=int(cantidad))
        value_cell.alignment = Alignment(horizontal="right")
        row += 1

    return row


def generate_estado_report(
    repository: GuiaRepository,
    output_dir: Path,
    target_date: date,
    estado: str,
    titulo: str,
    nombre_base: str,
) -> Path:
    """Genera un informe de toda la oficina con las guias de un estado en la fecha."""
    dataframe = normalize_dataframe(repository.to_dataframe())
    daily = filter_by_date(dataframe, target_date)
    seleccion = daily[daily["ESTADO"].str.upper() == estado.strip().upper()]

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{nombre_base} {target_date.day:02d} {MONTHS_ES[target_date.month]}.xlsx"

    by_operador = build_breakdown(seleccion, "OPERADOR")
    by_municipio = build_breakdown(seleccion, "MUNICIPIO")
    detail = seleccion[DETAIL_COLUMNS]

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        by_operador.to_excel(writer, index=False, sheet_name="POR OPERADOR")
        by_municipio.to_excel(writer, index=False, sheet_name="POR MUNICIPIO")
        detail.to_excel(writer, index=False, sheet_name="DETALLE")

        for sheet_name in writer.sheets:
            apply_report_format(writer.sheets[sheet_name])

        resumen_sheet = writer.book.create_sheet("RESUMEN", 0)
        build_estado_resumen_sheet(resumen_sheet, seleccion, target_date, titulo)

    return output_path


def build_estado_resumen_sheet(worksheet, seleccion: pd.DataFrame, target_date: date, titulo: str) -> None:
    fecha_label = f"{MONTHS_ES[target_date.month].upper()} {target_date.day} DE {target_date.year}"

    worksheet.merge_cells("A1:B1")
    title_cell = worksheet["A1"]
    title_cell.value = titulo
    title_cell.fill = RESUMEN_DARK_FILL
    title_cell.font = RESUMEN_TITLE_FONT
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    worksheet.row_dimensions[1].height = 22

    worksheet.merge_cells("A2:B2")
    fecha_cell = worksheet["A2"]
    fecha_cell.value = fecha_label
    fecha_cell.fill = RESUMEN_DARK_FILL
    fecha_cell.font = RESUMEN_HEADER_FONT
    fecha_cell.alignment = Alignment(horizontal="center", vertical="center")

    total_unidades = int(seleccion["UNID_NUMERICA"].sum()) if not seleccion.empty else 0
    total_valor = int(seleccion["VALOR_NUMERICO"].sum()) if not seleccion.empty else 0

    row = 3
    for label, value, is_currency in (
        ("TOTAL GUIAS", len(seleccion), False),
        ("TOTAL UNIDADES", total_unidades, False),
        ("TOTAL VALOR", total_valor, True),
    ):
        label_cell = worksheet.cell(row=row, column=1, value=label)
        label_cell.font = RESUMEN_LABEL_FONT
        value_cell = worksheet.cell(row=row, column=2, value=value)
        value_cell.alignment = Alignment(horizontal="right")
        if is_currency:
            value_cell.number_format = RESUMEN_CURRENCY_FORMAT
        row += 1

    row += 1
    _write_resumen_breakdown(worksheet, row, "GUIAS POR OPERADOR", seleccion, "OPERADOR")

    worksheet.column_dimensions["A"].width = 26
    worksheet.column_dimensions["B"].width = 18


def generate_devoluciones_report(repository: GuiaRepository, output_dir: Path, target_date: date) -> Path:
    return generate_estado_report(
        repository, output_dir, target_date, "D", "DEVOLUCIONES", "devoluciones"
    )


def generate_entregadas_report(repository: GuiaRepository, output_dir: Path, target_date: date) -> Path:
    return generate_estado_report(
        repository, output_dir, target_date, ESTADO_RECAUDO, "ENTREGADAS DEL DIA", "entregadas del dia"
    )


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
