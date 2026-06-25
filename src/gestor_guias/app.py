from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import load_settings
from .devoluciones import generate_devoluciones_report
from .excel_processor import consolidate_excels_with_movements
from .exporter import export_dataframe, export_movements_copy
from .operadores import hash_password
from .recaudo import generate_recaudo_report
from .relacion_ce_rr import generate_relacion_ce_rr_report
from .reports import (
    generate_daily_report,
    generate_entregadas_operador_excel,
    generate_monthly_operator_report,
    generate_operator_report,
    generate_reports,
    generate_salidas_operador_excel,
)
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

    result = consolidate_excels_with_movements(
        attachments, settings.excel.columns, import_date=target_date.isoformat()
    )
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

    result = consolidate_excels_with_movements(
        files, settings.excel.columns, import_date=target_date.isoformat()
    )
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


def report_by_operator(target_date: date | None, operador: str = "") -> Path:
    settings = load_settings()
    repository = GuiaRepository(settings.paths.database_file)
    output_path = generate_operator_report(repository, settings.paths.output_dir, target_date, operador)
    print(f"Informe generado: {output_path}")
    return output_path


def report_of_day(target_date: date) -> Path:
    settings = load_settings()
    repository = GuiaRepository(settings.paths.database_file)
    output_path = generate_daily_report(repository, settings.paths.output_dir, target_date)
    print(f"Informe generado: {output_path}")
    return output_path


def report_of_recaudo(target_date: date) -> Path:
    settings = load_settings()
    repository = GuiaRepository(settings.paths.database_file)
    output_path = generate_recaudo_report(repository, settings.paths.output_dir, target_date)
    print(f"Informe generado: {output_path}")
    return output_path


def report_relacion_ce_rr(target_date: date) -> Path:
    settings = load_settings()
    repository = GuiaRepository(settings.paths.database_file)
    output_path = generate_relacion_ce_rr_report(
        repository,
        settings.paths.output_dir,
        target_date,
        admin_name=settings.oficina.admin_name,
        oficina_nombre=settings.oficina.nombre,
    )
    print(f"Informe generado: {output_path}")
    return output_path


def report_of_salidas_operador(operador: str, target_date: date) -> Path:
    settings = load_settings()
    repository = GuiaRepository(settings.paths.database_file)
    output_path = generate_salidas_operador_excel(repository, settings.paths.output_dir, operador, target_date)
    print(f"Informe generado: {output_path}")
    return output_path


def report_of_entregas_operador(operador: str, target_date: date) -> Path:
    settings = load_settings()
    repository = GuiaRepository(settings.paths.database_file)
    output_path = generate_entregadas_operador_excel(repository, settings.paths.output_dir, operador, target_date)
    print(f"Informe generado: {output_path}")
    return output_path


def report_of_devoluciones(target_date: date) -> Path:
    settings = load_settings()
    repository = GuiaRepository(settings.paths.database_file)
    output_path = generate_devoluciones_report(repository, settings.paths.output_dir, target_date)
    print(f"Informe generado: {output_path}")
    return output_path


def report_monthly_by_operator(year: int, month: int) -> Path:
    settings = load_settings()
    repository = GuiaRepository(settings.paths.database_file)
    output_path = generate_monthly_operator_report(repository, settings.paths.output_dir, year, month)
    print(f"Informe generado: {output_path}")
    return output_path


def open_editor() -> None:
    # Import perezoso: tkinter solo esta disponible/es necesario en uso local
    # de escritorio, no en el servidor donde corre el panel web.
    from .editor_gui import run_editor

    settings = load_settings()
    repository = GuiaRepository(settings.paths.database_file)
    run_editor(repository, settings.paths.output_dir, settings.oficina)


def operador_crear(usuario: str, password: str, nombre: str, rol: str = "operador") -> None:
    settings = load_settings()
    repository = GuiaRepository(settings.paths.database_file)
    repository.crear_operador(usuario.strip(), hash_password(password), nombre.strip(), rol)
    print(f"Usuario '{usuario}' creado/actualizado para '{nombre}' con rol '{rol}'.")


def operador_listar() -> None:
    settings = load_settings()
    repository = GuiaRepository(settings.paths.database_file)
    operadores = repository.listar_operadores()
    if not operadores:
        print("No hay operadores registrados.")
        return
    for operador in operadores:
        print(f"{operador['usuario']} -> {operador['nombre']} ({operador['rol']})")


