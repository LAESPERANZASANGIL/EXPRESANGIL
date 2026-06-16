from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .exporter import MONTHS_ES
from .reports import ESTADO_RECAUDO, filter_by_date, normalize_dataframe
from .repository import GuiaRepository


OFICINA_NOMBRE = "SAN GIL"
ADMIN_NAME = "JOHAN A. ORTIZ"
SERVICIOS_RELACION = ("RR", "CE")

DARK_FILL = colors.HexColor("#1F3864")
TITLE_TEXT = colors.HexColor("#FFC000")


def format_currency_co(value: int) -> str:
    return f"$ {value:,}".replace(",", ".")


def generate_relacion_ce_rr_report(
    repository: GuiaRepository,
    output_dir: Path,
    target_date: date,
    admin_name: str = ADMIN_NAME,
    oficina_nombre: str = OFICINA_NOMBRE,
) -> Path:
    dataframe = normalize_dataframe(repository.to_dataframe())
    daily = filter_by_date(dataframe, target_date)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"relacion guias ce y rr {target_date.day:02d} {MONTHS_ES[target_date.month]}.pdf"

    fecha_label = target_date.strftime("%d/%m/%Y")

    elements: list = []

    if not daily.empty:
        relevant = daily[
            (daily["ESTADO"].str.upper() == ESTADO_RECAUDO) & (daily["SERVICIO"].str.upper().isin(SERVICIOS_RELACION))
        ]
        operators = sorted(relevant["OPERADOR"].unique())
    else:
        relevant = daily
        operators = []

    first = True
    for operador in operators:
        operator_rows = relevant[relevant["OPERADOR"] == operador].sort_values("SERVICIO")
        if operator_rows.empty:
            continue

        if not first:
            elements.append(PageBreak())
        first = False

        rows = [
            ["RELACION DE GUIAS CE Y RR " + oficina_nombre, "", "", ""],
            ["INFORME OFICINA EXPRESANGIL", "", "", ""],
            [admin_name, "", "FECHA", fecha_label],
            ["GUIAS CONTRAENTREGA Y RECAUDO", "", "", ""],
            ["N°", "CE O RR", "N° DE GUIA", "VALOR"],
        ]

        total = 0
        for index, (_, row) in enumerate(operator_rows.iterrows(), start=1):
            valor = int(row["VALOR_NUMERICO"])
            total += valor
            rows.append([str(index), row["SERVICIO"], row["GUIA"], format_currency_co(valor)])

        rows.append(["TOTAL", "", "", format_currency_co(total)])

        data_row_count = len(operator_rows)
        last_row_index = len(rows) - 1

        table = Table(rows, colWidths=[2 * cm, 3 * cm, 6 * cm, 4 * cm], repeatRows=5)
        table.setStyle(
            TableStyle(
                [
                    ("SPAN", (0, 0), (-1, 0)),
                    ("SPAN", (0, 1), (-1, 1)),
                    ("SPAN", (0, 2), (1, 2)),
                    ("SPAN", (0, 3), (-1, 3)),
                    ("SPAN", (0, last_row_index), (2, last_row_index)),
                    ("BACKGROUND", (0, 0), (-1, 0), DARK_FILL),
                    ("BACKGROUND", (0, 1), (-1, 1), DARK_FILL),
                    ("BACKGROUND", (0, 2), (-1, 2), colors.white),
                    ("BACKGROUND", (0, 3), (-1, 3), DARK_FILL),
                    ("BACKGROUND", (0, 4), (-1, 4), DARK_FILL),
                    ("BACKGROUND", (0, last_row_index), (-1, last_row_index), DARK_FILL),
                    ("TEXTCOLOR", (0, 0), (-1, 0), TITLE_TEXT),
                    ("TEXTCOLOR", (0, 1), (-1, 1), colors.white),
                    ("TEXTCOLOR", (0, 2), (-1, 2), colors.black),
                    ("TEXTCOLOR", (0, 3), (-1, 3), TITLE_TEXT),
                    ("TEXTCOLOR", (0, 4), (-1, 4), colors.white),
                    ("TEXTCOLOR", (0, last_row_index), (-1, last_row_index), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                    ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
                    ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
                    ("FONTNAME", (0, 4), (-1, 4), "Helvetica-Bold"),
                    ("FONTNAME", (0, last_row_index), (-1, last_row_index), "Helvetica-Bold"),
                    ("ALIGN", (0, 0), (-1, 4), "CENTER"),
                    ("ALIGN", (0, last_row_index), (-1, last_row_index), "CENTER"),
                    ("ALIGN", (0, 5), (0, 4 + data_row_count), "CENTER"),
                    ("ALIGN", (1, 5), (1, 4 + data_row_count), "CENTER"),
                    ("ALIGN", (3, 5), (3, last_row_index), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )

        elements.append(table)
        elements.append(Spacer(1, 14))

    if not elements:
        elements.append(Paragraph("Sin registros para esta fecha", getSampleStyleSheet()["Normal"]))

    doc = SimpleDocTemplate(str(output_path), pagesize=letter, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    doc.build(elements)

    return output_path
