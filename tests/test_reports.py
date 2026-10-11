from datetime import date
from gestor_guias.excel_processor import hoy_colombia
from pathlib import Path

import pandas as pd

from gestor_guias.devoluciones import generate_devoluciones_report
from gestor_guias.recaudo import generate_recaudo_report
from gestor_guias.relacion_ce_rr import generate_relacion_ce_rr_report
from gestor_guias.repository import GuiaRepository
from gestor_guias.reports import (
    build_cierre_breakdown,
    build_monthly_breakdown,
    filter_by_gestion,
    generate_entregadas_operador_excel,
    generate_monthly_operator_report,
    generate_operator_report,
    generate_salidas_operador_excel,
    normalize_dataframe,
)
from openpyxl import load_workbook


def build_dataframe(guia: str, operador: str, estado: str, valor: str, servicio: str = "") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "PLANILLA": "1",
                "SERVICIO": servicio,
                "GUIA": guia,
                "UNID": "1",
                "TIPO DE SERVICIO": "PT",
                "DESTINATARIO": "Persona",
                "MUNICIPIO": "SAN GIL",
                "VALOR": valor,
                "OPERADOR": operador,
                "ESTADO": estado,
                "CAUSAL": "",
                "F_INGRESO": "2026-06-10 00:00:00",
                "F_ENTREGA": "",
            }
        ]
    )


def test_build_cierre_breakdown_suma_efectivo_de_varios_operadores(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "", "", "10000"))
    repository.update_tracking_fields("100", "OMAR", "E", "")
    repository.save_consolidated(build_dataframe("200", "", "", "20000"))
    repository.update_tracking_fields("200", "KEVIN", "E", "")

    repository.guardar_cierre(
        fecha="2026-06-10", operador="OMAR", gestionadas=1, ro=0, n=0, d=0, e=1,
        recaudado=10_000, bancos=0, nequi=0, envia=0, efectivo=10_000,
    )
    repository.guardar_cierre(
        fecha="2026-06-10", operador="KEVIN", gestionadas=1, ro=0, n=0, d=0, e=1,
        recaudado=20_000, bancos=5_000, nequi=0, envia=0, efectivo=15_000,
        gastos=2_000,
    )

    dataframe = normalize_dataframe(repository.to_dataframe())
    resumen = build_cierre_breakdown(repository, dataframe, date(2026, 6, 10))

    assert int(resumen["EFECTIVO"].sum()) == 25_000
    assert int(resumen.set_index("OPERADOR").loc["KEVIN", "GASTOS"]) == 2_000


def test_build_cierre_breakdown_incluye_cantidad_de_billetes_contados(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "", "", "10000"))
    repository.update_tracking_fields("100", "OMAR", "E", "")

    repository.guardar_cierre(
        fecha="2026-06-10", operador="OMAR", gestionadas=1, ro=0, n=0, d=0, e=1,
        recaudado=10_000, bancos=0, nequi=0, envia=0, efectivo=10_000,
        denominaciones={50_000: 0, 10_000: 1, 1_000: 0},
    )

    dataframe = normalize_dataframe(repository.to_dataframe())
    resumen = build_cierre_breakdown(repository, dataframe, date(2026, 6, 10))

    fila = resumen.set_index("OPERADOR").loc["OMAR"]
    assert int(fila["BILLETES 10.000"]) == 1
    assert int(fila["BILLETES 50.000"]) == 0


def test_build_cierre_breakdown_incluye_cierre_sin_guias_del_dia(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe_con_fecha("100", "", "", "10000", "2026-06-05 00:00:00"))
    repository.update_tracking_fields("100", "OMAR", "E", "", "2026-06-05")

    repository.guardar_cierre(
        fecha="2026-06-10", operador="OMAR", gestionadas=0, ro=0, n=0, d=0, e=0,
        recaudado=0, bancos=0, nequi=0, envia=0, efectivo=7_161_650,
    )

    dataframe = filter_by_gestion(normalize_dataframe(repository.to_dataframe()), date(2026, 6, 10))
    resumen = build_cierre_breakdown(repository, dataframe, date(2026, 6, 10))

    assert int(resumen.set_index("OPERADOR").loc["OMAR", "EFECTIVO"]) == 7_161_650


def test_generate_operator_report_incluye_detalle_de_guias_entregadas(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe_con_fecha("100", "", "", "10000", "2026-06-10 00:00:00"))
    repository.update_tracking_fields("100", "OMAR", "E", "", "2026-06-10")
    repository.save_consolidated(build_dataframe_con_fecha("200", "", "", "20000", "2026-06-10 00:00:00"))
    repository.update_tracking_fields("200", "KEVIN", "R", "")

    output_path = generate_operator_report(repository, tmp_path / "output", date(2026, 6, 10))

    workbook = load_workbook(output_path)
    assert "GUIAS ENTREGADAS" in workbook.sheetnames
    assert "CIERRE" in workbook.sheetnames
    sheet = workbook["GUIAS ENTREGADAS"]
    guias = [sheet.cell(row=row, column=2).value for row in range(2, sheet.max_row + 1)]
    assert guias == ["100"]