def operador_eliminar(usuario: str) -> None:
    settings = load_settings()
    repository = GuiaRepository(settings.paths.database_file)
    eliminado = repository.eliminar_operador(usuario.strip())
    print("Operador eliminado." if eliminado else "Operador no encontrado.")


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

    operator_report_parser = subparsers.add_parser(
        "informe-operador",
        help="Genera el informe por operador a partir de las guias guardadas",
    )
    operator_report_parser.add_argument(
        "--fecha", help="Filtra por fecha de planilla en formato YYYY-MM-DD (opcional)"
    )
    operator_report_parser.add_argument(
        "--operador", help="Filtra el informe a un solo operador (opcional, vacio = todos)"
    )

    salidas_report_parser = subparsers.add_parser(
        "informe-salidas",
        help="Genera el Excel con las guias en salida (en reparto) de un operador",
    )
    salidas_report_parser.add_argument("--operador", required=True, help="Nombre del operador")
    salidas_report_parser.add_argument(
        "--fecha", help="Fecha de planilla a consultar en formato YYYY-MM-DD (por defecto hoy)"
    )

    entregas_report_parser = subparsers.add_parser(
        "informe-entregas",
        help="Genera el Excel con las guias entregadas y recaudadas (estado E) de un operador",
    )
    entregas_report_parser.add_argument("--operador", required=True, help="Nombre del operador")
    entregas_report_parser.add_argument(
        "--fecha", help="Fecha de cierre a consultar en formato YYYY-MM-DD (por defecto hoy)"
    )

    daily_report_parser = subparsers.add_parser(
        "informe-dia",
        help="Genera el informe del dia a partir de las guias guardadas",
    )
    daily_report_parser.add_argument(
        "--fecha", help="Fecha de planilla a consultar en formato YYYY-MM-DD (por defecto hoy)"
    )

    recaudo_report_parser = subparsers.add_parser(
        "informe-recaudo",
        help="Genera el informe de recaudo diario a partir de las guias guardadas",
    )
    recaudo_report_parser.add_argument(
        "--fecha", help="Fecha de planilla a consultar en formato YYYY-MM-DD (por defecto hoy)"
    )

    relacion_ce_rr_parser = subparsers.add_parser(
        "informe-relacion-ce-rr",
        help="Genera la relacion de guias CE y RR entregadas y recaudadas por operador",
    )
    relacion_ce_rr_parser.add_argument(
        "--fecha", help="Fecha de planilla a consultar en formato YYYY-MM-DD (por defecto hoy)"
    )

    devoluciones_report_parser = subparsers.add_parser(
        "informe-devoluciones",
        help="Genera el informe de devoluciones (estado D) a partir de las guias guardadas",
    )
    devoluciones_report_parser.add_argument(
        "--fecha", help="Fecha de planilla a consultar en formato YYYY-MM-DD (por defecto hoy)"
    )

    monthly_report_parser = subparsers.add_parser(
        "informe-mensual",
        help="Genera el informe mensual por operador (gastos, adelantos, gestionadas, entregadas, efectividad)",
    )
    monthly_report_parser.add_argument("--mes", required=True, help="Mes a consultar en formato YYYY-MM")

    subparsers.add_parser("editar", help="Abre la interfaz para editar operador, estado y causal")

    operador_crear_parser = subparsers.add_parser(
        "operador-crear",
        help="Crea o actualiza un usuario de operador para el modulo de operadores",
    )
    operador_crear_parser.add_argument("--usuario", required=True, help="Usuario de acceso")
    operador_crear_parser.add_argument("--password", required=True, help="Contraseña de acceso")
    operador_crear_parser.add_argument(
        "--nombre", required=True, help="Nombre del operador como aparece en la columna OPERADOR"
    )
    operador_crear_parser.add_argument(
        "--rol",
        choices=["operador", "admin"],
        default="operador",
        help="Rol del usuario: operador o admin (por defecto operador)",
    )

    subparsers.add_parser("operador-listar", help="Lista los usuarios de operador registrados")

    operador_eliminar_parser = subparsers.add_parser(
        "operador-eliminar", help="Elimina un usuario de operador"
    )
    operador_eliminar_parser.add_argument("--usuario", required=True, help="Usuario a eliminar")

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
    elif args.command == "informe-operador":
        fecha = parse_date(args.fecha, settings.gmail.timezone) if args.fecha else None
        report_by_operator(fecha, args.operador or "")
    elif args.command == "informe-salidas":
        fecha = parse_date(args.fecha, settings.gmail.timezone) if args.fecha else date.today()
        report_of_salidas_operador(args.operador, fecha)
    elif args.command == "informe-entregas":
        fecha = parse_date(args.fecha, settings.gmail.timezone) if args.fecha else date.today()
        report_of_entregas_operador(args.operador, fecha)
    elif args.command == "informe-dia":
        report_of_day(parse_date(args.fecha, settings.gmail.timezone))
    elif args.command == "informe-recaudo":
        report_of_recaudo(parse_date(args.fecha, settings.gmail.timezone))
    elif args.command == "informe-relacion-ce-rr":
        report_relacion_ce_rr(parse_date(args.fecha, settings.gmail.timezone))
    elif args.command == "informe-devoluciones":
        report_of_devoluciones(parse_date(args.fecha, settings.gmail.timezone))
    elif args.command == "informe-mensual":
        anio, mes = (int(parte) for parte in args.mes.split("-"))
        report_monthly_by_operator(anio, mes)
    elif args.command == "editar":
        open_editor()
    elif args.command == "operador-crear":
        operador_crear(args.usuario, args.password, args.nombre, args.rol)
    elif args.command == "operador-listar":
        operador_listar()
    elif args.command == "operador-eliminar":
        operador_eliminar(args.usuario)


if __name__ == "__main__":
    main()
