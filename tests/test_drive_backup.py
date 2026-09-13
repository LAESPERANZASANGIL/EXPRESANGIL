"""Pruebas de la subida del respaldo a Google Drive.

No tocan la red: se simula el servicio de Drive para comprobar la logica
propia (buscar o crear la carpeta, subir y rotar).
"""

from pathlib import Path

import pytest

from gestor_guias.drive_backup import CARPETA_MIME, RespaldoDrive
from gestor_guias.repository import GuiaRepository

import test_repository as ayudas


class _Peticion:
    def __init__(self, resultado):
        self._resultado = resultado

    def execute(self):
        return self._resultado


class ArchivosFalsos:
    """Imita `servicio.files()` de la API de Drive."""

    def __init__(self, existentes=None):
        self.existentes = list(existentes or [])
        self.creados = []
        self.borrados = []

    def list(self, **kwargs):
        consulta = kwargs.get("q", "")
        if CARPETA_MIME in consulta:
            return _Peticion({"files": [f for f in self.existentes if f.get("es_carpeta")]})
        return _Peticion({"files": [f for f in self.existentes if not f.get("es_carpeta")]})

    def create(self, **kwargs):
        cuerpo = kwargs.get("body", {})
        self.creados.append(cuerpo)
        return _Peticion({"id": f"id-{len(self.creados)}"})

    def delete(self, fileId):  # noqa: N803 - nombre de la API de Google
        self.borrados.append(fileId)
        return _Peticion({})


class ServicioFalso:
    def __init__(self, archivos):
        self._archivos = archivos

    def files(self):
        return self._archivos


@pytest.fixture
def repositorio(tmp_path: Path) -> GuiaRepository:
    repository = GuiaRepository(tmp_path / "guias.db")
    repository.save_consolidated(ayudas.build_dataframe("100", "Cliente"))
    return repository


def _subida(tmp_path: Path, archivos: ArchivosFalsos, copias: int = 30) -> RespaldoDrive:
    subida = RespaldoDrive(
        credentials_file=tmp_path / "credentials.json",
        token_file=tmp_path / "token.json",
        carpeta="WILLIANS, Institucion Educativa La Esperanza",
        copias=copias,
    )
    subida._servicio = lambda: ServicioFalso(archivos)  # type: ignore[method-assign]
    return subida


def test_crea_la_carpeta_si_no_existe(tmp_path: Path, repositorio: GuiaRepository) -> None:
    archivos = ArchivosFalsos()

    resultado = _subida(tmp_path, archivos).subir(repositorio)

    carpeta, respaldo = archivos.creados
    assert carpeta["mimeType"] == CARPETA_MIME
    assert carpeta["name"] == "WILLIANS, Institucion Educativa La Esperanza"
    assert respaldo["name"] == resultado["nombre"]
    assert resultado["tamano"] > 0


def test_reusa_la_carpeta_existente(tmp_path: Path, repositorio: GuiaRepository) -> None:
    archivos = ArchivosFalsos([{"id": "carpeta-1", "name": "X", "es_carpeta": True}])

    _subida(tmp_path, archivos).subir(repositorio)

    assert [c["name"] for c in archivos.creados if c.get("mimeType") == CARPETA_MIME] == []
    assert archivos.creados[0]["parents"] == ["carpeta-1"]


def test_rota_las_copias_viejas(tmp_path: Path, repositorio: GuiaRepository) -> None:
    """Drive tampoco es infinito: solo se conservan las mas recientes."""
    viejos = [{"id": f"v{i}", "name": f"respaldo {i}.db"} for i in range(5)]
    archivos = ArchivosFalsos([{"id": "c", "es_carpeta": True}, *viejos])

    resultado = _subida(tmp_path, archivos, copias=3).subir(repositorio)

    assert resultado["borradas"] == 2
    assert archivos.borrados == ["v3", "v4"]


def test_no_sube_si_la_base_esta_danada(tmp_path: Path) -> None:
    """Subir un respaldo danado seria peor que no subir nada."""
    repository = GuiaRepository(tmp_path / "guias.db")
    repository.initialize()
    (tmp_path / "guias.db").write_bytes(b"esto no es una base de datos")
    archivos = ArchivosFalsos()

    with pytest.raises(Exception):
        _subida(tmp_path, archivos).subir(repository)

    assert not [c for c in archivos.creados if "parents" in c]


def test_sin_token_pide_autorizar_primero(tmp_path: Path) -> None:
    subida = RespaldoDrive(
        credentials_file=tmp_path / "credentials.json",
        token_file=tmp_path / "no_existe.json",
        carpeta="X",
    )

    with pytest.raises(FileNotFoundError, match="Autoriza primero"):
        subida._credenciales()
