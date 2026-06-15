from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import load_settings
from .editor_gui import run_editor
from .excel_processor import consolidate_excels_with_movements
from .exporter import export_dataframe, export_movements_copy
from .reports import generate_reports
from .repository import GuiaRepository


def parse_date(value: str | None, timezone: str = "America/Bogota") -> date:
    if value is None:
        return datetime.now(ZoneInfo(timezone)).date()
    return datetime.strptime(value, "%Y-%m-%d").date()


def consolidate(target_date: date) -> Path:
    from .gmail_client import GmailAttachmentDownloader

    settings = load_settings()
    daily_attachment_dir = settings.paths.attachments_dir / target_date.isoformat()

    downloader = GmailAttachmentDownloader(
        credentials_file=settings.gmail.credentials_file,
        token_file=settings.gmail.token_file,
    )
    attachments = downloader.download_excel_attachments(
        senders=settings.gmail.senders,
        target_date=target_date,
        output_dir=daily_attachment_dir,
    )

    result = consolidate_excels_with_movements(attachments, settings.excel.columns)
    repository = GuiaRepository(settings.paths.database_file)
    repository.save_consolidated(result.active)

    output_path = export_dataframe(repository.to_dataframe(), settings.paths.output_dir, target_date)
    movements_path = export_movements_copy(result.movements_copy, settings.paths.output_dir, target_date)
    print(f"Adjuntos descargados: {len(attachments)}")
    print(f"Guias con estado N: {len(result.active)}")
    print(f"Movimientos con otros estados: {len(result.movements_copy)}")
    print(f"Archivo generado: {output_path}")
    if movements_path:
        print(f"Copia de movimientos generada: {movements_path}")
    return output_path


def process_local_files(paths: list[str], target_date: date) -> Path:
    settings = load_settings()
    files = [Path(path) for path in paths]
    missing = [str(path) for path in files if not path.exists()]
    if missing:
        raise FileNotFoundError(f"No existen estos archivos: {', '.join(missing)}")

    result = consolidate_excels_with_movements(files, settings.excel.columns)
    repository = GuiaRepository(settings.paths.database_file)
    repository.save_consolidated(result.active)

    output_path = export_dataframe(repository.to_dataframe(), settings.paths.output_dir, target_date)
    movements_path = export_movements_copy(result.movements_copy, settings.paths.output_dir, target_date)
    print(f"Archivos procesados: {len(files)}")
    print(f"Guias con estado N: {len(result.active)}")
    print(f"Movimientos con otros estados: {len(result.movements_copy)}")
    print(f"Archivo generado: {output_path}")
    if movements_path:
        print(f"Copia de movimientos generada: {movements_path}")
    return output_path


def clear_data(confirm: bool) -> None:
    if not confirm:
        raise ValueError("Para borrar la informacion guardada usa: borrar-datos --confirmar")

    settings = load_settings()
    repository = GuiaRepository(settings.paths.database_file)
    repository.clear_all()
    print("Informacion guardada borrada correctamente.")


def export_existing(target_date: date) -> Path:
    settings = load_settings()
    repository = GuiaRepository(settings.paths.database_file)
    output_path = export_dataframe(repository.to_dataframe(), settings.paths.output_dir, target_date)
    print(f"Archivo generado: {output_path}")
    return output_path


def generate_reports_from_file(source_file: str, target_date: date) -> Path:
    settings = load_settings()
    output_path = generate_reports(Path(source_file), settings.paths.output_dir, target_date)
    print(f"Informes generados: {output_path}")
    return output_path


def open_editor() -> None:
    settings = load_settings()
    repository = GuiaRepository(settings.paths.database_file)
    run_editor(repository)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gestor diario de guias Envia")
    subparsers = parser.add_subparsers(dest="command", required=True)

    consolidate_parser = subparsers.add_parser("consolidar", help="Descarga adjuntos y genera Excel final")
    consolidate_parser.add_argument("--fecha", help="Fecha a procesar en formato YYYY-MM-DD")

    export_parser = subparsers.add_parser("exportar", help="Exporta a Excel las guias guardadas")
    export_parser.add_argument("--fecha", help="Fecha para nombrar el archivo en formato YYYY-MM-DD")

    import_parser = subparsers.add_parser(
        "importar",
        help="Importa planillas descargadas manualmente y conserva la informacion existente",
    )
    import_parser.add_argument("archivos", nargs="+", help="Rutas de archivos .xls o .xlsx")
    import_parser.add_argument("--fecha", help="Fecha para nombrar el archivo en formato YYYY-MM-DD")

    local_parser = subparsers.add_parser(
        "procesar-archivos",
        help="Alias de importar para compatibilidad",
    )
    local_parser.add_argument("archivos", nargs="+", help="Rutas de archivos .xls o .xlsx")
    local_parser.add_argument("--fecha", help="Fecha para nombrar el archivo en formato YYYY-MM-DD")

    reports_parser = subparsers.add_parser(
        "informes",
        help="Genera informes generales y por operador desde el consolidado diario",
    )
    reports_parser.add_argument("archivo", help="Ruta del consolidado diario .xlsx")
    reports_parser.add_argument("--fecha", help="Fecha para nombrar el archivo en formato YYYY-MM-DD")

    clear_parser = subparsers.add_parser(
        "borrar-datos",
        help="Borra toda la informacion guardada cuando el usuario lo confirme",
    )
    clear_parser.add_argument("--confirmar", action="store_true", help="Confirma el borrado total")

    subparsers.add_parser("editar", help="Abre la interfaz para editar operador, estado y causal")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    settings = load_settings()

    if args.command == "consolidar":
        consolidate(parse_date(args.fecha, settings.gmail.timezone))
    elif args.command == "exportar":
        export_existing(parse_date(args.fecha, settings.gmail.timezone))
    elif args.command in {"importar", "procesar-archivos"}:
        process_local_files(args.archivos, parse_date(args.fecha, settings.gmail.timezone))
    elif args.command == "informes":
        generate_reports_from_file(args.archivo, parse_date(args.fecha, settings.gmail.timezone))
    elif args.command == "borrar-datos":
        clear_data(args.confirmar)
    elif args.command == "editar":
        open_editor()


if __name__ == "__main__":
    main()
