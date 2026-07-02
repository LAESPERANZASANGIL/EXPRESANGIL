from gestor_guias.consulta_publica import describir_estado


def test_describir_estado_en_oficina() -> None:
    mensaje = describir_estado({"estado": "RO"})
    assert mensaje == "Se encuentra en la oficina."


def test_describir_estado_en_reparto() -> None:
    mensaje = describir_estado({"estado": "R"})
    assert mensaje == "Se encuentra en reparto."


def test_describir_estado_entregada() -> None:
    mensaje = describir_estado({"estado": "E"})
    assert mensaje == "Ya fue entregada."


def test_describir_estado_devuelta() -> None:
    mensaje = describir_estado({"estado": "D"})
    assert "devuelta" in mensaje


def test_describir_estado_sin_estado() -> None:
    mensaje = describir_estado({"estado": ""})
    assert mensaje == "Se encuentra en la oficina."
