from __future__ import annotations

from .operadores import ESTADO_SALIDA
from .reports import ESTADO_RECAUDO
from .repository import OPERADOR_BODEGA


def describir_estado(guia: dict) -> str:
    operador = str(guia.get("operador") or "").strip().upper()
    estado = str(guia.get("estado") or "").strip().upper()

    if estado == ESTADO_RECAUDO:
        return "Su guia ya fue entregada al destinatario."
    if estado == "D":
        return "Su guia fue devuelta a nuestra oficina de San Gil. Comuniquese con la oficina para mas informacion."
    if estado == "RO":
        return "Su guia esta en nuestra oficina de San Gil. El destinatario debe reclamarla en oficina."
    if estado == "N":
        return "Su guia tiene una novedad operativa. Comuniquese con nuestra oficina de San Gil."
    if estado == ESTADO_SALIDA and operador == OPERADOR_BODEGA:
        return "Su guia se encuentra en nuestra oficina de San Gil, pendiente de reparto."
    if estado == ESTADO_SALIDA:
        return "Su guia esta en reparto el dia de hoy."

    return "Su guia se encuentra en nuestra oficina de San Gil."
