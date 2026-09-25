"""Libro de caja de la oficina.

Es un libro de **caja**: cuenta la plata que entra y sale de la oficina.
Todo se digita, salvo lo que ya vive en otra parte y se trae solo para no
teclearlo dos veces: la nomina, los gastos del cierre abiertos por concepto,
y los prestamos y adelantos entregados.

Lo unico que no entra es el **recaudo**: no es plata de la oficina, es del
cliente y se le entrega a Envia.
"""

from pathlib import Path

import pytest

from gestor_guias.repository import GuiaRepository


@pytest.fixture
def repositorio(tmp_path: Path) -> GuiaRepository:
    return GuiaRepository(tmp_path / "guias.db")


def _nomina(repositorio: GuiaRepository, periodo: str, total: int) -> None:
    repositorio.guardar_nomina(
        periodo,
        "PIPE",
        {
            "salario_base": total,
            "dias_trabajados": 30,
            "auxilio_transporte": 0,
            "bonificaciones": 0,
            "salud": 0,
            "pension": 0,
            "descuento_prestamos": 0,
            "otros_descuentos": 0,
            "total_pagar": total,
        },
    )


def _cierre(repositorio: GuiaRepository, fecha: str, gastos: int, adelanto: int = 0) -> None:
    repositorio.guardar_cierre(
        fecha=fecha, operador="PIPE", gestionadas=1, ro=0, n=0, d=0, e=1,
        recaudado=500000, bancos=0, nequi=0, envia=0, efectivo=500000,
        gastos=gastos, adelanto_salario=adelanto,
    )


# ------------------------------ Registro ---------------------------------

def test_registrar_y_listar(repositorio: GuiaRepository) -> None:
    repositorio.crear_movimiento({
        "tipo": "EGRESO", "fecha": "2026-09-03", "categoria": "arriendo",
        "descripcion": "Arriendo del local", "valor": 800000, "forma_pago": "transferencia",
    })

    movimientos = repositorio.listar_movimientos(2026, 9)

    assert len(movimientos) == 1
    # Categoria y forma de pago se normalizan a mayusculas para que el
    # desglose no separe "arriendo" de "ARRIENDO".
    assert movimientos[0]["categoria"] == "ARRIENDO"
    assert movimientos[0]["forma_pago"] == "TRANSFERENCIA"
    assert movimientos[0]["valor"] == 800000


def test_solo_muestra_el_mes_consultado(repositorio: GuiaRepository) -> None:
    for fecha in ("2026-08-31", "2026-09-01", "2026-10-01"):
        repositorio.crear_movimiento({
            "tipo": "EGRESO", "fecha": fecha, "categoria": "X", "valor": 1000,
        })

    assert len(repositorio.listar_movimientos(2026, 9)) == 1


def test_un_tipo_invalido_se_rechaza(repositorio: GuiaRepository) -> None:
    with pytest.raises(ValueError, match="INGRESO o EGRESO"):
        repositorio.crear_movimiento({"tipo": "OTRO", "fecha": "2026-09-03", "valor": 1000})


def test_un_valor_en_cero_o_negativo_se_rechaza(repositorio: GuiaRepository) -> None:
    for valor in (0, -500):
        with pytest.raises(ValueError, match="mayor que cero"):
            repositorio.crear_movimiento(
                {"tipo": "EGRESO", "fecha": "2026-09-03", "valor": valor}
            )


def test_sin_fecha_se_rechaza(repositorio: GuiaRepository) -> None:
    with pytest.raises(ValueError, match="fecha"):
        repositorio.crear_movimiento({"tipo": "EGRESO", "fecha": "", "valor": 1000})


def test_eliminar_un_movimiento(repositorio: GuiaRepository) -> None:
    identificador = repositorio.crear_movimiento(
        {"tipo": "EGRESO", "fecha": "2026-09-03", "categoria": "X", "valor": 1000}
    )

    assert repositorio.eliminar_movimiento(identificador) is True
    assert repositorio.listar_movimientos(2026, 9) == []
    assert repositorio.eliminar_movimiento(identificador) is False


# --------------------------- Egresos automaticos --------------------------

def test_la_nomina_y_los_gastos_entran_solos(repositorio: GuiaRepository) -> None:
    _nomina(repositorio, "2026-09", 1396000)
    _cierre(repositorio, "2026-09-10", gastos=45000)

    automaticos = {m["categoria"]: m["valor"] for m in repositorio.egresos_automaticos_mes(2026, 9)}

    # Sin detalle (cierre viejo) el gasto sigue sumando, agrupado aparte.
    assert automaticos == {"NOMINA": 1396000, "GASTOS SIN DETALLE": 45000}


def test_los_gastos_entran_abiertos_por_concepto(repositorio: GuiaRepository) -> None:
    """De nada sirve saber que se fueron 70.000 si no se sabe en que."""
    repositorio.guardar_cierre(
        fecha="2026-09-10", operador="PIPE", gestionadas=1, ro=0, n=0, d=0, e=1,
        recaudado=500000, bancos=0, nequi=0, envia=0, efectivo=430000,
        gastos=70000, adelanto_salario=0,
        gastos_detalle=[
            {"concepto": "COMBUSTIBLE VAN", "valor": 50000},
            {"concepto": "CAMBIO DE ACEITE", "valor": 20000},
        ],
    )

    automaticos = {m["categoria"]: m["valor"] for m in repositorio.egresos_automaticos_mes(2026, 9)}

    assert automaticos == {"COMBUSTIBLE VAN": 50000, "CAMBIO DE ACEITE": 20000}


