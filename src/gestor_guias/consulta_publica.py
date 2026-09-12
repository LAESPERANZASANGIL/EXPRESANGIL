from __future__ import annotations

from .operadores import ESTADO_SALIDA
from .reports import ESTADO_RECAUDO


# Estados en los que la guia sigue fisicamente en la oficina: al cliente se
# le da la direccion para que pueda acercarse.
ESTADOS_EN_OFICINA = ("RO", "D", "N")


def _datos_del_operador(operador: dict | None) -> str:
    """Nombre y celular del repartidor que lleva la guia, si se conocen."""
    if not operador:
        return ""
    nombre = " ".join(
        parte for parte in (
            str(operador.get("nombre") or "").strip(),
            str(operador.get("apellidos") or "").strip(),
        ) if parte
    )
    celular = str(operador.get("celular") or "").strip()
    if not nombre:
        return ""
    if celular:
        return f" La lleva nuestro repartidor {nombre} (celular {celular})."
    return f" La lleva nuestro repartidor {nombre}."


def _datos_de_la_oficina(oficina: dict | None) -> str:
    """Direccion y telefono de la oficina para que el cliente se acerque."""
    if not oficina:
        return ""
    direccion = str(oficina.get("direccion") or "").strip()
    telefono = str(oficina.get("telefono") or "").strip()
    if not direccion and not telefono:
        return ""

    partes = []
    if direccion:
        partes.append(f"Puede reclamarla en {direccion}")
    if telefono:
        partes.append(
            f"telefono {telefono}" if direccion else f"Comuniquese al telefono {telefono}"
        )
    return " " + ", ".join(partes) + "."


def describir_estado(
    guia: dict, operador: dict | None = None, oficina: dict | None = None
) -> str:
    """Mensaje que ve el cliente final al consultar su guia.

    Cuando la guia salio a reparto se le indica quien la lleva y a que
    celular ubicarlo; cuando sigue en la oficina, la direccion para
    reclamarla.
    """
    estado = str(guia.get("estado") or "").strip().upper()

    if estado == ESTADO_RECAUDO:
        return "Ya fue entregada."
    if estado == ESTADO_SALIDA:
        return "Se encuentra en reparto." + _datos_del_operador(operador)
    if estado == "RO":
        return "Se encuentra en la oficina." + _datos_de_la_oficina(oficina)
    if estado == "D":
        return (
            "Fue devuelta a nuestra oficina de San Gil. Comuniquese con la "
            "oficina para mas informacion." + _datos_de_la_oficina(oficina)
        )
    if estado == "N":
        return (
            "Tiene una novedad operativa. Comuniquese con nuestra oficina de "
            "San Gil." + _datos_de_la_oficina(oficina)
        )

    return "Se encuentra en la oficina." + _datos_de_la_oficina(oficina)