def test_generate_salidas_operador_excel_solo_incluye_guias_en_reparto(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "", "", "10000"))
    repository.update_tracking_fields("100", "KEVIN", "R", "")

    repository.save_consolidated(build_dataframe("200", "", "", "20000"))
    repository.update_tracking_fields("200", "KEVIN", "E", "")

    repository.save_consolidated(build_dataframe("300", "", "", "30000"))
    repository.update_tracking_fields("300", "OMAR", "R", "")

    output_path = generate_salidas_operador_excel(repository, tmp_path / "output", "KEVIN", date(2026, 6, 10))

    assert output_path.exists()
    assert output_path.suffix == ".xlsx"

    worksheet = load_workbook(output_path)["SALIDAS"]
    guias = [worksheet.cell(row=row, column=1).value for row in range(2, worksheet.max_row + 1)]
    assert "100" in guias
    assert "200" not in guias
    assert "300" not in guias


def test_generate_salidas_operador_excel_no_depende_de_la_fecha_de_planilla(tmp_path: Path) -> None:
    # La guia puede haber llegado en una planilla de otro dia y salir hoy;
    # el informe debe encontrarla igual, sin filtrar por F_INGRESO.
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "", "", "10000"))
    repository.asignar_salida(["100"], "KEVIN", "R")

    output_path = generate_salidas_operador_excel(repository, tmp_path / "output", "KEVIN", date(2026, 6, 23))

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_guias_en_salida_respeta_el_orden_de_registro(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    for guia in ("300", "100", "200"):
        repository.save_consolidated(build_dataframe(guia, "", "", "10000"))

    repository.asignar_salida(["300", "100"], "KEVIN", "R")
    repository.asignar_salida(["200"], "KEVIN", "R")

    guias = repository.guias_en_salida("KEVIN", "R")

    assert [guia["guia"] for guia in guias] == ["300", "100", "200"]


def test_generate_salidas_operador_excel_sin_guias(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    output_path = generate_salidas_operador_excel(repository, tmp_path / "output", "KEVIN", date(2026, 6, 10))

    assert output_path.exists()


def test_generate_entregadas_operador_excel_solo_incluye_guias_entregadas(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "", "", "10000"))
    repository.asignar_salida(["100"], "KEVIN", "R")
    repository.update_tracking_fields("100", "KEVIN", "E", "")

    repository.save_consolidated(build_dataframe("200", "", "", "20000"))
    repository.asignar_salida(["200"], "KEVIN", "R")

    repository.save_consolidated(build_dataframe("300", "", "", "30000"))
    repository.asignar_salida(["300"], "OMAR", "R")
    repository.update_tracking_fields("300", "OMAR", "E", "")

    output_path = generate_entregadas_operador_excel(repository, tmp_path / "output", "KEVIN", hoy_colombia())

    assert output_path.exists()
    assert output_path.suffix == ".xlsx"

    worksheet = load_workbook(output_path)["ENTREGAS"]
    guias = [worksheet.cell(row=row, column=1).value for row in range(2, worksheet.max_row + 1)]
    assert "100" in guias
    assert "200" not in guias
    assert "300" not in guias


def test_generate_entregadas_operador_excel_incluye_hoja_de_cierre_con_denominaciones(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    output_path = generate_entregadas_operador_excel(
        repository,
        tmp_path / "output",
        "KEVIN",
        hoy_colombia(),
        resumen={"gestionadas": 2, "recaudado": 30_000, "efectivo": 30_000, "efectivo_contado": 30_000},
        denominaciones={"20000": 1, "10000": 1},
    )

    worksheet = load_workbook(output_path)["CIERRE"]
    valores = [
        cell.value
        for row in worksheet.iter_rows(min_row=1, max_row=worksheet.max_row, max_col=3)
        for cell in row
        if cell.value is not None
    ]
    assert "CONTEO DE EFECTIVO EN CAJA" in valores
    assert 20000 in valores
    assert 10000 in valores
    assert 20000 * 1 in valores


def test_generate_entregadas_operador_excel_sin_guias(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    output_path = generate_entregadas_operador_excel(repository, tmp_path / "output", "KEVIN", hoy_colombia())

    assert output_path.exists()


def test_generate_recaudo_report(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "", "", "10000"))
    repository.update_tracking_fields("100", "OMAR", "E", "")

    repository.save_consolidated(build_dataframe("200", "", "", "20000"))
    repository.update_tracking_fields("200", "OMAR", "R", "")

    output_path = generate_recaudo_report(repository, tmp_path / "output", date(2026, 6, 10))

    assert output_path.exists()
    assert output_path.suffix == ".xlsx"


def test_generate_recaudo_report_incluye_bancos_nequi_envia_gastos_y_adelanto(tmp_path: Path) -> None:
    import openpyxl

    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "", "", "10000"))
    repository.update_tracking_fields("100", "OMAR", "E", "")

    repository.guardar_cierre(
        fecha="2026-06-10", operador="OMAR", gestionadas=1, ro=0, n=0, d=0, e=1,
        recaudado=10_000, bancos=3_000, nequi=2_000, envia=1_000, efectivo=4_000,
        gastos=500, adelanto_salario=1_500,
    )

    output_path = generate_recaudo_report(repository, tmp_path / "output", date(2026, 6, 10))

    workbook = openpyxl.load_workbook(output_path)
    sheet = workbook["RECAUDO"]
    fila = next(fila for fila in sheet.iter_rows(min_row=5) if fila[0].value == "OMAR")

    assert fila[3].value == 3_000
    assert fila[4].value == 2_000
    assert fila[5].value == 1_000
    assert fila[6].value == 500
    assert fila[7].value == 1_500

    fila_gastos_dia = next(
        fila for fila in sheet.iter_rows(min_row=1, max_col=1) if fila[0].value == "Gastos del dia"
    )
    valor_gastos_dia = sheet.cell(row=fila_gastos_dia[0].row, column=2).value
    assert "G" in valor_gastos_dia


