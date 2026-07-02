from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from .exporter import MONTHS_ES
from .reports import apply_report_format, filter_by_date, normalize_dataframe
from .repository import GuiaRepository


# Estado que marca una guia como devolucion (novedad "D" del modulo operadores).
ESTADO_DEVOLUCION = "D"

DEVOLUCIONES_COLUMNS = [
    "PLANILLA",
    "SERVICIO",
    "GUIA",
    "UNID",
    "TIPO DE SERVICIO",
    "DESTINATARIO",
    "MUNICIPIO",
    "VALOR",
    "ESTADO",
    "CAUSAL",
    "F_INGRESO",
    "F_ENTREGA",
]


def generate_devoluciones_report(
    repository: GuiaRepository, output_dir: Path, target_date: date
) -> Path:
    dataframe = normalize_dataframe(repository.to_dataframe())
    daily = filter_by_date(dataframe, target_date)
    devoluciones = daily[daily["ESTADO"].str.upper() == ESTADO_DEVOLUCION]
    detail = devoluciones[DEVOLUCIONES_COLUMNS]

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = (
        output_dir / f"informe de devoluciones {target_date.day:02d} {MONTHS_ES[target_date.month]}.xlsx"
    )

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        detail.to_excel(writer, index=False, sheet_name="DEVOLUCIONES")
        for sheet_name in writer.sheets:
            apply_report_format(writer.sheets[sheet_name])

    return output_path
