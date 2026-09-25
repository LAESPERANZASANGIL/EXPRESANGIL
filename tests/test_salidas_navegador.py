"""El resaltado de guias repetidas, probado en un navegador de verdad.

Es logica de interfaz: que el JavaScript "parezca" correcto no basta. Aqui
se levanta el panel, se abre Chromium y se comprueba lo que ve el operador.

Se saltan si no hay Playwright o navegador instalado, para que la suite siga
corriendo en el equipo de desarrollo (Windows) sin dependencias extra.
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


@pytest.fixture
def panel(tmp_path: Path):
    """Panel sirviendo en un puerto propio, con un operador listo."""
    ls.REPOSITORY = GuiaRepository(tmp_path / "guias.db")
    ls.REPOSITORY.crear_operador("pipe", hash_password("clave"), "PIPE")
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
        pagina = navegador.new_page()
        pagina.goto(f"{panel}/operadores")
        pagina.fill("#login-usuario", "pipe")
        pagina.fill("#login-password", "clave")
        pagina.click("#btn-login")
        pagina.wait_for_selector("#pantalla-operador:not(.oculto)")
        try:
            yield pagina
        finally:
            navegador.close()


def _escribir(pagina, texto: str) -> None:
    pagina.fill("#salidas-guias", texto)
    pagina.wait_for_timeout(150)


@sin_navegador
def test_sin_repetidas_no_hay_marcas_ni_bloqueo(pagina) -> None:
    _escribir(pagina, "064108001\n064108002\n064108003")

    assert pagina.locator("#salidas-resaltado mark").count() == 0
    assert pagina.is_disabled("#btn-salidas") is False
    assert pagina.is_visible("#salidas-duplicadas") is False


@sin_navegador
def test_siempre_dice_cuantas_encomiendas_saca(pagina) -> None:
    _escribir(pagina, "064108001\n064108002\n064108003")
    assert pagina.inner_text("#salidas-contador") == "3"

    _escribir(pagina, "064108001")
    assert pagina.inner_text("#salidas-contador") == "1"


@sin_navegador
def test_una_repetida_se_marca_y_bloquea_el_registro(pagina) -> None:
    _escribir(pagina, "064108001\n064108002\n064108001")

    # Se marcan las DOS apariciones: el operador tiene que ver donde estan.
    assert pagina.locator("#salidas-resaltado mark").count() == 2
    assert pagina.is_disabled("#btn-salidas") is True
    assert "064108001" in pagina.inner_text("#salidas-duplicadas")


@sin_navegador
def test_el_cero_inicial_no_disimula_la_repetida(pagina) -> None:
    """`064108001` y `64108001` son la misma guia."""
    _escribir(pagina, "064108001\n64108001")

    assert pagina.locator("#salidas-resaltado mark").count() == 2
    assert pagina.is_disabled("#btn-salidas") is True


@sin_navegador
def test_al_corregir_se_libera_el_boton(pagina) -> None:
    _escribir(pagina, "064108001\n064108001")
    assert pagina.is_disabled("#btn-salidas") is True

    _escribir(pagina, "064108001\n064108002")

    assert pagina.locator("#salidas-resaltado mark").count() == 0
    assert pagina.is_disabled("#btn-salidas") is False
    assert pagina.is_visible("#salidas-duplicadas") is False


@sin_navegador
def test_el_resaltado_cae_justo_sobre_el_campo(pagina) -> None:
    """Si las capas se desalinean, la marca roja señala el numero equivocado."""
    _escribir(pagina, "064108001\n064108001")

    medidas = pagina.evaluate(
        """() => {
            const campo = document.getElementById('salidas-guias');
            const capa = document.getElementById('salidas-resaltado');
            const a = campo.getBoundingClientRect();
            const b = capa.getBoundingClientRect();
            const ea = getComputedStyle(campo), eb = getComputedStyle(capa);
            return {
                dx: Math.round(b.x - a.x), dy: Math.round(b.y - a.y),
                dw: Math.round(b.width - a.width), dh: Math.round(b.height - a.height),
                mismaFuente: ea.fontFamily === eb.fontFamily
                    && ea.fontSize === eb.fontSize
                    && ea.lineHeight === eb.lineHeight
                    && ea.padding === eb.padding,
            };
        }"""
    )

    assert (medidas["dx"], medidas["dy"], medidas["dw"], medidas["dh"]) == (0, 0, 0, 0)
    assert medidas["mismaFuente"] is True


# --------------------- Gastos: las lineas se agregan a pedido ---------------


@sin_navegador
def test_el_cierre_arranca_con_una_sola_linea_de_gasto(pagina) -> None:
    """Cinco casillas vacias parecian de llenado obligatorio."""
    assert pagina.locator("#tabla-gastos-body tr").count() == 1
    # Con una sola linea no hay nada que quitar.
    assert pagina.locator("#tabla-gastos-body .quitar-gasto:visible").count() == 0


@sin_navegador
def test_se_agregan_lineas_hasta_el_maximo_de_cinco(pagina) -> None:
    for _ in range(10):
        if pagina.locator("#agregar-gasto").is_disabled():
            break
        pagina.click("#agregar-gasto")
    assert pagina.locator("#tabla-gastos-body tr").count() == 5
    assert pagina.locator("#agregar-gasto").is_disabled() is True


@sin_navegador
def test_quitar_una_linea_la_borra_y_recalcula_el_total(pagina) -> None:
    pagina.click("#agregar-gasto")
    filas = pagina.locator("#tabla-gastos-body tr")
    filas.nth(0).locator(".gasto-concepto").select_option("COMBUSTIBLE VAN")
    filas.nth(0).locator(".gasto-valor").fill("50000")
    filas.nth(1).locator(".gasto-concepto").select_option("CAMBIO DE ACEITE")
    filas.nth(1).locator(".gasto-valor").fill("20000")
    assert pagina.text_content("#cierre-gastos-total").strip() == "$ 70.000"

    filas.nth(1).locator(".quitar-gasto").click()
    assert pagina.locator("#tabla-gastos-body tr").count() == 1
    assert pagina.text_content("#cierre-gastos-total").strip() == "$ 50.000"
