from __future__ import annotations

from datetime import date
import hashlib
import os
import re
import secrets

from .excel_processor import normalize_guide
from .reports import ESTADO_RECAUDO, value_to_number
from .repository import GuiaRepository


# Estado que marca una guia como "en reparto" (salio con el operador, aun sin cerrar).
ESTADO_SALIDA = "R"

# La bodega no reparte: una salida registrada a su nombre solo cambia el
# operador y deja el estado en blanco (no entra a "en reparto").
OPERADOR_BODEGA = "BODEGA"

# Documentos de un operador con fecha de vencimiento; campo en la tabla -> etiqueta para el usuario.
DOCUMENTOS_OPERADOR = (
    ("licencia_vencimiento", "Licencia de conduccion"),
    ("soat_vencimiento", "Seguro obligatorio (SOAT)"),
    ("tecnomecanica_vencimiento", "Tecnomecanica"),
)


def documentos_vencidos(operador: dict) -> list[str]:
    hoy = date.today()
    vencidos = []
    for campo, etiqueta in DOCUMENTOS_OPERADOR:
        valor = str(operador.get(campo, "") or "").strip()
        if not valor:
            continue
        try:
            vencimiento = date.fromisoformat(valor)
        except ValueError:
            continue
        if vencimiento < hoy:
            vencidos.append(etiqueta)
    return vencidos


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
    return secrets.compare_digest(digest.hex(), digest_hex)


def parse_guides(text: str) -> list[str]:
    # Las guias escaneadas o pegadas pueden traer el cero inicial que la
    # base de datos no guarda (064108... -> 64108...), por eso se normalizan.
    return [normalize_guide(match.group(0)) for match in re.finditer(r"\d{6,}", text or "")]


def parse_guides_con_causal(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    # Cada linea de una devolucion debe traer la guia y la causal (2 digitos)
    # separados por espacio, coma o guion, ej: "064108123 10".
    items: list[tuple[str, str]] = []
    errores: list[str] = []
    for linea in (text or "").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        tokens = [token for token in re.split(r"[\s,;-]+", linea) if token]
        if len(tokens) < 2 or not re.fullmatch(r"\d{6,}", tokens[0]) or not re.fullmatch(r"\d{2}", tokens[-1]):
            errores.append(linea)
            continue
        items.append((normalize_guide(tokens[0]), tokens[-1]))
    return items, errores


def registrar_salidas(repository: GuiaRepository, operador: str, guias_texto: str) -> dict:
    guias = parse_guides(guias_texto)
    estado = "" if operador.strip().upper() == OPERADOR_BODEGA else ESTADO_SALIDA
    actualizadas, no_encontradas = repository.asignar_salida(guias, operador, estado)
    return {"recibidas": len(guias), "actualizadas": actualizadas, "no_encontradas": no_encontradas}


def registrar_novedades(
    repository: GuiaRepository,
    operador: str,
    fecha: str,
    ro_texto: str,
    n_texto: str,
    d_texto: str,
) -> dict:
    textos = {"ro": ro_texto, "n": n_texto}
    resultado = {}
    for clave, estado in (("ro", "RO"), ("n", "N")):
        guias = parse_guides(textos[clave])
        actualizadas = repository.registrar_novedad(guias, operador, fecha, ESTADO_SALIDA, estado)
        resultado[clave] = {"recibidas": len(guias), "actualizadas": actualizadas}

    items_d, errores_d = parse_guides_con_causal(d_texto)
    actualizadas_d = repository.registrar_devolucion(items_d, operador, fecha, ESTADO_SALIDA, "D")
    resultado["d"] = {"recibidas": len(items_d), "actualizadas": actualizadas_d, "errores": errores_d}
    return resultado


DENOMINACIONES = (100_000, 50_000, 20_000, 10_000, 5_000, 2_000, 1_000, 500, 200, 100, 50)


def calcular_diferencia_caja(efectivo_esperado: int, denominaciones: dict[int, int] | None) -> dict:
    efectivo_contado = sum(
        denominacion * cantidad for denominacion, cantidad in (denominaciones or {}).items()
    )
    diferencia = efectivo_esperado - efectivo_contado
    if diferencia > 0:
        nota = f"Pendiente por entregar: $ {diferencia:,.0f}".replace(",", ".")
    elif diferencia < 0:
        nota = f"Sobrante en caja: $ {abs(diferencia):,.0f}".replace(",", ".")
    else:
        nota = ""
    return {"efectivo_contado": efectivo_contado, "diferencia": diferencia, "nota": nota}


def _contar_guias_operador(guias: list[dict]) -> tuple[dict[str, int], int]:
    conteos = {"RO": 0, "N": 0, "D": 0, ESTADO_RECAUDO: 0}
    recaudado = 0
    for guia in guias:
        estado = (guia["estado"] or "").strip().upper()
        if estado in conteos:
            conteos[estado] += 1
        if estado == ESTADO_RECAUDO:
            recaudado += value_to_number(guia["valor"])
    return conteos, recaudado


def cerrar_dia(
    repository: GuiaRepository,
    operador: str,
    fecha: str,
    bancos: int,
    nequi: int,
    envia: int,
    denominaciones: dict[int, int] | None = None,
    gastos: int = 0,
    adelanto_salario: int = 0,
) -> dict:
    repository.cerrar_dia_operador(operador, fecha, ESTADO_SALIDA, ESTADO_RECAUDO)

    guias = repository.guias_de_operador(operador, fecha)
    conteos, recaudado = _contar_guias_operador(guias)

    gestionadas = len(guias)
    efectivo = recaudado - (bancos + nequi + envia + gastos + adelanto_salario)

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
        gastos=gastos,
        adelanto_salario=adelanto_salario,
    )

    caja = calcular_diferencia_caja(efectivo, denominaciones)

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
        "gastos": gastos,
        "adelanto_salario": adelanto_salario,
        "efectivo": efectivo,
        "efectivo_contado": caja["efectivo_contado"],
        "diferencia": caja["diferencia"],
        "nota": caja["nota"],
    }


def recalcular_cierre(repository: GuiaRepository, operador: str, fecha: str) -> dict:
    """Vuelve a calcular un cierre ya guardado con el estado actual de las guias.

    Util cuando a un operador le asignan o le entregan mas guias despues de
    haber cerrado el dia, dejando su cierre guardado desactualizado.
    """
    cierre_anterior = repository.obtener_cierre(fecha, operador)
    bancos = cierre_anterior["bancos"] if cierre_anterior else 0
    nequi = cierre_anterior["nequi"] if cierre_anterior else 0
    envia = cierre_anterior["envia"] if cierre_anterior else 0
    gastos = cierre_anterior["gastos"] if cierre_anterior else 0
    adelanto_salario = cierre_anterior["adelanto_salario"] if cierre_anterior else 0

    guias = repository.guias_de_operador(operador, fecha)
    conteos, recaudado = _contar_guias_operador(guias)

    gestionadas = len(guias)
    efectivo = recaudado - (bancos + nequi + envia + gastos + adelanto_salario)

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
        gastos=gastos,
        adelanto_salario=adelanto_salario,
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
        "gastos": gastos,
        "adelanto_salario": adelanto_salario,
        "efectivo": efectivo,
    }
