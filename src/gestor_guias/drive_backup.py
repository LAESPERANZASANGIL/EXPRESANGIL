"""Subida del respaldo de la base a una carpeta de Google Drive.

Los respaldos automaticos viven en el disco del VPS: si ese disco falla se
pierden todos a la vez. Este modulo se lleva una copia fuera del servidor,
sin depender de que alguien se acuerde de bajarla a mano.

El servidor no tiene navegador, asi que la autorizacion de Google se hace
**una sola vez desde el PC** con `python -m gestor_guias.app respaldo-drive
--autorizar`, y el `token_drive.json` que se genera se copia al VPS. A
partir de ahi la credencial se renueva sola con el refresh token.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# `drive.file` solo da acceso a los archivos que crea esta aplicacion: no
# puede leer ni tocar el resto del Drive del usuario.
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

CARPETA_MIME = "application/vnd.google-apps.folder"


class RespaldoDrive:
    """Sube y rota los respaldos en una carpeta de Google Drive."""

    def __init__(
        self,
        credentials_file: Path,
        token_file: Path,
        carpeta: str,
        copias: int = 30,
    ) -> None:
        self.credentials_file = Path(credentials_file)
        self.token_file = Path(token_file)
        self.carpeta = carpeta.strip()
        self.copias = max(1, int(copias))

    # ------------------------------- Credenciales -------------------------

    def autorizar(self) -> Path:
        """Abre el navegador para autorizar y guarda el token. Solo en el PC."""
        if not self.credentials_file.is_file():
            raise FileNotFoundError(
                f"No existe {self.credentials_file}. Descarga el JSON OAuth de "
                "Google Cloud (tipo 'Aplicacion de escritorio') y guardalo ahi."
            )
        flujo = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
        credenciales = flujo.run_local_server(port=0)
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(credenciales.to_json(), encoding="utf-8")
        return self.token_file

    def _credenciales(self) -> Credentials:
        if not self.token_file.is_file():
            raise FileNotFoundError(
                f"No existe {self.token_file}. Autoriza primero desde el PC con "
                "'python -m gestor_guias.app respaldo-drive --autorizar' y copia "
                "el archivo al servidor."
            )
        credenciales = Credentials.from_authorized_user_file(self.token_file, SCOPES)
        if not credenciales.valid:
            if not (credenciales.expired and credenciales.refresh_token):
                raise PermissionError(
                    "La autorizacion de Google ya no sirve; vuelve a autorizar "
                    "desde el PC y copia el token al servidor."
                )
            credenciales.refresh(Request())
            # El refresh puede traer un token nuevo: se guarda para no repetirlo.
            self.token_file.write_text(credenciales.to_json(), encoding="utf-8")
        return credenciales

    def _servicio(self):
        return build("drive", "v3", credentials=self._credenciales(), cache_discovery=False)

    # --------------------------------- Carpeta ----------------------------

    def _id_de_carpeta(self, servicio) -> str:
        """Id de la carpeta configurada; la crea si no existe."""
        nombre = self.carpeta.replace("'", "\\'")
        respuesta = servicio.files().list(
            q=f"name = '{nombre}' and mimeType = '{CARPETA_MIME}' and trashed = false",
            spaces="drive",
            fields="files(id, name)",
            pageSize=1,
        ).execute()
        encontradas = respuesta.get("files", [])
        if encontradas:
            return encontradas[0]["id"]

        creada = servicio.files().create(
            body={"name": self.carpeta, "mimeType": CARPETA_MIME},
            fields="id",
        ).execute()
        return creada["id"]

    # --------------------------------- Subida -----------------------------

    def subir(self, repositorio) -> dict:
        """Genera una copia verificada de la base y la sube a Drive.

        Devuelve el nombre, el tamaño y cuantas copias viejas se borraron.
        """
        marca = datetime.now().strftime("%Y-%m-%d %H%M")
        nombre = f"respaldo expresangil {marca}.db"

        servicio = self._servicio()
        carpeta_id = self._id_de_carpeta(servicio)

        with tempfile.TemporaryDirectory() as temporal:
            archivo = Path(temporal) / nombre
            # Reusa la copia verificada del repositorio: si la base esta
            # danada esto lanza y no se sube un respaldo inutil.
            repositorio.copia_para_descarga(archivo)
            tamano = archivo.stat().st_size
            medio = MediaFileUpload(
                str(archivo), mimetype="application/x-sqlite3", resumable=False
            )
            servicio.files().create(
                body={"name": nombre, "parents": [carpeta_id]},
                media_body=medio,
                fields="id",
            ).execute()

        return {
            "nombre": nombre,
            "tamano": tamano,
            "borradas": self._rotar(servicio, carpeta_id),
        }

    def _rotar(self, servicio, carpeta_id: str) -> int:
        """Deja solo las `copias` mas recientes; Drive tampoco es infinito."""
        respuesta = servicio.files().list(
            q=f"'{carpeta_id}' in parents and trashed = false",
            spaces="drive",
            fields="files(id, name, createdTime)",
            orderBy="createdTime desc",
            pageSize=200,
        ).execute()
        archivos = respuesta.get("files", [])

        borradas = 0
        for archivo in archivos[self.copias:]:
            servicio.files().delete(fileId=archivo["id"]).execute()
            borradas += 1
        return borradas
