from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


BASE_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class GmailSettings:
    credentials_file: Path
    token_file: Path
    timezone: str
    senders: list[str]


@dataclass(frozen=True)
class PathSettings:
    attachments_dir: Path
    output_dir: Path
    database_file: Path


@dataclass(frozen=True)
class ExcelSettings:
    columns: list[str]
    editable_columns: list[str]


@dataclass(frozen=True)
class Settings:
    gmail: GmailSettings
    paths: PathSettings
    excel: ExcelSettings


def _project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


def load_settings(config_file: str | Path = "config/settings.toml") -> Settings:
    config_path = _project_path(str(config_file))
    if not config_path.exists():
        raise FileNotFoundError(
            f"No existe {config_path}. Copia config/settings.example.toml como config/settings.toml."
        )

    with config_path.open("rb") as file:
        raw = tomllib.load(file)

    gmail = raw["gmail"]
    paths = raw["paths"]
    excel = raw["excel"]

    return Settings(
        gmail=GmailSettings(
            credentials_file=_project_path(gmail["credentials_file"]),
            token_file=_project_path(gmail["token_file"]),
            timezone=str(gmail.get("timezone", "America/Bogota")),
            senders=list(gmail["senders"]),
        ),
        paths=PathSettings(
            attachments_dir=_project_path(paths["attachments_dir"]),
            output_dir=_project_path(paths["output_dir"]),
            database_file=_project_path(paths["database_file"]),
        ),
        excel=ExcelSettings(
            columns=list(excel["columns"]),
            editable_columns=list(excel["editable_columns"]),
        ),
    )