def test_generate_recaudo_report_no_data(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    output_path = generate_recaudo_report(repository, tmp_path / "output", date(2026, 6, 10))

    assert output_path.exists()


def test_generate_relacion_ce_rr_report(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "", "", "15000", "RR"))
    repository.update_tracking_fields("100", "JOHAN ORTIZ", "E", "", "2026-06-10")

    repository.save_consolidated(build_dataframe("200", "", "", "19900", "CE"))
    repository.update_tracking_fields("200", "JOHAN ORTIZ", "E", "", "2026-06-10")

    repository.save_consolidated(build_dataframe("300", "", "", "20000", "PT"))
    repository.update_tracking_fields("300", "JOHAN ORTIZ", "E", "")

    repository.save_consolidated(build_dataframe("400", "", "", "30000", "RR"))
    repository.update_tracking_fields("400", "JOHAN ORTIZ", "R", "")

    output_path = generate_relacion_ce_rr_report(repository, tmp_path / "output", date(2026, 6, 10))

    assert output_path.exists()
    assert output_path.suffix == ".xlsx"
    assert output_path.stat().st_size > 0


def test_generate_relacion_ce_rr_report_resta_link_envia(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "", "", "15000", "RR"))
    repository.update_tracking_fields("100", "JOHAN ORTIZ", "E", "", "2026-06-10")

    repository.save_consolidated(build_dataframe("200", "", "", "19900", "CE"))
    repository.update_tracking_fields("200", "JOHAN ORTIZ", "E", "", "2026-06-10")

    repository.guardar_cierre(
        fecha="2026-06-10", operador="JOHAN ORTIZ", gestionadas=2, ro=0, n=0, d=0, e=2,
        recaudado=34_900, bancos=0, nequi=0, envia=10_000, efectivo=24_900,
    )

    output_path = generate_relacion_ce_rr_report(repository, tmp_path / "output", date(2026, 6, 10))

    workbook = load_workbook(output_path)
    sheet = workbook["RELACION CE Y RR"]

    fila_total = next(fila for fila in sheet.iter_rows() if fila[0].value == "TOTAL")
    assert sheet.cell(row=fila_total[0].row, column=4).value == 34_900

    fila_link = next(fila for fila in sheet.iter_rows() if fila[0].value == "(-) LINK ENVIA")
    assert sheet.cell(row=fila_link[0].row, column=4).value == 10_000

    fila_total_recaudar = next(fila for fila in sheet.iter_rows() if fila[0].value == "TOTAL A RECAUDAR")
    assert sheet.cell(row=fila_total_recaudar[0].row, column=4).value == 24_900


def test_generate_relacion_ce_rr_report_no_data(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    output_path = generate_relacion_ce_rr_report(repository, tmp_path / "output", date(2026, 6, 10))

    assert output_path.exists()


def test_generate_devoluciones_report(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "", "", "10000"))
    repository.update_tracking_fields("100", "OMAR", "D", "DIRECCION ERRADA", "2026-06-10")

    repository.save_consolidated(build_dataframe("200", "", "", "20000"))
    repository.update_tracking_fields("200", "OMAR", "E", "", "2026-06-10")

    output_path = generate_devoluciones_report(repository, tmp_path / "output", date(2026, 6, 10))

    assert output_path.exists()
    assert output_path.suffix == ".xlsx"

    dataframe = pd.read_excel(output_path, dtype=str)
    assert list(dataframe["GUIA"]) == ["100"]
    assert dataframe.iloc[0]["CAUSAL"] == "DIRECCION ERRADA"


def build_dataframe_con_fecha(guia: str, operador: str, estado: str, valor: str, fecha: str) -> pd.DataFrame:
    dataframe = build_dataframe(guia, operador, estado, valor)
    dataframe["F_INGRESO"] = fecha
    return dataframe


def test_build_monthly_breakdown_calcula_efectividad_por_operador(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe_con_fecha("100", "", "", "10000", "2026-06-05 00:00:00"))
    repository.update_tracking_fields("100", "KEVIN", "E", "", "2026-06-05")
    repository.save_consolidated(build_dataframe_con_fecha("200", "", "", "20000", "2026-06-15 00:00:00"))
    repository.update_tracking_fields("200", "KEVIN", "RO", "", "2026-06-15")
    # Sigue en reparto: no se gestiono, asi que no entra al mes.
    repository.save_consolidated(build_dataframe_con_fecha("250", "", "", "25000", "2026-06-20 00:00:00"))
    repository.update_tracking_fields("250", "KEVIN", "R", "")
    repository.save_consolidated(build_dataframe_con_fecha("300", "", "", "30000", "2026-07-01 00:00:00"))
    repository.update_tracking_fields("300", "KEVIN", "E", "", "2026-07-01")

    repository.guardar_cierre(
        fecha="2026-06-05", operador="KEVIN", gestionadas=1, ro=0, n=0, d=0, e=1,
        recaudado=10_000, bancos=0, nequi=0, envia=0, efectivo=10_000,
        gastos=2_000, adelanto_salario=5_000,
    )

    dataframe = normalize_dataframe(repository.to_dataframe())
    resumen = build_monthly_breakdown(repository, dataframe, 2026, 6)

    fila = resumen.set_index("OPERADOR").loc["KEVIN"]
    assert int(fila["GESTIONADAS"]) == 2
    assert int(fila["ENTREGADAS"]) == 1
    assert fila["EFECTIVIDAD"] == 50.0
    assert int(fila["GASTOS"]) == 2_000
    assert int(fila["ADELANTO_SALARIO"]) == 5_000


