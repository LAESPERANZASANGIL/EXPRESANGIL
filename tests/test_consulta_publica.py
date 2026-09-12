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


OFICINA = {
    "nombre": "SAN GIL",
    "direccion": "Calle 10 # 9-50, San Gil",
    "telefono": "300 111 2233",
}
REPARTIDOR = {"nombre": "PIPE", "apellidos": "GOMEZ", "celular": "300 444 5566"}


def test_en_reparto_informa_quien_lleva_la_guia_y_su_celular() -> None:
    mensaje = describir_estado({"estado": "R"}, operador=REPARTIDOR, oficina=OFICINA)

    assert mensaje == (
        "Se encuentra en reparto. La lleva nuestro repartidor PIPE GOMEZ "
        "(celular 300 444 5566)."
    )


def test_en_reparto_sin_celular_solo_da_el_nombre() -> None:
    mensaje = describir_estado(
        {"estado": "R"}, operador={"nombre": "PIPE", "apellidos": "", "celular": ""}
    )

    assert mensaje == "Se encuentra en reparto. La lleva nuestro repartidor PIPE."


def test_en_reparto_sin_datos_del_operador_no_agrega_nada() -> None:
    assert describir_estado({"estado": "R"}) == "Se encuentra en reparto."


def test_en_la_oficina_da_la_direccion_para_reclamarla() -> None:
    mensaje = describir_estado({"estado": "RO"}, oficina=OFICINA)

    assert mensaje == (
        "Se encuentra en la oficina. Puede reclamarla en Calle 10 # 9-50, San Gil, "
        "telefono 300 111 2233."
    )


def test_devuelta_y_novedad_tambien_dan_la_direccion() -> None:
    for estado in ("D", "N"):
        mensaje = describir_estado({"estado": estado}, oficina=OFICINA)
        assert "Calle 10 # 9-50, San Gil" in mensaje


def test_guia_sin_estado_da_la_direccion_de_la_oficina() -> None:
    mensaje = describir_estado({"estado": ""}, oficina=OFICINA)
    assert mensaje.startswith("Se encuentra en la oficina.")
    assert "Calle 10 # 9-50, San Gil" in mensaje


def test_entregada_no_da_direccion_ni_repartidor() -> None:
    mensaje = describir_estado({"estado": "E"}, operador=REPARTIDOR, oficina=OFICINA)
    assert mensaje == "Ya fue entregada."


def test_oficina_sin_direccion_configurada_no_rompe_el_mensaje() -> None:
    mensaje = describir_estado({"estado": "RO"}, oficina={"direccion": "", "telefono": ""})
    assert mensaje == "Se encuentra en la oficina."
