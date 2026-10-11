"""Los avisos y las descargas del panel, probados en un navegador de verdad.

El recuadro negro "Resultado" al pie de cada pantalla se quito: ocupaba
espacio y no se veia bien. Los mensajes salen ahora como aviso flotante y el
archivo generado se descarga solo, sin boton de por medio. Es logica de
interfaz: que el JavaScript "parezca" correcto no basta.

Se saltan si no hay Playwright o navegador instalado.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
import threading

import pytest

from gestor_guias.operadores import hash_password
from gestor_guias.repository import GuiaRepository

import gestor_guias.launcher_server as ls

CHROMIUM = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

sync_playwright = pytest.importorskip(
    "playwright.sync_api", reason="Playwright no esta instalado"
).sync_playwright

sin_navegador = pytest.mark.skipif(
    not CHROMIUM.is_file(), reason="no hay Chromium instalado"
)

# Todas las pantallas del panel: ninguna debe conservar el recuadro negro ni
# quedarse sin las funciones compartidas de avisos.js.
RUTAS_DEL_PANEL = (
    "/panel",
    "/operadores",
    "/usuarios",
    "/zona-trabajo",
    "/entregas-mes",
    "/ingresos-egresos",
    "/prestamos",
    "/nomina",
    "/liquidaciones",
    "/dashboard",
)


@pytest.fixture
def panel(tmp_path: Path):
    ls.REPOSITORY = GuiaRepository(tmp_path / "guias.db")
    ls.REPOSITORY.crear_operador("admin", hash_password("clave"), "ADMIN", "admin")
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), ls.LauncherHandler)
    puerto = servidor.server_address[1]
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{puerto}"
    finally:
        servidor.shutdown()
        servidor.server_close()


@pytest.fixture
def pagina(panel):
    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(executable_path=str(CHROMIUM))
        contexto = navegador.new_context(accept_downloads=True)
        pagina = contexto.new_page()
        pagina.goto(f"{panel}/panel")
        pagina.fill("#login-usuario", "admin")
        pagina.fill("#login-password", "clave")
        pagina.click("#btn-login")
        pagina.wait_for_selector("#pantalla-principal:not(.oculto)")
        try:
            yield pagina
        finally:
            navegador.close()


@sin_navegador
def test_ninguna_pantalla_conserva_el_recuadro_negro(pagina, panel) -> None:
    for ruta in RUTAS_DEL_PANEL:
        pagina.goto(f"{panel}{ruta}")
        assert pagina.locator("#log").count() == 0, ruta
        assert pagina.locator(".log-seccion").count() == 0, ruta


@sin_navegador
def test_todas_las_pantallas_cargan_los_avisos_compartidos(pagina, panel) -> None:
    """Cada pagina perdio su copia local: si falta avisos.js, revienta al usarla."""
    fallos: list[str] = []
    pagina.on("pageerror", lambda error: fallos.append(str(error)))
    for ruta in RUTAS_DEL_PANEL:
        pagina.goto(f"{panel}{ruta}")
        tiene = pagina.evaluate(
            "typeof mostrarLog === 'function' && typeof mostrarDescargas === 'function'"
            " && typeof mostrarAviso === 'function'"
        )
        assert tiene, ruta
    assert fallos == []


@sin_navegador
def test_el_archivo_generado_se_descarga_solo(pagina) -> None:
    with pagina.expect_download(timeout=10_000) as descarga:
        pagina.evaluate("mostrarDescargas(['informe diario 10 octubre.xlsx'])")
    assert descarga.value.suggested_filename == "informe diario 10 octubre.xlsx"
    # Y no queda ningun boton "Descargar ..." que haya que ir a buscar.
    assert pagina.locator("#descargas").count() == 0


@sin_navegador
def test_un_aviso_normal_se_va_solo(pagina) -> None:
    pagina.evaluate("mostrarAviso('Orden ejecutada', 'exito')")
    assert pagina.locator(".aviso.exito").count() == 1
    pagina.wait_for_timeout(5000)
    assert pagina.locator(".aviso.exito").count() == 0


@sin_navegador
def test_un_error_se_queda_hasta_que_lo_cierren(pagina) -> None:
    """Un error hay que poder leerlo con calma; antes quedaba en el recuadro."""
    pagina.evaluate("mostrarAviso('No se pudo generar el informe', 'error')")
    assert pagina.locator(".aviso.error").count() == 1

    pagina.wait_for_timeout(5000)
    assert pagina.locator(".aviso.error").count() == 1

    pagina.click(".aviso.error .aviso-cerrar")
    pagina.wait_for_timeout(600)
    assert pagina.locator(".aviso.error").count() == 0