def test_los_gastos_del_mismo_concepto_se_agrupan(repositorio: GuiaRepository) -> None:
    for fecha in ("2026-09-10", "2026-09-11"):
        repositorio.guardar_cierre(
            fecha=fecha, operador="PIPE", gestionadas=1, ro=0, n=0, d=0, e=1,
            recaudado=500000, bancos=0, nequi=0, envia=0, efectivo=450000,
            gastos=50000, adelanto_salario=0,
            gastos_detalle=[{"concepto": "COMBUSTIBLE VAN", "valor": 50000}],
        )

    automaticos = {m["categoria"]: m["valor"] for m in repositorio.egresos_automaticos_mes(2026, 9)}

    assert automaticos == {"COMBUSTIBLE VAN": 100000}


def test_los_adelantos_y_prestamos_si_son_egreso_de_caja(
    repositorio: GuiaRepository,
) -> None:
    """Es un libro de caja: esa plata salio de la oficina.

    No se cuenta dos veces porque la nomina llega **neta** del descuento:
    lo que se le presto al empleado baja su nomina por el mismo valor.
    """
    _cierre(repositorio, "2026-09-10", gastos=45000, adelanto=100000)
    repositorio.crear_prestamo(
        empleado="PIPE", tipo="PRESTAMO", monto=500000, fecha="2026-09-02", cuotas=5
    )

    automaticos = {m["categoria"]: m["valor"] for m in repositorio.egresos_automaticos_mes(2026, 9)}

    assert automaticos["ADELANTOS DEL CIERRE"] == 100000
    assert automaticos["PRESTAMOS ENTREGADOS"] == 500000


def test_un_prestamo_anulado_no_cuenta_como_egreso(repositorio: GuiaRepository) -> None:
    prestamo = repositorio.crear_prestamo(
        empleado="PIPE", tipo="PRESTAMO", monto=500000, fecha="2026-09-02", cuotas=5
    )
    repositorio.anular_prestamo(prestamo)

    assert repositorio.egresos_automaticos_mes(2026, 9) == []


def test_el_recaudo_no_es_ingreso_de_la_oficina(repositorio: GuiaRepository) -> None:
    """Es plata del cliente que se le entrega a Envia; la comision se digita."""
    _cierre(repositorio, "2026-09-10", gastos=0)

    resumen = repositorio.resumen_ingresos_egresos(2026, 9)

    assert resumen["ingresos"] == 0


def test_los_automaticos_no_se_guardan_en_la_tabla(repositorio: GuiaRepository) -> None:
    """Su fuente de verdad sigue siendo la nomina y el cierre del operador."""
    _nomina(repositorio, "2026-09", 1396000)
    _cierre(repositorio, "2026-09-10", gastos=45000)

    repositorio.resumen_ingresos_egresos(2026, 9)

    assert repositorio.listar_movimientos(2026, 9) == []


def test_sin_nomina_ni_gastos_no_inventa_filas(repositorio: GuiaRepository) -> None:
    assert repositorio.egresos_automaticos_mes(2026, 9) == []


# -------------------------------- Resumen ---------------------------------

def test_el_resumen_suma_lo_digitado_y_lo_automatico(repositorio: GuiaRepository) -> None:
    _nomina(repositorio, "2026-09", 1396000)
    _cierre(repositorio, "2026-09-10", gastos=45000, adelanto=100000)
    repositorio.crear_movimiento({
        "tipo": "INGRESO", "fecha": "2026-09-05", "categoria": "COMISION", "valor": 2500000,
    })
    repositorio.crear_movimiento({
        "tipo": "EGRESO", "fecha": "2026-09-03", "categoria": "ARRIENDO", "valor": 800000,
    })

    resumen = repositorio.resumen_ingresos_egresos(2026, 9)

    #              nomina    gastos   adelanto   arriendo (digitado)
    egresos = 1396000 + 45000 + 100000 + 800000
    assert resumen["ingresos"] == 2500000
    assert resumen["egresos"] == egresos
    assert resumen["saldo"] == 2500000 - egresos
    # Nomina, gastos y adelanto vienen solos; el arriendo se digito.
    assert [m["automatico"] for m in resumen["movimientos"]].count(True) == 3


def test_el_desglose_por_categoria_agrupa(repositorio: GuiaRepository) -> None:
    for valor in (800000, 200000):
        repositorio.crear_movimiento({
            "tipo": "EGRESO", "fecha": "2026-09-03", "categoria": "ARRIENDO", "valor": valor,
        })

    por_categoria = repositorio.resumen_ingresos_egresos(2026, 9)["por_categoria"]

    assert por_categoria["ARRIENDO"]["EGRESO"] == 1000000


def test_el_saldo_puede_ser_negativo(repositorio: GuiaRepository) -> None:
    """Si se gasta mas de lo que entra, el informe debe decirlo."""
    _nomina(repositorio, "2026-09", 1396000)

    assert repositorio.resumen_ingresos_egresos(2026, 9)["saldo"] == -1396000
