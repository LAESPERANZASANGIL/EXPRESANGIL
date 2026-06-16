from __future__ import annotations

import hashlib
import os
import re

from .excel_processor import normalize_guide
from .reports import ESTADO_RECAUDO, value_to_number
from .repository import GuiaRepository


# Estado que marca una guia como "en reparto" (salio con el operador, aun sin cerrar).
ESTADO_SALIDA = "R"

# Codigos de novedad capturados al cierre del dia.
NOVEDADES = (("ro", "RO"), ("n", "N"), ("d", "D"))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False

    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return digest.hex() == digest_hex


def parse_guides(text: str) -> list[str]:
    # Las guias escaneadas o pegadas pueden traer el cero inicial que la
    # base de datos no guarda (064108... -> 64108...), por eso se normalizan.
    return [normalize_guide(match.group(0)) for match in re.finditer(r"\d{6,}", text or "")]


def registrar_salidas(repository: GuiaRepository, operador: str, guias_texto: str) -> dict:
    guias = parse_guides(guias_texto)
    actualizadas = repository.asignar_salida(guias, operador, ESTADO_SALIDA)
    return {"recibidas": len(guias), "actualizadas": actualizadas}


def registrar_novedades(
    repository: GuiaRepository,
    operador: str,
    fecha: str,
    ro_texto: str,
    n_texto: str,
    d_texto: str,
) -> dict:
    textos = {"ro": ro_texto, "n": n_texto, "d": d_texto}
    resultado = {}
    for clave, estado in NOVEDADES:
        guias = parse_guides(textos[clave])
        actualizadas = repository.registrar_novedad(guias, operador, fecha, ESTADO_SALIDA, estado)
        resultado[clave] = {"recibidas": len(guias), "actualizadas": actualizadas}
    return resultado


def cerrar_dia(
    repository: GuiaRepository,
    operador: str,
    fecha: str,
    bancos: int,
    nequi: int,
    envia: int,
) -> dict:
    repository.cerrar_dia_operador(operador, fecha, ESTADO_SALIDA, ESTADO_RECAUDO)

    guias = repository.guias_de_operador(operador, fecha)
    conteos = {"RO": 0, "N": 0, "D": 0, ESTADO_RECAUDO: 0}
    recaudado = 0
    for guia in guias:
        estado = (guia["estado"] or "").strip().upper()
        if estado in conteos:
            conteos[estado] += 1
        if estado == ESTADO_RECAUDO:
            recaudado += value_to_number(guia["valor"])

    gestionadas = len(guias)
    efectivo = recaudado - (bancos + nequi + envia)

    repository.guardar_cierre(
        fecha=fecha,
        operador=operador,
        gestionadas=gestionadas,
        ro=conteos["RO"],
        n=conteos["N"],
        d=conteos["D"],
        e=conteos[ESTADO_RECAUDO],
        recaudado=recaudado,
        bancos=bancos,
        nequi=nequi,
        envia=envia,
        efectivo=efectivo,
    )

    return {
        "gestionadas": gestionadas,
        "ro": conteos["RO"],
        "n": conteos["N"],
        "d": conteos["D"],
        "e": conteos[ESTADO_RECAUDO],
        "recaudado": recaudado,
        "bancos": bancos,
        "nequi": nequi,
        "envia": envia,
        "efectivo": efectivo,
    }