def test_generate_monthly_operator_report(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe_con_fecha("100", "", "", "10000", "2026-06-05 00:00:00"))
    repository.update_tracking_fields("100", "KEVIN", "E", "", "2026-06-05")

    output_path = generate_monthly_operator_report(repository, tmp_path / "output", 2026, 6)

    assert output_path.exists()
    assert output_path.suffix == ".xlsx"


def test_generate_devoluciones_report_no_data(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    output_path = generate_devoluciones_report(repository, tmp_path / "output", date(2026, 6, 10))

    assert output_path.exists()


def _preparar_entregadas_del_mes(tmp_path: Path) -> GuiaRepository:
    repository = GuiaRepository(tmp_path / "guias.db")
    repository.save_consolidated(build_dataframe("100", "", "", "10000"))
    repository.update_tracking_fields("100", "OMAR", "E", "")
    repository.save_consolidated(build_dataframe("200", "", "", "20000"))
    repository.update_tracking_fields("200", "OMAR", "E", "")
    repository.save_consolidated(build_dataframe("300", "", "", "30000"))
    repository.update_tracking_fields("300", "KEVIN", "E", "")
    # Una guia sin entregar no debe aparecer en el informe.
    repository.save_consolidated(build_dataframe("400", "KEVIN", "R", "5000"))
    return repository


def test_generate_cierre_mensual_entregadas_incluye_promedio_por_empleado(tmp_path: Path) -> None:
    from gestor_guias.reports import generate_cierre_mensual_entregadas_excel

    repository = _preparar_entregadas_del_mes(tmp_path)
    hoy = hoy_colombia()

    ruta = generate_cierre_mensual_entregadas_excel(repository, tmp_path, hoy.year, hoy.month)

    workbook = load_workbook(ruta)
    assert "RESUMEN" in workbook.sheetnames
    assert "ENTREGADAS" in workbook.sheetnames

    resumen = list(workbook["RESUMEN"].values)
    filas = {row[0]: row for row in resumen[1:]}
    assert filas["TOTAL"][1] == 3
    assert filas["TOTAL"][2] == 3  # unidades entregadas (1 por guia)
    assert filas["TOTAL"][3] == 60_000
    assert filas["PROMEDIO POR EMPLEADO"][1] == 1.5
    assert filas["PROMEDIO POR EMPLEADO"][2] == 1.5
    assert filas["PROMEDIO POR EMPLEADO"][3] == 30_000

    entregadas = list(workbook["ENTREGADAS"].values)
    guias = {row[2] for row in entregadas[1:]}
    assert guias == {"100", "200", "300"}


def test_entregadas_mes_une_archivo_con_zona_de_trabajo(tmp_path: Path) -> None:
    from gestor_guias.reports import entregadas_mes_dataframe

    repository = _preparar_entregadas_del_mes(tmp_path)
    hoy = hoy_colombia()
    # Las dos primeras se archivan (cierre del dia); la tercera se entrega despues.
    repository.update_tracking_fields("300", "KEVIN", "R", "")
    assert repository.archivar_entregadas() == 2
    repository.update_tracking_fields("300", "KEVIN", "E", "")

    entregadas = entregadas_mes_dataframe(repository, hoy.year, hoy.month)

    assert sorted(entregadas["GUIA"]) == ["100", "200", "300"]
    # Un mes sin entregas no trae nada.
    assert entregadas_mes_dataframe(repository, 2020, 1).empty


def test_generate_cierre_mensual_entregadas_pdf(tmp_path: Path) -> None:
    from gestor_guias.reports import generate_cierre_mensual_entregadas_pdf

    repository = _preparar_entregadas_del_mes(tmp_path)
    hoy = hoy_colombia()

    ruta = generate_cierre_mensual_entregadas_pdf(repository, tmp_path, hoy.year, hoy.month)

    assert ruta.exists()
    assert ruta.suffix == ".pdf"
    assert ruta.stat().st_size > 0


def test_build_rendimiento_mensual_y_pdfs(tmp_path: Path) -> None:
    from gestor_guias.reports import (
        build_rendimiento_mensual,
        generate_rendimiento_mensual_operador_pdf,
        generate_rendimiento_mensual_pdf,
    )

    repository = _preparar_entregadas_del_mes(tmp_path)
    hoy = hoy_colombia()
    repository.guardar_cierre(
        fecha=hoy.isoformat(), operador="OMAR", gestionadas=2, ro=0, n=0, d=0, e=2,
        recaudado=30_000, bancos=0, nequi=0, envia=0, efectivo=30_000,
        gastos=5_000, adelanto_salario=50_000,
    )

    rendimiento = build_rendimiento_mensual(repository, hoy.year, hoy.month)
    fila_omar = rendimiento[rendimiento["OPERADOR"] == "OMAR"].iloc[0]
    assert fila_omar["GUIAS GESTIONADAS"] == 2
    assert fila_omar["GUIAS ENTREGADAS"] == 2
    assert fila_omar["ADELANTO/PRESTAMO"] == 50_000
    assert fila_omar["GASTOS"] == 5_000
    assert fila_omar["PROMEDIO DEL MES"] == 2  # 2 entregas en 1 dia trabajado

    ruta_operador = generate_rendimiento_mensual_operador_pdf(
        repository, tmp_path, "OMAR", hoy.year, hoy.month
    )
    ruta_todos = generate_rendimiento_mensual_pdf(repository, tmp_path, hoy.year, hoy.month)
    assert ruta_operador.exists() and ruta_operador.stat().st_size > 0
    assert ruta_todos.exists() and ruta_todos.stat().st_size > 0


def test_entregadas_operador_excel_incluye_hoja_de_novedades(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")
    hoy = hoy_colombia()

    repository.save_consolidated(build_dataframe("100", "", "", "10000"))
    repository.asignar_salida(["100"], "KEVIN", "R")
    repository.save_consolidated(build_dataframe("200", "", "", "20000"))
    repository.asignar_salida(["200"], "KEVIN", "R")
    repository.save_consolidated(build_dataframe("300", "", "", "30000"))
    repository.asignar_salida(["300"], "KEVIN", "R")

    repository.registrar_novedad(["100"], "KEVIN", hoy.isoformat(), "RO")
    repository.registrar_devolucion([("200", "10")], "KEVIN", hoy.isoformat(), "D")
    repository.cerrar_dia_operador("KEVIN", hoy.isoformat(), "R", "E")

    ruta = generate_entregadas_operador_excel(repository, tmp_path, "KEVIN", hoy)

    workbook = load_workbook(ruta)
    assert "NOVEDADES" in workbook.sheetnames
    hoja = workbook["NOVEDADES"]
    filas = {hoja.cell(row=r, column=1).value: hoja.cell(row=r, column=2).value for r in range(2, hoja.max_row + 1)}
    assert filas == {"100": "RO", "200": "D"}
    # La causal de la devolucion queda registrada.
    fila_d = next(r for r in range(2, hoja.max_row + 1) if hoja.cell(row=r, column=1).value == "200")
    assert hoja.cell(row=fila_d, column=3).value == "10"


def test_recaudo_incluye_operadores_con_cierre_sin_guias(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "", "", "10000"))
    repository.update_tracking_fields("100", "OMAR", "E", "")

    # PARRA no gestiono guias el 10/06 pero registro gastos y adelanto en su cierre.
    repository.guardar_cierre(
        fecha="2026-06-10", operador="PARRA", gestionadas=0, ro=0, n=0, d=0, e=0,
        recaudado=0, bancos=0, nequi=0, envia=0, efectivo=0,
        gastos=15_000, adelanto_salario=50_000,
    )

    ruta = generate_recaudo_report(repository, tmp_path / "output", date(2026, 6, 10))

    hoja = load_workbook(ruta)["RECAUDO"]
    operadores = [hoja.cell(row=r, column=1).value for r in range(5, hoja.max_row + 1)]
    assert "PARRA" in operadores
    # La tabla de detalle de gastos ya no existe.
    textos = [hoja.cell(row=r, column=1).value for r in range(1, hoja.max_row + 1)]
    assert "DETALLE DE GASTOS / DESCUENTOS" not in textos
    assert "Adelantos del dia" in textos


def test_informe_diario_combina_recaudo_resumen_y_cierre_general(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")

    repository.save_consolidated(build_dataframe("100", "", "", "10000"))
    repository.update_tracking_fields("100", "OMAR", "E", "")
    repository.guardar_cierre_general(
        "2026-06-10", {100_000: 2, 50_000: 1}, 250_000
    )

    ruta = generate_recaudo_report(repository, tmp_path / "output", date(2026, 6, 10))

    assert ruta.name == "informe diario 10 junio.xlsx"
    workbook = load_workbook(ruta)
    for hoja in ("RECAUDO", "RESUMEN", "POR ESTADO", "POR MUNICIPIO", "POR OPERADOR", "DETALLE"):
        assert hoja in workbook.sheetnames

    hoja_recaudo = workbook["RECAUDO"]
    textos = [hoja_recaudo.cell(row=r, column=1).value for r in range(1, hoja_recaudo.max_row + 1)]
    assert "CIERRE GENERAL DEL DIA (EFECTIVO CONTADO)" in textos
    # El conteo guardado del cierre general aparece en la tabla.
    fila_100k = next(r for r in range(1, hoja_recaudo.max_row + 1) if hoja_recaudo.cell(row=r, column=1).value == 100_000)
    assert hoja_recaudo.cell(row=fila_100k, column=2).value == 2


# ------ Los informes del dia se arman por F_ENTREGA, no por F_INGRESO ------
# Una guia puede llegar un dia y entregarse otro. Filtrar por la fecha de
# planilla le atribuia el movimiento al dia equivocado: el informe del dia en
# que el repartidor trabajo salia vacio, y el dia de la importacion mostraba
# entregas que no eran de ese dia.


def _repo_guia_llega_un_dia_y_se_gestiona_otro(tmp_path: Path) -> GuiaRepository:
    """Tres guias importadas el mismo dia: dos entregadas el 10, una con novedad el 11."""
    repository = GuiaRepository(tmp_path / "guias.db")
    for numero in ("100", "200", "300"):
        repository.save_consolidated(
            build_dataframe_con_fecha(numero, "", "", "50000", "2026-10-01 00:00:00")
        )
    repository.asignar_salida(["100", "200", "300"], "OMAR", "R")
    repository.cerrar_dia_operador("OMAR", "2026-10-10", "R", "E")
    repository.registrar_novedad(["300"], "OMAR", "2026-10-11", "RO")
    return repository


def test_el_informe_por_operador_cuenta_el_dia_en_que_se_gestiono(tmp_path: Path) -> None:
    repository = _repo_guia_llega_un_dia_y_se_gestiona_otro(tmp_path)
    dataframe = normalize_dataframe(repository.to_dataframe())

    del_10 = build_cierre_breakdown(
        repository, filter_by_gestion(dataframe, date(2026, 10, 10)), date(2026, 10, 10), "OMAR"
    ).set_index("OPERADOR").loc["OMAR"]
    assert int(del_10["GESTIONADAS"]) == 2
    assert int(del_10["E"]) == 2
    assert int(del_10["RO"]) == 0

    del_11 = build_cierre_breakdown(
        repository, filter_by_gestion(dataframe, date(2026, 10, 11)), date(2026, 10, 11), "OMAR"
    ).set_index("OPERADOR").loc["OMAR"]
    assert int(del_11["GESTIONADAS"]) == 1
    assert int(del_11["E"]) == 0
    assert int(del_11["RO"]) == 1

    # Ninguno de los dos movimientos se le atribuye al dia de la planilla.
    del_01 = build_cierre_breakdown(
        repository, filter_by_gestion(dataframe, date(2026, 10, 1)), date(2026, 10, 1), "OMAR"
    )
    assert del_01.empty


def test_el_informe_por_operador_cuadra_con_lo_que_dice_la_operacion(tmp_path: Path) -> None:
    """El informe y el cierre del repartidor deben dar el mismo numero."""
    repository = _repo_guia_llega_un_dia_y_se_gestiona_otro(tmp_path)
    dataframe = normalize_dataframe(repository.to_dataframe())

    for dia, esperadas in (("2026-10-10", 2), ("2026-10-11", 1)):
        fecha = date.fromisoformat(dia)
        resumen = build_cierre_breakdown(
            repository, filter_by_gestion(dataframe, fecha), fecha, "OMAR"
        ).set_index("OPERADOR").loc["OMAR"]
        assert int(resumen["GESTIONADAS"]) == len(repository.guias_de_operador("OMAR", dia)) == esperadas


def test_el_informe_diario_cuenta_el_mismo_dia_que_el_de_operador(tmp_path: Path) -> None:
    repository = _repo_guia_llega_un_dia_y_se_gestiona_otro(tmp_path)

    for dia, esperadas in ((date(2026, 10, 10), 2), (date(2026, 10, 11), 1)):
        salida = generate_recaudo_report(repository, tmp_path / "output", dia)
        hoja = load_workbook(salida)["RECAUDO"]
        fila = next(fila for fila in hoja.iter_rows() if fila[0].value == "OMAR")
        assert hoja.cell(row=fila[0].row, column=2).value == esperadas


def test_una_guia_en_reparto_no_cuenta_como_gestionada(tmp_path: Path) -> None:
    """Hasta que no se entrega o se le pone novedad, no tiene F_ENTREGA."""
    repository = GuiaRepository(tmp_path / "guias.db")
    repository.save_consolidated(build_dataframe_con_fecha("100", "", "", "50000", "2026-10-01 00:00:00"))
    repository.asignar_salida(["100"], "OMAR", "R")

    dataframe = normalize_dataframe(repository.to_dataframe())
    assert dataframe.iloc[0]["F_ENTREGA"] == ""
    assert filter_by_gestion(dataframe, date(2026, 10, 1)).empty


# ---- Archivar las entregadas no debe borrarlas de los informes del dia ----
# "Cerrar el dia" mueve las E a guias_archivo. Un informe que solo mirara
# guias perdia justamente las entregas: el cierre seguia mostrando el efectivo
# recaudado, pero E y RECAUDADO salian en cero.


def _repo_dia_con_entregas_y_novedades(tmp_path: Path) -> GuiaRepository:
    """Once guias gestionadas el 10: ocho entregadas y tres con novedad."""
    repository = GuiaRepository(tmp_path / "guias.db")
    numeros = [f"{numero:03d}" for numero in range(101, 112)]
    for numero in numeros:
        repository.save_consolidated(
            build_dataframe_con_fecha(numero, "", "", "100000", "2026-10-01 00:00:00")
        )
    repository.asignar_salida(numeros, "OMAR", "R")
    repository.registrar_novedad(numeros[8:], "OMAR", "2026-10-10", "RO")
    repository.cerrar_dia_operador("OMAR", "2026-10-10", "R", "E")
    repository.guardar_cierre(
        fecha="2026-10-10", operador="OMAR", gestionadas=11, ro=3, n=0, d=0, e=8,
        recaudado=800_000, bancos=0, nequi=199_400, envia=0, efectivo=600_600,
    )
    return repository


def _cierre_del_informe(repository: GuiaRepository, tmp_path: Path) -> dict:
    """La hoja CIERRE es vertical: se lee como pares etiqueta -> valor."""
    salida = generate_operator_report(repository, tmp_path / "output", date(2026, 10, 10), "OMAR")
    hoja = load_workbook(salida)["CIERRE"]
    return {
        str(fila[0].value).strip(): fila[2].value
        for fila in hoja.iter_rows(min_row=1, max_row=hoja.max_row, max_col=3)
        if fila[0].value is not None and fila[2].value is not None
    }


def test_el_informe_del_dia_no_pierde_las_entregas_al_archivarlas(tmp_path: Path) -> None:
    repository = _repo_dia_con_entregas_y_novedades(tmp_path)

    antes = _cierre_del_informe(repository, tmp_path)
    assert (
        int(antes["GUIAS GESTIONADAS"]),
        int(antes["ENTREGADAS (E)"]),
        int(antes["RECLAMA OFICINA (RO)"]),
    ) == (11, 8, 3)
    assert int(antes["RECAUDADO"]) == 800_000

    repository.archivar_entregadas()

    despues = _cierre_del_informe(repository, tmp_path)
    assert (
        int(despues["GUIAS GESTIONADAS"]),
        int(despues["ENTREGADAS (E)"]),
        int(despues["RECLAMA OFICINA (RO)"]),
    ) == (11, 8, 3)
    assert int(despues["RECAUDADO"]) == 800_000


def test_el_efectivo_del_cierre_no_queda_sin_entregas_que_lo_expliquen(tmp_path: Path) -> None:
    """El sintoma que lo delato: efectivo recaudado con E en cero."""
    repository = _repo_dia_con_entregas_y_novedades(tmp_path)
    repository.archivar_entregadas()

    fila = _cierre_del_informe(repository, tmp_path)
    assert int(fila["EFECTIVO A ENTREGAR"]) > 0
    assert int(fila["ENTREGADAS (E)"]) > 0


def test_el_informe_diario_tampoco_pierde_las_archivadas(tmp_path: Path) -> None:
    repository = _repo_dia_con_entregas_y_novedades(tmp_path)
    repository.archivar_entregadas()

    salida = generate_recaudo_report(repository, tmp_path / "output", date(2026, 10, 10))
    hoja = load_workbook(salida)["RECAUDO"]
    fila = next(fila for fila in hoja.iter_rows() if fila[0].value == "OMAR")
    assert hoja.cell(row=fila[0].row, column=2).value == 11
    assert hoja.cell(row=fila[0].row, column=3).value == 800_000


def test_la_zona_de_trabajo_sigue_viendo_solo_las_guias_vivas(tmp_path: Path) -> None:
    """to_dataframe no cambia: el archivo solo entra en los informes."""
    repository = _repo_dia_con_entregas_y_novedades(tmp_path)
    repository.archivar_entregadas()

    assert len(repository.to_dataframe()) == 3
    assert len(repository.to_dataframe_con_archivo()) == 11


# ----------------- La hoja CIERRE es vertical y con secciones -----------------


def _hoja_cierre(tmp_path: Path):
    repository = GuiaRepository(tmp_path / "guias.db")
    numeros = [f"{numero:03d}" for numero in range(201, 204)]
    for numero in numeros:
        repository.save_consolidated(
            build_dataframe_con_fecha(numero, "", "", "100000", "2026-10-01 00:00:00")
        )
    repository.asignar_salida(numeros, "OMAR", "R")
    repository.cerrar_dia_operador("OMAR", "2026-10-10", "R", "E")
    repository.guardar_cierre(
        fecha="2026-10-10", operador="OMAR", gestionadas=3, ro=0, n=0, d=0, e=3,
        recaudado=300_000, bancos=0, nequi=50_000, envia=0, efectivo=205_000, gastos=45_000,
        denominaciones={100_000: 2, 5_000: 1},
        gastos_detalle=[
            {"concepto": "COMBUSTIBLE VAN", "valor": 30_000},
            {"concepto": "RESTAURANTE", "valor": 15_000},
        ],
    )
    salida = generate_operator_report(repository, tmp_path / "output", date(2026, 10, 10), "OMAR")
    return load_workbook(salida)["CIERRE"]


def _etiquetas(hoja) -> list[str]:
    return [
        str(fila[0].value).strip()
        for fila in hoja.iter_rows(min_row=1, max_row=hoja.max_row, max_col=1)
        if fila[0].value is not None
    ]


def test_la_hoja_cierre_va_en_vertical_con_sus_secciones(tmp_path: Path) -> None:
    etiquetas = _etiquetas(_hoja_cierre(tmp_path))

    for titulo in (
        "CIERRE DEL DIA",
        "MOVIMIENTO DEL DIA",
        "FORMAS DE PAGO Y DESCUENTOS",
        "CONTEO DE EFECTIVO EN CAJA",
    ):
        assert titulo in etiquetas

    # Las secciones van en ese orden, de arriba hacia abajo.
    assert etiquetas.index("MOVIMIENTO DEL DIA") < etiquetas.index("FORMAS DE PAGO Y DESCUENTOS")
    assert etiquetas.index("FORMAS DE PAGO Y DESCUENTOS") < etiquetas.index("CONTEO DE EFECTIVO EN CAJA")


def test_la_hoja_cierre_desglosa_los_gastos_por_concepto(tmp_path: Path) -> None:
    etiquetas = [texto.strip() for texto in _etiquetas(_hoja_cierre(tmp_path))]
    assert "COMBUSTIBLE VAN" in etiquetas
    assert "RESTAURANTE" in etiquetas


def test_la_hoja_cierre_avisa_la_diferencia_de_caja(tmp_path: Path) -> None:
    """Contado 205.000 contra 205.000 esperados: cuadra."""
    hoja = _hoja_cierre(tmp_path)
    valores = {
        str(fila[0].value).strip(): fila[2].value
        for fila in hoja.iter_rows(min_row=1, max_row=hoja.max_row, max_col=3)
        if fila[0].value is not None and fila[2].value is not None
    }
    assert valores["TOTAL CONTADO"] == 205_000
    assert valores["DIFERENCIA (CUADRA)"] == 0


def test_la_hoja_cierre_marca_cuando_la_caja_no_cuadra(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")
    repository.save_consolidated(build_dataframe_con_fecha("301", "", "", "100000", "2026-10-01 00:00:00"))
    repository.asignar_salida(["301"], "OMAR", "R")
    repository.cerrar_dia_operador("OMAR", "2026-10-10", "R", "E")
    repository.guardar_cierre(
        fecha="2026-10-10", operador="OMAR", gestionadas=1, ro=0, n=0, d=0, e=1,
        recaudado=100_000, bancos=0, nequi=0, envia=0, efectivo=100_000,
        denominaciones={50_000: 1},
    )
    salida = generate_operator_report(repository, tmp_path / "output", date(2026, 10, 10), "OMAR")
    etiquetas = _etiquetas(load_workbook(salida)["CIERRE"])
    assert "DIFERENCIA (FALTA)" in etiquetas


# --------- El cierre guardado contra las guias de hoy: avisar el desfase ------
# El cierre que firmo el repartidor queda guardado, pero el informe vuelve a
# contar las guias. Si despues del cierre se corrige una guia en la Zona de
# Trabajo, la fila del informe se contradice sola: el recaudado baja y el
# efectivo, que sale del cierre guardado, se queda como estaba. Antes eso
# pasaba en silencio.


def _repo_cerrado_el_diez(tmp_path: Path) -> GuiaRepository:
    repository = GuiaRepository(tmp_path / "guias.db")
    numeros = [f"{numero:03d}" for numero in range(401, 406)]
    for numero in numeros:
        repository.save_consolidated(
            build_dataframe_con_fecha(numero, "", "", "100000", "2026-10-01 00:00:00")
        )
    repository.asignar_salida(numeros, "OMAR", "R")
    repository.cerrar_dia_operador("OMAR", "2026-10-10", "R", "E")
    repository.guardar_cierre(
        fecha="2026-10-10", operador="OMAR", gestionadas=5, ro=0, n=0, d=0, e=5,
        recaudado=500_000, bancos=0, nequi=0, envia=0, efectivo=500_000,
        denominaciones={100_000: 5},
    )
    return repository


def _corregir_una_guia(repository: GuiaRepository) -> None:
    """El admin repara en la Zona de Trabajo: no era entregada, era devolucion."""
    repository.update_guide_details(
        "401", "1", "Persona", "", "SAN GIL", "100000", "OMAR", "D", "03"
    )


def _etiquetas_cierre(tmp_path: Path, repository: GuiaRepository) -> list[str]:
    salida = generate_operator_report(repository, tmp_path / "output", date(2026, 10, 10), "OMAR")
    hoja = load_workbook(salida)["CIERRE"]
    return [
        str(fila[0].value).strip()
        for fila in hoja.iter_rows(min_row=1, max_row=hoja.max_row, max_col=1)
        if fila[0].value is not None
    ]


def test_sin_cambios_el_informe_no_inventa_un_desfase(tmp_path: Path) -> None:
    repository = _repo_cerrado_el_diez(tmp_path)
    assert "ATENCION: EL CIERRE GUARDADO NO COINCIDE" not in _etiquetas_cierre(tmp_path, repository)


def test_corregir_una_guia_despues_de_cerrar_queda_avisado(tmp_path: Path) -> None:
    repository = _repo_cerrado_el_diez(tmp_path)
    _corregir_una_guia(repository)

    etiquetas = _etiquetas_cierre(tmp_path, repository)
    assert "ATENCION: EL CIERRE GUARDADO NO COINCIDE" in etiquetas
    # Y dice exactamente que cambio, no solo que algo cambio.
    assert "entregadas" in etiquetas
    assert "recaudado" in etiquetas


def test_el_aviso_nombra_el_valor_de_antes_y_el_de_ahora(tmp_path: Path) -> None:
    repository = _repo_cerrado_el_diez(tmp_path)
    _corregir_una_guia(repository)

    salida = generate_operator_report(repository, tmp_path / "output", date(2026, 10, 10), "OMAR")
    hoja = load_workbook(salida)["CIERRE"]
    filas = {
        str(fila[0].value).strip(): (fila[1].value, fila[2].value)
        for fila in hoja.iter_rows(min_row=1, max_row=hoja.max_row, max_col=3)
        if fila[0].value is not None
    }
    assert filas["entregadas"] == (5, 4)
    assert filas["recaudado"] == (500_000, 400_000)


def test_el_informe_diario_marca_al_operador_desfasado(tmp_path: Path) -> None:
    repository = _repo_cerrado_el_diez(tmp_path)
    _corregir_una_guia(repository)

    salida = generate_recaudo_report(repository, tmp_path / "output", date(2026, 10, 10))
    hoja = load_workbook(salida)["RECAUDO"]
    fila = next(fila for fila in hoja.iter_rows() if fila[0].value == "OMAR")
    assert "C00000" in str(fila[0].font.color.rgb)

    notas = [
        str(celda.value)
        for fila in hoja.iter_rows()
        for celda in fila
        if celda.value and "En rojo:" in str(celda.value)
    ]
    assert notas and "OMAR" in notas[0]


def test_el_informe_diario_no_marca_a_quien_esta_al_dia(tmp_path: Path) -> None:
    repository = _repo_cerrado_el_diez(tmp_path)

    salida = generate_recaudo_report(repository, tmp_path / "output", date(2026, 10, 10))
    hoja = load_workbook(salida)["RECAUDO"]
    notas = [
        celda.value
        for fila in hoja.iter_rows()
        for celda in fila
        if celda.value and "En rojo:" in str(celda.value)
    ]
    assert notas == []


def test_regenerar_el_cierre_deja_de_avisar(tmp_path: Path) -> None:
    """El remedio que propone el aviso tiene que funcionar de verdad."""
    from gestor_guias.operadores import recalcular_cierre

    repository = _repo_cerrado_el_diez(tmp_path)
    _corregir_una_guia(repository)
    assert "ATENCION: EL CIERRE GUARDADO NO COINCIDE" in _etiquetas_cierre(tmp_path, repository)

    recalcular_cierre(repository, "OMAR", "2026-10-10")

    assert "ATENCION: EL CIERRE GUARDADO NO COINCIDE" not in _etiquetas_cierre(tmp_path, repository)
