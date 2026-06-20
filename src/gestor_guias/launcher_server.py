from __future__ import annotations

from datetime import date
from http.cookies import SimpleCookie
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import load_settings
from .consulta_publica import describir_estado
from .operadores import (
    cerrar_dia,
    hash_password,
    registrar_novedades,
    registrar_salidas,
    verify_password,
)
from .excel_processor import normalize_guide
from .reports import value_to_number
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
    "dia": "informe-dia",
    "recaudo": "informe-recaudo",
    "relacion": "informe-relacion-ce-rr",
    "devoluciones": "informe-devoluciones",
}

UPLOADS_DIR = SETTINGS.paths.attachments_dir / "subidos"

STATIC_FILES = {
    "/logo.svg": ("logo.svg", "image/svg+xml"),
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
}


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
        return SESSIONS.get(token)

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

        if route == "/api/descargar":
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
        if self.path == "/api/subir-archivo":
            archivos = self._read_multipart_files()
            if not archivos:
                self._send_json({"ok": False, "output": "No se recibio ningun archivo."})
                return
            UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
            rutas = []
            for nombre, contenido in archivos.items():
                destino = UPLOADS_DIR / nombre
                destino.write_bytes(contenido)
                rutas.append(str(destino))
            self._send_json({"ok": True, "rutas": rutas})
            return

        data = self._read_json()

        if self.path == "/api/guias/guardar":
            if not self._require_admin():
                return
            guia = str(data.get("guia", "")).strip()
            if not guia:
                self._send_json({"ok": False, "output": "Indica la guia a guardar."})
                return
            REPOSITORY.update_tracking_fields(
                guia=guia,
                operador=str(data.get("operador", "")).strip(),
                estado=str(data.get("estado", "")).strip(),
                causal=str(data.get("causal", "")).strip(),
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

        if self.path == "/api/guias/eliminar":
            if not self._require_admin():
                return
            guias = [normalize_guide(str(g)) for g in data.get("guias", []) if str(g).strip()]
            if not guias:
                self._send_json({"ok": False, "output": "Indica una o varias guias."})
                return
            eliminadas = REPOSITORY.delete_many(guias)
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
            args = ["exportar"]
            if fecha:
                args += ["--fecha", fecha]
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
            if fecha:
                args += ["--fecha", fecha]
            self._send_json(run_command(args))
            return

        if self.path == "/api/operador/login":
            usuario = str(data.get("usuario", "")).strip()
            password = str(data.get("password", ""))
            operador = REPOSITORY.obtener_operador(usuario)
            if not operador or not verify_password(password, operador["password_hash"]):
                self._send_json({"ok": False, "output": "Usuario o contrasena incorrectos."}, status=401)
                return

            token = secrets.token_hex(16)
            rol = operador.get("rol", "operador")
            SESSIONS[token] = {"usuario": usuario, "nombre": operador["nombre"], "rol": rol}
            self._send_json(
                {
                    "ok": True,
                    "output": "Sesion iniciada.",
                    "nombre": operador["nombre"],
                    "rol": rol,
                },
                headers={"Set-Cookie": f"session={token}; Path=/; HttpOnly"},
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
            if not usuario or not password or not nombre:
                self._send_json({"ok": False, "output": "Usuario, contrasena y nombre son obligatorios."})
                return
            if rol not in ROLES_VALIDOS:
                self._send_json({"ok": False, "output": "Rol no valido (operador o admin)."})
                return

            REPOSITORY.crear_operador(usuario, hash_password(password), nombre, rol)
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
                self._send_json({"ok": True, "output": f"Usuario '{usuario}' eliminado."})
            else:
                self._send_json({"ok": False, "output": "Usuario no encontrado."})
            return

        if self.path == "/api/operador/logout":
            token = self._session_token()
            SESSIONS.pop(token, None)
            self._send_json(
                {"ok": True, "output": "Sesion cerrada."},
                headers={"Set-Cookie": "session=; Path=/; HttpOnly; Max-Age=0"},
            )
            return

        if self.path == "/api/operador/salidas":
            session = self._get_session()
            if session is None:
                self._send_json({"ok": False, "output": "Debes iniciar sesion."}, status=401)
                return

            resultado = registrar_salidas(REPOSITORY, session["nombre"], str(data.get("guias", "")))
            self._send_json(
                {
                    "ok": True,
                    "output": (
                        f"Guias recibidas: {resultado['recibidas']}. "
                        f"Asignadas a {session['nombre']}: {resultado['actualizadas']}."
                    ),
                }
            )
            return

        if self.path == "/api/operador/novedades":
            session = self._get_session()
            if session is None:
                self._send_json({"ok": False, "output": "Debes iniciar sesion."}, status=401)
                return

            fecha = str(data.get("fecha", "")).strip() or date.today().isoformat()
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
            self._send_json({"ok": True, "output": f"Novedades registradas -> {resumen}"})
            return

        if self.path == "/api/operador/cierre":
            session = self._get_session()
            if session is None:
                self._send_json({"ok": False, "output": "Debes iniciar sesion."}, status=401)
                return

            fecha = str(data.get("fecha", "")).strip() or date.today().isoformat()
            bancos = value_to_number(data.get("bancos", 0))
            nequi = value_to_number(data.get("nequi", 0))
            envia = value_to_number(data.get("envia", 0))

            resumen = cerrar_dia(REPOSITORY, session["nombre"], fecha, bancos, nequi, envia)
            self._send_json({"ok": True, "output": "Cierre del dia generado.", "resumen": resumen})
            return

        self.send_error(404)

    def log_message(self, format_: str, *args: object) -> None:
        pass


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), LauncherHandler)
    url = f"http://{HOST}:{PORT}/"
    if os.environ.get("GESTOR_GUIAS_NO_BROWSER") != "1":
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    print(f"Panel disponible en {url} (Ctrl+C para salir)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
