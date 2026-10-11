"""Red de seguridad de las rutas del panel.

`_do_POST` pasa de las 1.400 lineas con 53 rutas en una sola cadena de `if`, y
cada una repite a mano su control de acceso. Antes de reorganizarlo hace falta
fijar lo que hay: que todas las rutas existen y que las de administrador
rechazan a quien no lo es. Si una ruta se pierde o se queda sin control al
mover el codigo, estas pruebas lo dicen.
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


@pytest.fixture(scope="module")
def panel(tmp_path_factory):
    """Un solo servidor para todo el modulo.

    Son mas de cien casos (una ruta cada uno) y ninguno escribe nada que el
    siguiente vea: levantar un panel por caso costaba minuto y medio.
    """
    carpeta = tmp_path_factory.mktemp("panel")
    repositorio = GuiaRepository(carpeta / "guias.db")
    repositorio.crear_operador("jefe", hash_password("clave"), "JEFE", "admin")
    repositorio.crear_operador("pipe", hash_password("clave"), "PIPE")
    anterior = ls.REPOSITORY
    ls.REPOSITORY = repositorio

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), ls.LauncherHandler)
    puerto = servidor.server_address[1]
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{puerto}"
    finally:
        servidor.shutdown()
        servidor.server_close()
        ls.REPOSITORY = anterior


def _pedir(url: str, datos: dict | None = None, cookie: str = "") -> int:
    """El codigo de respuesta, sin que un error HTTP corte la prueba."""
    peticion = urllib.request.Request(url)
    if cookie:
        peticion.add_header("Cookie", cookie)
    if datos is not None:
        peticion.data = json.dumps(datos).encode()
        peticion.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(peticion) as respuesta:
            return respuesta.status
    except urllib.error.HTTPError as error:
        return error.code


def _entrar(panel: str, usuario: str) -> str:
    peticion = urllib.request.Request(
        f"{panel}/api/operador/login",
        data=json.dumps({"usuario": usuario, "password": "clave"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(peticion) as respuesta:
        galleta = respuesta.headers.get("Set-Cookie", "")
    return galleta.split(";")[0]


def _rutas_declaradas() -> dict[str, list]:
    """Las rutas tal como estan escritas en el servidor, leidas del fuente.

    De las de administrador se guarda tambien su metodo: preguntar por POST a
    una ruta que solo existe en GET da 404 y no probaria nada.
    """
    import re

    fuente = Path(ls.__file__).read_text(encoding="utf-8").split("\n")
    rutas: dict[str, list] = {"GET": [], "POST": [], "admin": []}
    metodo = None
    for numero, linea in enumerate(fuente):
        if re.match(r"    def _do_GET", linea):
            metodo = "GET"
        elif re.match(r"    def _do_POST", linea):
            metodo = "POST"
        encontrada = re.match(r'        if (?:self\.path|route|ruta) == "(/[^"]+)":', linea)
        if encontrada and metodo:
            ruta = encontrada.group(1)
            rutas[metodo].append(ruta)
    # Las de administrador ya no repiten el control en cada bloque: salen de
    # la lista que el servidor comprueba una sola vez al entrar.
    for metodo, conjunto in ls.RUTAS_ADMIN.items():
        for ruta in sorted(conjunto):
            rutas["admin"].append((metodo, ruta))
    return rutas


RUTAS = _rutas_declaradas()

# Las tres rutas que responden sin sesion, a proposito. Se nombran aqui para
# que agregar una cuarta sea una decision explicita y no un descuido:
#   - usuarios/estado  dice solo si ya existe algun administrador, que hace
#     falta saber antes del primer ingreso.
#   - consultar-guia   es la consulta publica: el cliente final no tiene cuenta.
#   - operador/logout  cerrar sesion sin tenerla no hace dano.
RUTAS_PUBLICAS = {
    "/api/usuarios/estado",
    "/api/consultar-guia",
    "/api/operador/logout",
}


def test_el_panel_declara_las_rutas_que_esperamos() -> None:
    """Si el numero cambia, que sea a proposito y no por un bloque perdido."""
    assert len(RUTAS["GET"]) == 10
    assert len(RUTAS["POST"]) == 53
    assert len(RUTAS["admin"]) == 49


def test_toda_ruta_de_admin_declarada_existe_de_verdad() -> None:
    """Una ruta mal escrita en la lista no protegeria nada y no se notaria."""
    declaradas = {ruta for _, ruta in RUTAS["admin"]}
    existentes = set(RUTAS["GET"]) | set(RUTAS["POST"])
    assert declaradas <= existentes


@pytest.mark.parametrize("ruta", RUTAS["GET"])
def test_cada_ruta_get_existe(panel, ruta: str) -> None:
    """Sin sesion debe responder 401/403, nunca 404: la ruta esta ahi."""
    esperado = (200, 400) if ruta in RUTAS_PUBLICAS else (401, 403)
    assert _pedir(f"{panel}{ruta}") in esperado


@pytest.mark.parametrize("ruta", RUTAS["POST"])
def test_cada_ruta_post_existe(panel, ruta: str) -> None:
    esperado = (200, 400) if ruta in RUTAS_PUBLICAS else (401, 403)
    assert _pedir(f"{panel}{ruta}", datos={}) in esperado


@pytest.mark.parametrize("metodo,ruta", RUTAS["admin"])
def test_las_rutas_de_admin_rechazan_al_operador(panel, metodo: str, ruta: str) -> None:
    """Un operador con sesion valida no puede entrar a lo de administrador."""
    cookie = _entrar(panel, "pipe")
    datos = {} if metodo == "POST" else None
    assert _pedir(f"{panel}{ruta}", datos=datos, cookie=cookie) == 401


def test_solo_esas_tres_rutas_son_publicas(panel) -> None:
    """Si alguna ruta deja de pedir sesion, que no pase inadvertido."""
    abiertas = set()
    for ruta in RUTAS["GET"]:
        if _pedir(f"{panel}{ruta}") not in (401, 403):
            abiertas.add(ruta)
    for ruta in RUTAS["POST"]:
        if _pedir(f"{panel}{ruta}", datos={}) not in (401, 403):
            abiertas.add(ruta)
    assert abiertas == RUTAS_PUBLICAS


def test_el_admin_si_pasa_el_control(panel) -> None:
    """La otra mitad: que el control no este rechazando a todo el mundo."""
    cookie = _entrar(panel, "jefe")
    assert _pedir(f"{panel}/api/usuarios", cookie=cookie) == 200
