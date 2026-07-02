from __future__ import annotations

from datetime import date, datetime
from http.cookies import SimpleCookie
import json
import os
import re
import secrets
import ssl
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import load_settings
from .consulta_publica import describir_estado
from .operadores import (
    ESTADO_SALIDA,
    calcular_diferencia_caja,
    cerrar_dia,
    documentos_vencidos,
    hash_password,
    recalcular_cierre,
    registrar_novedades,
    registrar_salidas,
    revertir_cierre,
    verify_password,
)
from .excel_processor import hoy_colombia, normalize_guide
from .exporter import export_marked_dataframe
from .reports import (
    filter_by_date,
    generate_entregadas_operador_excel,
    generate_salidas_operador_excel,
    normalize_dataframe,
    value_to_number,
)
from .repository import GuiaRepository


BASE_DIR = Path(__file__).resolve().parents[2]
LAUNCHER_DIR = BASE_DIR / "launcher"
PYTHON = sys.executable
HOST = os.environ.get("GESTOR_GUIAS_HOST", "127.0.0.1")
PORT = int(os.environ.get("GESTOR_GUIAS_PORT", "8765"))

SETTINGS = load_settings()
REPOSITORY = GuiaRepository(SETTINGS.paths.database_file)

# Sesiones en memoria: token -> {"usuario": ..., "nombre": ..., "rol": ...}
SESSIONS: dict[str, dict] = {}

ROLES_VALIDOS = {"operador", "admin"}

INFORME_COMANDOS = {
    "operador": "informe-operador",
    "salidas": "informe-salidas",
    "dia": "informe-dia",
    "recaudo": "informe-recaudo",
    "relacion": "informe-relacion-ce-rr",
    "devoluciones": "informe-devoluciones",
    "mensual": "informe-mensual",
}

UPLOADS_DIR = SETTINGS.paths.attachments_dir / "subidos"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
SESSION_MAX_EDAD_SEGUNDOS = 12 * 60 * 60
# Se activa en main() si se configuro un certificado HTTPS valido.
COOKIE_SECURE = False


def _cookie_atributos() -> str:
    return "; Secure" if COOKIE_SECURE else ""

STATIC_FILES = {
    "/logo.png": ("logo.png", "image/png"),
    # La raiz del dominio es publica: pagina de consulta para el cliente final.
    "/": ("consulta.html", "text/html; charset=utf-8"),
    "/consultar": ("consulta.html", "text/html; charset=utf-8"),
    "/consultar.html": ("consulta.html", "text/html; charset=utf-8"),
    "/consulta.css": ("consulta.css", "text/css; charset=utf-8"),
    "/consulta.js": ("consulta.js", "application/javascript; charset=utf-8"),
    # El panel interno de la empresa vive en /panel, no se enlaza desde la pagina publica.
    "/panel": ("index.html", "text/html; charset=utf-8"),
    "/panel.html": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/operadores": ("operadores.html", "text/html; charset=utf-8"),
    "/operadores.html": ("operadores.html", "text/html; charset=utf-8"),
    "/operadores.css": ("operadores.css", "text/css; charset=utf-8"),
    "/operadores.js": ("operadores.js", "application/javascript; charset=utf-8"),
    "/usuarios": ("usuarios.html", "text/html; charset=utf-8"),
    "/usuarios.html": ("usuarios.html", "text/html; charset=utf-8"),
    "/usuarios.css": ("usuarios.css", "text/css; charset=utf-8"),
    "/usuarios.js": ("usuarios.js", "application/javascript; charset=utf-8"),
    "/zona-trabajo": ("zona-trabajo.html", "text/html; charset=utf-8"),
    "/zona-trabajo.html": ("zona-trabajo.html", "text/html; charset=utf-8"),
    "/zona-trabajo.css": ("zona-trabajo.css", "text/css; charset=utf-8"),
    "/zona-trabajo.js": ("zona-trabajo.js", "application/javascript; charset=utf-8"),
    "/dashboard": ("dashboard.html", "text/html; charset=utf-8"),
    "/dashboard.html": ("dashboard.html", "text/html; charset=utf-8"),
    "/dashboard.css": ("dashboard.css", "text/css; charset=utf-8"),
    "/dashboard.js": ("dashboard.js", "application/javascript; charset=utf-8"),
}

# Campos de cada guia que necesita la Zona de Trabajo web.
GUIA_FIELDS = (
    "planilla",
    "guia",
    "destinatario",
    "direccion",
    "municipio",
    "valor",
    "operador",
    "estado",
    "causal",
)


AUDITORIA_FILE = SETTINGS.paths.database_file.parent / "auditoria.log"


def _validar_fecha_opcional(valor: object) -> str:
    texto = str(valor or "").strip()
    if not texto:
        return ""
    date.fromisoformat(texto)
    return texto


