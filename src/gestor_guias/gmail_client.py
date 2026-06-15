from __future__ import annotations

from base64 import urlsafe_b64decode
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailAttachmentDownloader:
    def __init__(self, credentials_file: Path, token_file: Path) -> None:
        self.credentials_file = credentials_file
        self.token_file = token_file

    def download_excel_attachments(
        self,
        senders: Iterable[str],
        target_date: date,
        output_dir: Path,
    ) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        service = self._build_service()
        query = self._build_query(senders, target_date)
        message_ids = self._search_messages(service, query)

        downloaded: list[Path] = []
        for message_id in message_ids:
            message = service.users().messages().get(
                userId="me",
                id=message_id,
                format="full",
            ).execute()
            downloaded.extend(self._download_message_attachments(service, message, output_dir))

        return downloaded

    def _build_service(self):
        credentials = self._load_credentials()
        return build("gmail", "v1", credentials=credentials)

    def _load_credentials(self) -> Credentials:
        credentials = None
        if self.token_file.exists():
            credentials = Credentials.from_authorized_user_file(self.token_file, SCOPES)

        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                if not self.credentials_file.exists():
                    raise FileNotFoundError(
                        f"No existe {self.credentials_file}. Descarga el JSON OAuth de Google Cloud."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
                credentials = flow.run_local_server(port=0)

            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_file.write_text(credentials.to_json(), encoding="utf-8")

        return credentials

    def _build_query(self, senders: Iterable[str], target_date: date) -> str:
        sender_query = " OR ".join(f"from:{sender}" for sender in senders)
        after = target_date.isoformat()
        before = (target_date + timedelta(days=1)).isoformat()
        return f"({sender_query}) after:{after} before:{before} has:attachment"

    def _search_messages(self, service, query: str) -> list[str]:
        message_ids: list[str] = []
        request = service.users().messages().list(userId="me", q=query)

        while request is not None:
            response = request.execute()
            message_ids.extend(message["id"] for message in response.get("messages", []))
            request = service.users().messages().list_next(request, response)

        return message_ids

    def _download_message_attachments(self, service, message: dict, output_dir: Path) -> list[Path]:
        downloaded: list[Path] = []
        parts = self._walk_parts(message.get("payload", {}))

        for part in parts:
            filename = part.get("filename")
            body = part.get("body", {})
            attachment_id = body.get("attachmentId")

            if not filename or not attachment_id or not filename.lower().endswith((".xlsx", ".xls")):
                continue

            attachment = service.users().messages().attachments().get(
                userId="me",
                messageId=message["id"],
                id=attachment_id,
            ).execute()

            file_bytes = urlsafe_b64decode(attachment["data"].encode("utf-8"))
            safe_name = filename.replace("/", "_").replace("\\", "_")
            target = output_dir / safe_name
            target.write_bytes(file_bytes)
            downloaded.append(target)

        return downloaded

    def _walk_parts(self, payload: dict) -> list[dict]:
        parts = []
        stack = [payload]
        while stack:
            current = stack.pop()
            parts.append(current)
            stack.extend(current.get("parts", []))
        return parts

