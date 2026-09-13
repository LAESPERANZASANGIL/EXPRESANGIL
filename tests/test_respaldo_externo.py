"""Pruebas de la copia del respaldo fuera del servidor.

No hay red ni proveedor de por medio: el comando configurado se sustituye
por `cp`, que es lo que en produccion hace `rclone` o `scp`.
"""

from pathlib import Path

import pytest

from gestor_guias.repository import GuiaRepository
from gestor_guias.respaldo_externo import construir_comando, copiar_fuera

import test_repository as ayudas


@pytest.fixture
def repositorio(tmp_path: Path) -> GuiaRepository:
    repository = GuiaRepository(tmp_path / "guias.db")
    repository.save_consolidated(ayudas.build_dataframe("100", "Cliente"))
    return repository


def test_el_respaldo_llega_al_destino(tmp_path: Path, repositorio: GuiaRepository) -> None:
    destino = tmp_path / "afuera"
    destino.mkdir()

    resultado = copiar_fuera(repositorio, f"cp {{archivo}} {destino}")

    copiado = destino / resultado["nombre"]
    assert copiado.is_file()
    assert copiado.stat().st_size == resultado["tamano"]
    # Y lo que llego es una base utilizable, no un archivo a medias.
    assert GuiaRepository(copiado).to_dataframe()["GUIA"].tolist() == ["100"]


def test_un_comando_que_falla_no_se_reporta_como_exito(
    tmp_path: Path, repositorio: GuiaRepository
) -> None:
    """Un respaldo que no llego a su destino no protege de nada."""
    with pytest.raises(RuntimeError, match="El comando fallo"):
        copiar_fuera(repositorio, "cp {archivo} /no/existe/esta/ruta/")


def test_no_manda_una_base_danada(tmp_path: Path) -> None:
    repository = GuiaRepository(tmp_path / "guias.db")
    repository.initialize()
    (tmp_path / "guias.db").write_bytes(b"esto no es una base de datos")
    destino = tmp_path / "afuera"
    destino.mkdir()

    with pytest.raises(Exception):
        copiar_fuera(repository, f"cp {{archivo}} {destino}")

    assert list(destino.iterdir()) == []


def test_la_ruta_con_espacios_viaja_como_un_solo_argumento() -> None:
    """El nombre del respaldo lleva espacios; no debe partirse en dos."""
    partes = construir_comando(
        "rclone copy {archivo} onedrive:Respaldos", Path("/tmp/respaldo expresangil 01.db")
    )

    assert partes == [
        "rclone", "copy", "/tmp/respaldo expresangil 01.db", "onedrive:Respaldos",
    ]


def test_exige_el_marcador_del_archivo() -> None:
    with pytest.raises(ValueError, match=r"\{archivo\}"):
        construir_comando("rclone copy onedrive:Respaldos", Path("/tmp/x.db"))


def test_sin_comando_avisa() -> None:
    with pytest.raises(ValueError, match="No hay comando configurado"):
        construir_comando("   ", Path("/tmp/x.db"))
