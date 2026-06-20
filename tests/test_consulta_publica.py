from gestor_guias.consulta_publica import describir_estado


def test_describir_estado_en_bodega() -> None:
    mensaje = describir_estado({"operador": "BODEGA", "estado": "R"})
    assert "San Gil" in mensaje
    assert "pendiente de reparto" in mensaje


def test_describir_estado_en_reparto() -> None:
    mensaje = describir_estado({"operador": "KEVIN", "estado": "R"})
    assert "reparto" in mensaje


def test_describir_estado_entregada() -> None:
    mensaje = describir_estado({"operador": "KEVIN", "estado": "E"})
    assert "entregada" in mensaje


def test_describir_estado_devuelta() -> None:
    mensaje = describir_estado({"operador": "KEVIN", "estado": "D"})
    assert "devuelta" in mensaje


def test_describir_estado_reclamar_oficina() -> None:
    mensaje = describir_estado({"operador": "KEVIN", "estado": "RO"})
    assert "reclamarla" in mensaje
