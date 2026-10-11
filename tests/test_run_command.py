"""La orden de la CLI ejecutada dentro del proceso del panel.

Antes el panel lanzaba `python -m gestor_guias.app` por cada informe: ~0,8 s
de arranque e importaciones antes de calcular nada. Ahora llama a `app.main()`
con los mismos argumentos. Lo que ese cambio pone en riesgo es lo que se
prueba aqui: que un fallo siga llegando legible al panel, que dos informes a
la vez no se mezclen el texto y que la CLI siga sirviendo por si sola.
"""

from pathlib import Path
import threading

import pandas as pd
import pytest

from gestor_guias.repository import GuiaRepository

import gestor_guias.launcher_server as ls


def _guia(numero: str) -> dict:
    return {
        "PLANILLA": "1", "SERVICIO": "CE", "GUIA": numero, "UNID": "1",
        "TIPO DE SERVICIO": "PT", "DESTINATARIO": "Persona", "DIRECCION": "CL 1",
        "MUNICIPIO": "SAN GIL", "VALOR": "50000", "OPERADOR": "", "ESTADO": "N",
        "CAUSAL": "", "F_INGRESO": "2026-10-10 00:00:00", "F_ENTREGA": "",
    }


@pytest.fixture
def repositorio(tmp_path: Path, monkeypatch):
    repositorio = GuiaRepository(tmp_path / "guias.db")
    repositorio.save_consolidated(pd.DataFrame([_guia("101"), _guia("102")]))
    monkeypatch.setattr(ls, "REPOSITORY", repositorio)
    return repositorio


def test_una_orden_valida_devuelve_el_archivo_generado(repositorio, tmp_path, monkeypatch) -> None:
    import gestor_guias.app as cli

    monkeypatch.setattr(cli, "load_settings", _ajustes_de_prueba(tmp_path, repositorio))
    resultado = ls.run_command(["informe-dia", "--fecha", "2026-10-10"])

    assert resultado["ok"] is True
    assert resultado["descargas"] == ["informe diario 10 octubre.xlsx"]


def test_una_orden_que_falla_llega_legible_al_panel(repositorio) -> None:
    """Sin subproceso, una excepcion podria tumbar el hilo en vez de avisar."""
    resultado = ls.run_command(["informe-mensual", "--mes", "esto-no-es-un-mes"])

    assert resultado["ok"] is False
    assert resultado["output"].strip()
    assert resultado["descargas"] == []


def test_un_argumento_invalido_no_tumba_el_panel(repositorio) -> None:
    """argparse llama a sys.exit; el panel tiene que sobrevivirlo."""
    resultado = ls.run_command(["comando-que-no-existe"])

    assert resultado["ok"] is False
    assert resultado["output"].strip()


def test_dos_ordenes_a_la_vez_no_se_mezclan_el_texto(repositorio, tmp_path, monkeypatch) -> None:
    """main() escribe en la salida estandar, que es de todo el proceso."""
    import gestor_guias.app as cli

    monkeypatch.setattr(cli, "load_settings", _ajustes_de_prueba(tmp_path, repositorio))

    resultados: list[dict] = []
    hilos = [
        threading.Thread(target=lambda: resultados.append(
            ls.run_command(["informe-dia", "--fecha", "2026-10-10"])
        ))
        for _ in range(4)
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert len(resultados) == 4
    for resultado in resultados:
        assert resultado["ok"] is True
        # Si se mezclaran, una respuesta traeria el archivo de otra tambien.
        assert resultado["descargas"] == ["informe diario 10 octubre.xlsx"]


def test_la_cli_sigue_funcionando_por_si_sola() -> None:
    """main() sin argumentos debe seguir leyendo sys.argv, como siempre."""
    import inspect

    import gestor_guias.app as cli

    parametro = inspect.signature(cli.main).parameters["argv"]
    assert parametro.default is None


def _ajustes_de_prueba(tmp_path: Path, repositorio: GuiaRepository):
    """load_settings apuntando a la base y la carpeta de salida de la prueba."""
    from gestor_guias.config import load_settings

    reales = load_settings()

    def falsos():
        import dataclasses

        rutas = dataclasses.replace(
            reales.paths,
            database_file=repositorio.database_file,
            output_dir=tmp_path / "output",
        )
        return dataclasses.replace(reales, paths=rutas)

    return falsos