def registrar_auditoria(usuario: str, accion: str, detalle: str) -> None:
    AUDITORIA_FILE.parent.mkdir(parents=True, exist_ok=True)
    linea = f"{datetime.now().isoformat(timespec='seconds')}\t{usuario}\t{accion}\t{detalle}\n"
    with AUDITORIA_FILE.open("a", encoding="utf-8") as archivo:
        archivo.write(linea)


def run_command(args: list[str]) -> dict:
    result = subprocess.run(
        [PYTHON, "-m", "gestor_guias.app", *args],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
    )
    output = (result.stdout + result.stderr).strip() or "Listo."
    archivos = re.findall(r"^.+generado:\s*(.+)$", output, re.MULTILINE)
    descargas = [Path(ruta.strip()).name for ruta in archivos if Path(ruta.strip()).suffix in {".xlsx", ".pdf"}]
    return {"ok": result.returncode == 0, "output": output, "descargas": descargas}


class LauncherHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200, headers: dict | None = None) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _session_token(self) -> str | None:
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return None
        cookie = SimpleCookie()
        cookie.load(cookie_header)
        morsel = cookie.get("session")
        return morsel.value if morsel else None

    def _get_session(self) -> dict | None:
        token = self._session_token()
        if token is None:
            return None
        session = SESSIONS.get(token)
        if session is None:
            return None
        if time.monotonic() - session["creada"] > SESSION_MAX_EDAD_SEGUNDOS:
            SESSIONS.pop(token, None)
            return None
        return session

    def _require_admin(self) -> bool:
        """Responde 401 y devuelve False si la sesion actual no es de administrador."""
        session = self._get_session()
        if session is None or session.get("rol") != "admin":
            self._send_json(
                {"ok": False, "output": "Requiere sesion de administrador."}, status=401
            )
            return False
        return True

    def _send_file(self, filename: str, content_type: str) -> None:
        path = LAUNCHER_DIR / filename
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}

    def _read_multipart_files(self) -> dict[str, bytes]:
        content_type = self.headers.get("Content-Type", "")
        match = re.search(r"boundary=(.+)$", content_type)
        if not match:
            return {}
        boundary = match.group(1).strip('"').encode()
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        archivos: dict[str, bytes] = {}
        for part in body.split(b"--" + boundary):
            part = part.strip(b"\r\n")
            if not part or part == b"--":
                continue
            header_blob, _, content = part.partition(b"\r\n\r\n")
            header_text = header_blob.decode("utf-8", "ignore")
            filename_match = re.search(r'filename="([^"]*)"', header_text)
            if not filename_match or not filename_match.group(1):
                continue
            nombre = Path(filename_match.group(1)).name
            archivos[nombre] = content.rstrip(b"\r\n")
        return archivos

    def do_GET(self) -> None:
        try:
            self._do_GET()
        except Exception as error:
            self._send_json({"ok": False, "output": f"Error interno: {error}"}, status=500)

    def _do_GET(self) -> None:
        route = self.path.split("?")[0]

        if route == "/api/operador/sesion":
            session = self._get_session()
            if session is None:
                self._send_json({"ok": False}, status=401)
            else:
                self._send_json(
                    {
                        "ok": True,
                        "usuario": session["usuario"],
                        "nombre": session["nombre"],
                        "rol": session.get("rol", "operador"),
                    }
                )
            return

        if route == "/api/usuarios/estado":
            self._send_json({"ok": True, "hay_admin": REPOSITORY.contar_admins() > 0})
            return

        if route == "/api/guias":
            if not self._require_admin():
                return
            self._send_json({"ok": True, "guias": REPOSITORY.list_all()})
            return

        if route == "/api/dashboard":
            if not self._require_admin():
                return

            from urllib.parse import parse_qs, urlsplit

            query = parse_qs(urlsplit(self.path).query)
            fecha_texto = (query.get("fecha") or [""])[0].strip()
            try:
                fecha = date.fromisoformat(fecha_texto) if fecha_texto else hoy_colombia()
            except ValueError:
                self._send_json({"ok": False, "output": "Fecha invalida."})
                return

            dataframe = normalize_dataframe(REPOSITORY.to_dataframe())

            estados = [
                {"estado": fila["ESTADO"], "cantidad": int(fila["count"])}
                for fila in dataframe["ESTADO"].value_counts().reset_index(name="count").to_dict(orient="records")
            ]

            en_reparto = dataframe[dataframe["ESTADO"].str.upper() == ESTADO_SALIDA]
            operadores_en_reparto = [
                {"operador": fila["OPERADOR"], "cantidad": int(fila["count"])}
                for fila in en_reparto["OPERADOR"].value_counts().reset_index(name="count").to_dict(orient="records")
            ]
            valor_en_reparto = int(en_reparto["VALOR_NUMERICO"].sum())

            daily = filter_by_date(dataframe, fecha)
            totales_panel = REPOSITORY.sumar_totales_cierres_dia(fecha.isoformat())
            recaudado_total = totales_panel["recaudado"]
            bancos_total = totales_panel["bancos"]
            nequi_total = totales_panel["nequi"]
            envia_total = totales_panel["envia"]
            gastos_total = totales_panel["gastos"]
            adelanto_total = totales_panel["adelanto_salario"]
            efectivo_total = totales_panel["efectivo"]

            # El efectivo esperado del dia incluye lo ya recaudado mas lo que
            # todavia esta en la calle (estado R), para que se vea el total
            # que deberia entrar y se actualice solo a medida que el operador
            # entrega y recauda las guias que tiene en reparto.
            efectivo_esperado_total = efectivo_total + valor_en_reparto

            self._send_json(
                {
                    "ok": True,
                    "fecha": fecha.isoformat(),
                    "total_guias": len(dataframe),
                    "estados": estados,
                    "operadores_en_reparto": operadores_en_reparto,
                    "resumen_financiero": {
                        "recaudado": recaudado_total,
                        "bancos": bancos_total,
                        "nequi": nequi_total,
                        "envia": envia_total,
                        "gastos": gastos_total,
                        "adelanto_salario": adelanto_total,
                        "efectivo": efectivo_total,
                        "valor_en_reparto": valor_en_reparto,
                        "efectivo_esperado": efectivo_esperado_total,
                    },
                }
            )
            return

        if route == "/api/consultar-guia":
            from urllib.parse import parse_qs, urlsplit

            query = parse_qs(urlsplit(self.path).query)
            guia_texto = (query.get("guia") or [""])[0].strip()
            guia = normalize_guide(guia_texto)
            if not guia:
                self._send_json({"ok": False, "output": "Escribe el numero de guia."})
                return

            registro = REPOSITORY.obtener_guia(guia)
            if registro is None:
                self._send_json(
                    {
                        "ok": True,
                        "encontrada": False,
                        "mensaje": "Esta guia no ha llegado a nuestras oficinas.",
                    }
                )
                return

            self._send_json(
                {
                    "ok": True,
                    "encontrada": True,
                    "guia": registro["guia"],
                    "mensaje": describir_estado(registro),
                }
            )
            return

        if route == "/api/usuarios":
            session = self._get_session()
            if session is None or session.get("rol") != "admin":
                self._send_json(
                    {"ok": False, "output": "Requiere sesion de administrador."}, status=401
                )
                return
            self._send_json({"ok": True, "usuarios": REPOSITORY.listar_operadores()})
            return

        if route == "/api/operadores-guias":
            session = self._get_session()
            if session is None or session.get("rol") != "admin":
                self._send_json(
                    {"ok": False, "output": "Requiere sesion de administrador."}, status=401
                )
                return
            self._send_json({"ok": True, "operadores": REPOSITORY.listar_operadores_en_guias()})
            return

        if route == "/api/operador/descargar":
            session = self._get_session()
            if session is None:
                self.send_error(401)
                return
            from urllib.parse import parse_qs, urlsplit

            query = parse_qs(urlsplit(self.path).query)
            nombre = (query.get("archivo") or [""])[0]
            nombre = Path(nombre).name
            # Cada operador solo puede descargar sus propios informes de salidas o entregas.
            prefijos_permitidos = (f"salidas {session['nombre']} ", f"entregas {session['nombre']} ")
            if not nombre.startswith(prefijos_permitidos):
                self.send_error(403)
                return
            ruta = SETTINGS.paths.output_dir / nombre
            if not ruta.is_file():
                self.send_error(404)
                return
            self.send_response(200)
            content_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                if ruta.suffix == ".xlsx"
                else "application/pdf"
            )
            self.send_header("Content-Type", content_type)
            data_bytes = ruta.read_bytes()
            self.send_header("Content-Length", str(len(data_bytes)))
            self.send_header("Content-Disposition", f'attachment; filename="{nombre}"')
            self.end_headers()
            self.wfile.write(data_bytes)
            return

        if route == "/api/descargar":
            if not self._require_admin():
                return
            from urllib.parse import parse_qs, urlsplit

            query = parse_qs(urlsplit(self.path).query)
            nombre = (query.get("archivo") or [""])[0]
            nombre = Path(nombre).name
            ruta = SETTINGS.paths.output_dir / nombre
            if not nombre or not ruta.is_file():
                self.send_error(404)
                return
            content_type = "application/pdf" if ruta.suffix == ".pdf" else (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            data = ruta.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", f'attachment; filename="{nombre}"')
            self.end_headers()
            self.wfile.write(data)
            return

        if route in STATIC_FILES:
            filename, content_type = STATIC_FILES[route]
            self._send_file(filename, content_type)
            return

        self.send_error(404)

    def do_POST(self) -> None:
        try:
            self._do_POST()
        except Exception as error:
            self._send_json({"ok": False, "output": f"Error interno: {error}"}, status=500)

    def _do_POST(self) -> None:
        if self.path == "/api/subir-archivo":
            if not self._require_admin():
                return
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > MAX_UPLOAD_BYTES:
                self._send_json(
                    {"ok": False, "output": "El archivo supera el tamano maximo permitido."},
                    status=413,
                )
                return
            archivos = self._read_multipart_files()
            if not archivos:
                self._send_json({"ok": False, "output": "No se recibio ningun archivo."})
                return
            UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
            rutas = []
            for nombre, contenido in archivos.items():
                destino = UPLOADS_DIR / nombre
                if destino.exists():
                    sufijo = datetime.now().strftime("%Y%m%d%H%M%S")
                    destino = UPLOADS_DIR / f"{destino.stem}_{sufijo}{destino.suffix}"
                destino.write_bytes(contenido)
                rutas.append(str(destino))
            self._send_json({"ok": True, "rutas": rutas})
            return

        data = self._read_json()

        if self.path == "/api/guias/guardar":
            if not self._require_admin():
                return
            guia = normalize_guide(str(data.get("guia", "")).strip())
            if not guia:
                self._send_json({"ok": False, "output": "Indica la guia a guardar."})
                return
            fecha = str(data.get("fecha", "")).strip()
            entrega = str(data.get("entrega", "")).strip()
            servicio = str(data.get("servicio", "")).strip()
            REPOSITORY.update_guide_details(
                guia=guia,
                planilla=str(data.get("planilla", "")).strip(),
                destinatario=str(data.get("destinatario", "")).strip(),
                direccion=str(data.get("direccion", "")).strip(),
                municipio=str(data.get("municipio", "")).strip(),
                valor=str(data.get("valor", "")).strip(),
                operador=str(data.get("operador", "")).strip(),
                estado=str(data.get("estado", "")).strip(),
                causal=str(data.get("causal", "")).strip(),
                fecha=fecha or None,
                entrega=entrega or None,
                servicio=servicio or None,
            )
            self._send_json({"ok": True, "output": f"Se actualizo la guia {guia}."})
            return

        if self.path == "/api/guias/guardar-muchas":
            if not self._require_admin():
                return
            guias = [normalize_guide(str(g)) for g in data.get("guias", []) if str(g).strip()]
            if not guias:
                self._send_json({"ok": False, "output": "Indica una o varias guias."})
                return
            actualizadas = REPOSITORY.update_many_tracking_fields(
                guias=guias,
                operador=str(data.get("operador", "")).strip(),
                estado=str(data.get("estado", "")).strip(),
                causal=str(data.get("causal", "")).strip(),
            )
            self._send_json({"ok": True, "output": f"Se actualizaron {actualizadas} guia(s)."})
            return

        if self.path == "/api/guias/exportar-marcadas":
            if not self._require_admin():
                return
            guias = [normalize_guide(str(g)) for g in data.get("guias", []) if str(g).strip()]
            if not guias:
                self._send_json({"ok": False, "output": "Marca una o varias guias para descargar."})
                return
            dataframe = normalize_dataframe(REPOSITORY.to_dataframe())
            seleccion = dataframe[dataframe["GUIA"].isin(guias)]
            if seleccion.empty:
                self._send_json({"ok": False, "output": "No se encontraron guias para exportar."})
                return
            archivo = export_marked_dataframe(seleccion, SETTINGS.paths.output_dir, hoy_colombia())
            self._send_json(
                {"ok": True, "output": f"Se exportaron {len(seleccion)} guia(s).", "archivo": archivo.name}
            )
            return

        if self.path == "/api/guias/eliminar":
            if not self._require_admin():
                return
            guias = [normalize_guide(str(g)) for g in data.get("guias", []) if str(g).strip()]
            if not guias:
                self._send_json({"ok": False, "output": "Indica una o varias guias."})
                return
            eliminadas = REPOSITORY.delete_many(guias)
            registrar_auditoria(
                self._get_session()["usuario"], "eliminar-guias", f"{eliminadas} guia(s): {guias}"
            )
            self._send_json({"ok": True, "output": f"Se eliminaron {eliminadas} guia(s)."})
            return

        if self.path == "/api/guias/eliminar-fecha":
            if not self._require_admin():
                return
            fecha = str(data.get("fecha", "")).strip()
            if not fecha:
                self._send_json({"ok": False, "output": "Escribe una fecha en formato YYYY-MM-DD."})
                return
            eliminadas = REPOSITORY.delete_by_fecha(fecha)
            registrar_auditoria(
                self._get_session()["usuario"], "eliminar-guias-por-fecha", f"{eliminadas} guia(s), fecha={fecha}"
            )
            self._send_json({"ok": True, "output": f"Se eliminaron {eliminadas} guia(s) con fecha {fecha}."})
            return

        if self.path == "/api/guias/eliminar-estado":
            if not self._require_admin():
                return
            estado = str(data.get("estado", "")).strip()
            if not estado:
                self._send_json({"ok": False, "output": "Escribe un estado."})
                return
            eliminadas = REPOSITORY.delete_by_estado(estado)
            registrar_auditoria(
                self._get_session()["usuario"], "eliminar-guias-por-estado", f"{eliminadas} guia(s), estado={estado}"
            )
            self._send_json({"ok": True, "output": f"Se eliminaron {eliminadas} guia(s) con estado '{estado}'."})
            return

        if self.path == "/api/guias/eliminar-operador":
            if not self._require_admin():
                return
            operador = str(data.get("operador", "")).strip()
            if not operador:
                self._send_json({"ok": False, "output": "Escribe un operador."})
                return
            eliminadas = REPOSITORY.delete_by_operador(operador)
            registrar_auditoria(
                self._get_session()["usuario"], "eliminar-guias-por-operador", f"{eliminadas} guia(s), operador={operador}"
            )
            self._send_json(
                {"ok": True, "output": f"Se eliminaron {eliminadas} guia(s) del operador '{operador}'."}
            )
            return

        if self.path == "/api/importar":
            if not self._require_admin():
                return
            archivos = data.get("archivos")
            if not isinstance(archivos, list):
                archivos = str(data.get("archivo", "")).split(";")
            archivos = [ruta for ruta in (str(parte).strip() for parte in archivos) if ruta]
            fecha = str(data.get("fecha", "")).strip()
            if not archivos:
                self._send_json({"ok": False, "output": "Indica la ruta del archivo."})
                return
            args = ["importar", *archivos]
            if fecha:
                args += ["--fecha", fecha]
            self._send_json(run_command(args))
            return

        if self.path == "/api/exportar":
            if not self._require_admin():
                return
            fecha = str(data.get("fecha", "")).strip()
            estado = str(data.get("estado", "")).strip()
            args = ["exportar"]
            if fecha:
                args += ["--fecha", fecha]
            if estado:
                args += ["--estado", estado]
            self._send_json(run_command(args))
            return

        if self.path == "/api/informe":
            if not self._require_admin():
                return
            tipo = str(data.get("tipo", ""))
            fecha = str(data.get("fecha", "")).strip()
            comando = INFORME_COMANDOS.get(tipo)
            if not comando:
                self._send_json({"ok": False, "output": "Tipo de informe no valido."})
                return
            args = [comando]
            if tipo == "salidas":
                operador = str(data.get("operador", "")).strip()
                if not operador:
                    self._send_json({"ok": False, "output": "Indica el operador del informe de salidas."})
                    return
                args += ["--operador", operador]
            elif tipo == "operador":
                operador = str(data.get("operador", "")).strip()
                if operador:
                    args += ["--operador", operador]
            elif tipo == "mensual":
                mes = str(data.get("mes", "")).strip()
                if not mes:
                    self._send_json({"ok": False, "output": "Indica el mes del informe mensual."})
                    return
                args += ["--mes", mes]
                self._send_json(run_command(args))
                return
            if fecha:
                args += ["--fecha", fecha]
            self._send_json(run_command(args))
            return

        if self.path == "/api/cierre-general":
            if not self._require_admin():
                return

            fecha_texto = str(data.get("fecha", "")).strip()
            try:
                fecha = date.fromisoformat(fecha_texto) if fecha_texto else hoy_colombia()
            except ValueError:
                self._send_json({"ok": False, "output": "Fecha invalida."})
                return

            denominaciones_raw = data.get("denominaciones") or {}
            denominaciones = {
                int(denominacion): value_to_number(cantidad)
                for denominacion, cantidad in denominaciones_raw.items()
            }

            dataframe = normalize_dataframe(REPOSITORY.to_dataframe())
            daily = filter_by_date(dataframe, fecha)
            en_reparto = int((daily["ESTADO"].astype(str).str.strip().str.upper() == ESTADO_SALIDA).sum())

            totales = REPOSITORY.sumar_totales_cierres_dia(fecha.isoformat())
            recaudado_total = totales["recaudado"]
            bancos_total = totales["bancos"]
            nequi_total = totales["nequi"]
            envia_total = totales["envia"]
            gastos_total = totales["gastos"]
            adelanto_total = totales["adelanto_salario"]
            efectivo_esperado = totales["efectivo"]

            caja = calcular_diferencia_caja(efectivo_esperado, denominaciones)
            aviso = (
                f"Advertencia: hay {en_reparto} guia(s) en estado R aun sin cerrar para esta fecha."
                if en_reparto else ""
            )
            self._send_json(
                {
                    "ok": True,
                    "output": aviso or "Cierre general calculado.",
                    "resumen": {
                        "recaudado": recaudado_total,
                        "bancos": bancos_total,
                        "nequi": nequi_total,
                        "envia": envia_total,
                        "gastos": gastos_total,
                        "adelanto_salario": adelanto_total,
                        "efectivo_esperado": efectivo_esperado,
                        "efectivo_contado": caja["efectivo_contado"],
                        "diferencia": caja["diferencia"],
                        "nota": caja["nota"],
                        "en_reparto": en_reparto,
                    },
                }
            )
            return

        if self.path == "/api/cierre-recalcular":
            if not self._require_admin():
                return

            operador = str(data.get("operador", "")).strip()
            fecha_texto = str(data.get("fecha", "")).strip()
            if not operador or not fecha_texto:
                self._send_json({"ok": False, "output": "Falta operador o fecha."})
                return
            try:
                date.fromisoformat(fecha_texto)
            except ValueError:
                self._send_json({"ok": False, "output": "Fecha invalida."})
                return

            resumen = recalcular_cierre(REPOSITORY, operador, fecha_texto)
            self._send_json(
                {
                    "ok": True,
                    "output": "Cierre recalculado.",
                    "resumen": resumen,
                }
            )
            return

        if self.path == "/api/operador/login":
            usuario = str(data.get("usuario", "")).strip()
            password = str(data.get("password", ""))
            operador = REPOSITORY.obtener_operador(usuario)
            if not operador or not verify_password(password, operador["password_hash"]):
                self._send_json({"ok": False, "output": "Usuario o contrasena incorrectos."}, status=401)
                return

            vencidos = documentos_vencidos(operador)
            if vencidos:
                self._send_json(
                    {
                        "ok": False,
                        "output": "No puedes ingresar: tienes vencido(s) " + ", ".join(vencidos) + ".",
                    },
                    status=403,
                )
                return

            for token_previo, sesion_previa in list(SESSIONS.items()):
                if sesion_previa.get("usuario") == usuario:
                    SESSIONS.pop(token_previo, None)

            token = secrets.token_hex(16)
            rol = operador.get("rol", "operador")
            SESSIONS[token] = {
                "usuario": usuario,
                "nombre": operador["nombre"],
                "rol": rol,
                "creada": time.monotonic(),
            }
            self._send_json(
                {
                    "ok": True,
                    "output": "Sesion iniciada.",
                    "nombre": operador["nombre"],
                    "rol": rol,
                },
                headers={"Set-Cookie": f"session={token}; Path=/; HttpOnly; SameSite=Lax{_cookie_atributos()}"},
            )
            return

        if self.path == "/api/usuarios/crear":
            session = self._get_session()
            es_admin = session is not None and session.get("rol") == "admin"
            # Bootstrap: si todavia no existe ningun admin, se permite crear el primero sin sesion.
            primer_admin = REPOSITORY.contar_admins() == 0

            usuario = str(data.get("usuario", "")).strip()
            password = str(data.get("password", ""))
            nombre = str(data.get("nombre", "")).strip().upper()
            rol = str(data.get("rol", "operador")).strip().lower()
            existente = REPOSITORY.obtener_operador(usuario) if usuario else None

            try:
                licencia_vencimiento = _validar_fecha_opcional(data.get("licencia_vencimiento", ""))
                soat_vencimiento = _validar_fecha_opcional(data.get("soat_vencimiento", ""))
                tecnomecanica_vencimiento = _validar_fecha_opcional(data.get("tecnomecanica_vencimiento", ""))
            except ValueError:
                self._send_json({"ok": False, "output": "Las fechas deben tener formato YYYY-MM-DD."})
                return

            if not es_admin and not primer_admin:
                self._send_json(
                    {"ok": False, "output": "Requiere sesion de administrador."}, status=401
                )
                return
            if not es_admin and primer_admin and rol != "admin":
                self._send_json(
                    {"ok": False, "output": "Primero debes crear un usuario administrador."}
                )
                return
            if not usuario or not nombre:
                self._send_json({"ok": False, "output": "Usuario y nombre son obligatorios."})
                return
            if not password and not existente:
                self._send_json({"ok": False, "output": "La contrasena es obligatoria para usuarios nuevos."})
                return
            if rol not in ROLES_VALIDOS:
                self._send_json({"ok": False, "output": "Rol no valido (operador o admin)."})
                return

            password_hash = hash_password(password) if password else existente["password_hash"]
            REPOSITORY.crear_operador(
                usuario,
                password_hash,
                nombre,
                rol,
                licencia_vencimiento,
                soat_vencimiento,
                tecnomecanica_vencimiento,
            )
            registrar_auditoria(
                session["usuario"] if session else "bootstrap",
                "actualizar-usuario" if existente else "crear-usuario",
                f"usuario={usuario}, rol={rol}",
            )
            self._send_json(
                {"ok": True, "output": f"Usuario '{usuario}' guardado con rol '{rol}'."}
            )
            return

        if self.path == "/api/usuarios/eliminar":
            session = self._get_session()
            if session is None or session.get("rol") != "admin":
                self._send_json(
                    {"ok": False, "output": "Requiere sesion de administrador."}, status=401
                )
                return

            usuario = str(data.get("usuario", "")).strip()
            if usuario == session["usuario"]:
                self._send_json({"ok": False, "output": "No puedes eliminar tu propio usuario."})
                return

            eliminado = REPOSITORY.eliminar_operador(usuario)
            if eliminado:
                registrar_auditoria(session["usuario"], "eliminar-usuario", f"usuario={usuario}")
                self._send_json({"ok": True, "output": f"Usuario '{usuario}' eliminado."})
            else:
                self._send_json({"ok": False, "output": "Usuario no encontrado."})
            return

        if self.path == "/api/operador/logout":
            token = self._session_token()
            SESSIONS.pop(token, None)
            self._send_json(
                {"ok": True, "output": "Sesion cerrada."},
                headers={
                    "Set-Cookie": f"session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{_cookie_atributos()}"
                },
            )
            return

        if self.path == "/api/operador/salidas":
            session = self._get_session()
            if session is None:
                self._send_json({"ok": False, "output": "Debes iniciar sesion."}, status=401)
                return

            resultado = registrar_salidas(REPOSITORY, session["nombre"], str(data.get("guias", "")))
            salida = (
                f"Guias recibidas: {resultado['recibidas']}. "
                f"Asignadas a {session['nombre']}: {resultado['actualizadas']}."
            )
            creadas = resultado["no_encontradas"]
            if creadas:
                salida += " Creadas sin planilla: " + ", ".join(creadas) + "."
            self._send_json({"ok": True, "output": salida, "no_encontradas": creadas})
            return

        if self.path == "/api/operador/novedades":
            session = self._get_session()
            if session is None:
                self._send_json({"ok": False, "output": "Debes iniciar sesion."}, status=401)
                return

            fecha = str(data.get("fecha", "")).strip() or hoy_colombia().isoformat()
            resultado = registrar_novedades(
                REPOSITORY,
                session["nombre"],
                fecha,
                str(data.get("ro", "")),
                str(data.get("n", "")),
                str(data.get("d", "")),
            )
            resumen = ", ".join(
                f"{clave.upper()}: {info['actualizadas']}/{info['recibidas']}"
                for clave, info in resultado.items()
            )
            errores_d = resultado.get("d", {}).get("errores", [])
            if errores_d:
                resumen += (
                    f". No se entendieron {len(errores_d)} linea(s) de devoluciones "
                    "(formato esperado: guia y causal de 2 digitos, ej. '064108123 10')"
                )
            self._send_json(
                {"ok": True, "output": f"Novedades registradas -> {resumen}", "errores_d": errores_d}
            )
            return

        if self.path == "/api/operador/informe-salidas":
            session = self._get_session()
            if session is None:
                self._send_json({"ok": False, "output": "Debes iniciar sesion."}, status=401)
                return

            fecha_texto = str(data.get("fecha", "")).strip()
            try:
                fecha = date.fromisoformat(fecha_texto) if fecha_texto else hoy_colombia()
            except ValueError:
                self._send_json({"ok": False, "output": "Fecha invalida."})
                return

            ruta = generate_salidas_operador_excel(
                REPOSITORY, SETTINGS.paths.output_dir, session["nombre"], fecha
            )
            self._send_json(
                {"ok": True, "output": "Informe de salidas generado.", "archivo": ruta.name}
            )
            return

        if self.path == "/api/operador/cierre":
            session = self._get_session()
            if session is None:
                self._send_json({"ok": False, "output": "Debes iniciar sesion."}, status=401)
                return

            fecha = str(data.get("fecha", "")).strip() or hoy_colombia().isoformat()
            bancos = value_to_number(data.get("bancos", 0))
            nequi = value_to_number(data.get("nequi", 0))
            envia = value_to_number(data.get("envia", 0))
            gastos = value_to_number(data.get("gastos", 0))
            adelanto_salario = value_to_number(data.get("adelanto_salario", 0))
            denominaciones_raw = data.get("denominaciones") or {}
            denominaciones = {
                int(denominacion): value_to_number(cantidad)
                for denominacion, cantidad in denominaciones_raw.items()
            }
            simular = bool(data.get("simular"))

            resumen = cerrar_dia(
                REPOSITORY, session["nombre"], fecha, bancos, nequi, envia,
                denominaciones, gastos, adelanto_salario, simular=simular,
            )

            if simular:
                self._send_json(
                    {
                        "ok": True,
                        "output": "Simulacion de cierre generada. Nada se ha guardado todavia.",
                        "resumen": resumen,
                        "simulado": True,
                    }
                )
                return

            ruta_entregas = generate_entregadas_operador_excel(
                REPOSITORY,
                SETTINGS.paths.output_dir,
                session["nombre"],
                date.fromisoformat(fecha),
                resumen=resumen,
                denominaciones=denominaciones,
            )
            self._send_json(
                {
                    "ok": True,
                    "output": "Cierre del dia generado.",
                    "resumen": resumen,
                    "archivo_entregas": ruta_entregas.name,
                }
            )
            return

        if self.path == "/api/admin/cierre/revertir-dia":
            if not self._require_admin():
                return
            fecha_texto = str(data.get("fecha", "")).strip()
            if not fecha_texto:
                self._send_json({"ok": False, "output": "Falta la fecha."})
                return
            try:
                date.fromisoformat(fecha_texto)
            except ValueError:
                self._send_json({"ok": False, "output": "Fecha invalida."})
                return
            resultado = REPOSITORY.revertir_cierres_dia(fecha_texto)
            self._send_json({
                "ok": True,
                "output": (
                    f"Cierres del {fecha_texto} revertidos: "
                    f"{resultado['guias_revertidas']} guia(s) volvieron a R, "
                    f"{resultado['cierres_eliminados']} registro(s) de cierre eliminados."
                ),
                "resultado": resultado,
            })
            return

        if self.path == "/api/admin/cierre/revertir":
            if not self._require_admin():
                return
            operador = str(data.get("operador", "")).strip()
            fecha_texto = str(data.get("fecha", "")).strip()
            if not operador or not fecha_texto:
                self._send_json({"ok": False, "output": "Faltan operador o fecha."})
                return
            try:
                date.fromisoformat(fecha_texto)
            except ValueError:
                self._send_json({"ok": False, "output": "Fecha invalida."})
                return
            resultado = revertir_cierre(REPOSITORY, operador, fecha_texto)
            self._send_json({
                "ok": True,
                "output": (
                    f"Cierre revertido: {resultado['guias_revertidas']} guia(s) volvieron a estado R. "
                    f"Registro de cierre {'eliminado' if resultado['cierre_eliminado'] else 'no encontrado'}."
                ),
                "resultado": resultado,
            })
            return

        if self.path == "/api/admin/cierre/regenerar":
            if not self._require_admin():
                return
            operador = str(data.get("operador", "")).strip()
            fecha_texto = str(data.get("fecha", "")).strip() or hoy_colombia().isoformat()
            try:
                fecha_date = date.fromisoformat(fecha_texto)
            except ValueError:
                self._send_json({"ok": False, "output": "Fecha invalida."})
                return
            if not operador:
                self._send_json({"ok": False, "output": "Falta el operador."})
                return
            bancos = value_to_number(data.get("bancos", 0))
            nequi = value_to_number(data.get("nequi", 0))
            envia = value_to_number(data.get("envia", 0))
            gastos = value_to_number(data.get("gastos", 0))
            adelanto_salario = value_to_number(data.get("adelanto_salario", 0))
            denominaciones_raw = data.get("denominaciones") or {}
            denominaciones = {
                int(d): value_to_number(c) for d, c in denominaciones_raw.items()
            }
            resumen = cerrar_dia(
                REPOSITORY, operador, fecha_texto, bancos, nequi, envia,
                denominaciones, gastos, adelanto_salario,
            )
            ruta_entregas = generate_entregadas_operador_excel(
                REPOSITORY, SETTINGS.paths.output_dir, operador, fecha_date,
                resumen=resumen, denominaciones=denominaciones,
            )
            self._send_json({
                "ok": True,
                "output": f"Cierre regenerado para {operador} ({fecha_texto}).",
                "resumen": resumen,
                "archivo_entregas": ruta_entregas.name,
            })
            return

        self.send_error(404)

    def log_message(self, format_: str, *args: object) -> None:
        pass


def main() -> None:
    global COOKIE_SECURE

    server = ThreadingHTTPServer((HOST, PORT), LauncherHandler)
    esquema = "http"

    cert_file = SETTINGS.servidor.cert_file
    key_file = SETTINGS.servidor.key_file
    if cert_file and key_file:
        if not cert_file.is_file() or not key_file.is_file():
            print(
                f"Aviso: no se encontro el certificado o la llave configurados "
                f"({cert_file}, {key_file}); el panel seguira por HTTP plano."
            )
        else:
            contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            contexto.load_cert_chain(certfile=str(cert_file), keyfile=str(key_file))
            server.socket = contexto.wrap_socket(server.socket, server_side=True)
            esquema = "https"
            COOKIE_SECURE = True

    url = f"{esquema}://{HOST}:{PORT}/"
    if os.environ.get("GESTOR_GUIAS_NO_BROWSER") != "1":
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    print(f"Panel disponible en {url} (Ctrl+C para salir)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
