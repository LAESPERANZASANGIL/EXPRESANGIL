"""Copia del respaldo fuera del servidor, mediante un comando configurable.

Los respaldos automaticos viven en el disco del VPS: si ese disco falla se
pierden todos a la vez. Este modulo genera una copia verificada y se la
entrega al comando que el administrador configure en `settings.toml`.

Se dejo como comando y no como integracion con un proveedor concreto para
no depender de registrar la aplicacion en Google Cloud o en Azure, y para
que cambiar de destino no exija tocar el codigo. Con `rclone` cubre
OneDrive, Drive o S3; con `scp`, otro servidor.

    [respaldo_externo]
    activo = true
    comando = "rclone copy {archivo} onedrive:Respaldos Expresangil"
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shlex
import subprocess
import tempfile

# Si el destino no responde en este tiempo se corta: el hilo de respaldo no
# puede quedarse colgado esperando a la red.
TIEMPO_LIMITE_SEGUNDOS = 15 * 60


def construir_comando(plantilla: str, archivo: Path) -> list[str]:
    """Parte la plantilla en argumentos y le pone la ruta del respaldo.

    Se parte con `shlex` y se ejecuta sin `shell=True`: el nombre del
    archivo lleva espacios y asi no hay que preocuparse por el escapado.
    """
    plantilla = str(plantilla or "").strip()
    if not plantilla:
        raise ValueError("No hay comando configurado en [respaldo_externo].")
    if "{archivo}" not in plantilla:
        raise ValueError(
            "El comando de [respaldo_externo] debe incluir {archivo}, "
            "que se reemplaza por la ruta del respaldo."
        )
    return [parte.replace("{archivo}", str(archivo)) for parte in shlex.split(plantilla)]


def copiar_fuera(repositorio, comando: str) -> dict:
    """Genera el respaldo y lo entrega al comando configurado.

    Devuelve el nombre y el tamaño de lo enviado. Lanza si la base esta
    danada o si el comando falla: un respaldo que no llego a su destino no
    debe reportarse como exitoso.
    """
    marca = datetime.now().strftime("%Y-%m-%d %H%M")
    nombre = f"respaldo expresangil {marca}.db"

    with tempfile.TemporaryDirectory() as temporal:
        archivo = Path(temporal) / nombre
        # Copia verificada: si la base esta danada esto lanza y no se manda
        # afuera un respaldo inutil.
        repositorio.copia_para_descarga(archivo)
        tamano = archivo.stat().st_size

        proceso = subprocess.run(
            construir_comando(comando, archivo),
            capture_output=True,
            text=True,
            timeout=TIEMPO_LIMITE_SEGUNDOS,
        )

    if proceso.returncode != 0:
        detalle = (proceso.stderr or proceso.stdout or "").strip()
        raise RuntimeError(f"El comando fallo (codigo {proceso.returncode}): {detalle}")

    return {"nombre": nombre, "tamano": tamano, "salida": (proceso.stdout or "").strip()}
