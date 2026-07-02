from __future__ import annotations

from .operadores import ESTADO_SALIDA
from .reports import ESTADO_RECAUDO


def describir_estado(guia: dict) -> str:
    estado = str(guia.get("estado") or "").strip().upper()

    if estado == ESTADO_RECAUDO:
        return "Ya fue entregada."
    if estado == "RO":
        return "Se encuentra en la oficina."
    if estado == ESTADO_SALIDA:
        return "Se encuentra en reparto."
    if estado == "D":
        return "Fue devuelta a nuestra oficina de San Gil. Comuniquese con la oficina para mas informacion."
    if estado == "N":
        return "Tiene una novedad operativa. Comuniquese con nuestra oficina de San Gil."

    return "Se encuentra en la oficina."
