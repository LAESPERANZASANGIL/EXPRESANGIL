"""La sesion debe sobrevivir a un reinicio del servidor.

Es el punto de todo el cambio: antes las sesiones vivian en memoria y cada
despliegue —o cada reinicio inesperado del VPS— expulsaba a todo el mundo a
mitad de la jornada. Aqui se levanta el panel de verdad, se inicia sesion,
se mata el servidor y se comprueba contra uno nuevo.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
import json
import threading
import urllib.error
import urllib.request

import pytest

from gestor_guias.operadores import hash_password
from gestor_guias.repository import GuiaRepository

import gestor_guias.launcher_server as ls


@pytest.fixture
def base(tmp_path: Path) -> Path:
    return tmp_path / "guias.db"


def _levantar(base: Path, puerto: int):
    """Panel escuchando en `puerto`, apuntando a `base`."""
    ls.REPOSITORY = GuiaRepository(base)
    servidor = ThreadingHTTPServer(("127.0.0.1", puerto), ls.LauncherHandler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return servidor


def _pedir(puerto: int, ruta: str, cookie: str = "", cuerpo: dict | None = None):
    peticion = urllib.request.Request(
        f"http://127.0.0.1:{puerto}{ruta}",
        data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
        headers={"Content-Type": "application/json"},
    )
    if cookie:
        peticion.add_header("Cookie", f"session={cookie}")
    with urllib.request.urlopen(peticion) as respuesta:
        return json.loads(respuesta.read()), respuesta.headers


def _iniciar_sesion(base: Path, puerto: int) -> str:
    """Crea el admin, entra y devuelve la cookie de sesion."""
    GuiaRepository(base).crear_operador("adm", hash_password("clave"), "ADMIN", rol="admin")
    _, cabeceras = _pedir(puerto, "/api/operador/login", cuerpo={"usuario": "adm", "password": "clave"})
    galleta = cabeceras["Set-Cookie"]
    return galleta.split("session=", 1)[1].split(";", 1)[0]


def test_la_sesion_sobrevive_al_reinicio_del_servidor(base: Path) -> None:
    servidor = _levantar(base, 8861)
    try:
        cookie = _iniciar_sesion(base, 8861)
        antes, _ = _pedir(8861, "/api/operador/sesion", cookie)
        assert antes["usuario"] == "adm"
    finally:
        servidor.shutdown()
        servidor.server_close()

    # Servidor nuevo: no conserva nada en memoria de la ejecucion anterior.
    servidor = _levantar(base, 8862)
    try:
        despues, _ = _pedir(8862, "/api/operador/sesion", cookie)
    finally:
        servidor.shutdown()
        servidor.server_close()

    assert despues["usuario"] == "adm"
    assert despues["rol"] == "admin"


def test_la_cookie_no_se_guarda_tal_cual(base: Path) -> None:
    """Los respaldos salen del servidor: una copia no puede dar sesiones vivas."""
    servidor = _levantar(base, 8863)
    try:
        cookie = _iniciar_sesion(base, 8863)
    finally:
        servidor.shutdown()
        servidor.server_close()

    repositorio = GuiaRepository(base)
    ahora = ls._ahora()
    assert repositorio.obtener_sesion(cookie, ahora) is None
    assert repositorio.obtener_sesion(ls._hash_token(cookie), ahora)["usuario"] == "adm"


def test_cerrar_sesion_la_invalida_de_verdad(base: Path) -> None:
    servidor = _levantar(base, 8864)
    try:
        cookie = _iniciar_sesion(base, 8864)
        _pedir(8864, "/api/operador/logout", cookie, cuerpo={})

        with pytest.raises(urllib.error.HTTPError) as fallo:
            _pedir(8864, "/api/operador/sesion", cookie)
    finally:
        servidor.shutdown()
        servidor.server_close()

    assert fallo.value.code == 401


def test_una_cookie_inventada_no_entra(base: Path) -> None:
    servidor = _levantar(base, 8865)
    try:
        _iniciar_sesion(base, 8865)

        with pytest.raises(urllib.error.HTTPError) as fallo:
            _pedir(8865, "/api/operador/sesion", "cookie-inventada")
    finally:
        servidor.shutdown()
        servidor.server_close()

    assert fallo.value.code == 401
