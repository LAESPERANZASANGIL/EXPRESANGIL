"""Libro de caja de la oficina.

Regla del negocio: **todo se digita**, salvo dos egresos que ya viven en la
base y se traen solos —la nomina liquidada y los gastos que los repartidores
reportan en su cierre— para no teclearlos dos veces.
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

    assert automaticos == {"NOMINA": 1396000, "GASTOS": 45000}


def test_los_adelantos_no_son_egreso(repositorio: GuiaRepository) -> None:
    """El adelanto vuelve y ya se descuenta de la nomina: contarlo seria restar dos veces."""
    _cierre(repositorio, "2026-09-10", gastos=45000, adelanto=100000)

    automaticos = repositorio.egresos_automaticos_mes(2026, 9)

    assert [m["categoria"] for m in automaticos] == ["GASTOS"]
    assert sum(m["valor"] for m in automaticos) == 45000


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

    assert resumen["ingresos"] == 2500000
    assert resumen["egresos"] == 1396000 + 45000 + 800000
    assert resumen["saldo"] == 2500000 - 2241000
    assert [m["automatico"] for m in resumen["movimientos"]].count(True) == 2


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
