import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .models import AppConfig


def defaultHome() -> Path:
    override = os.environ.get("VIS_HIGHLIGHTS_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".config" / "vis-highlights"


def configPath(home: Optional[Path] = None) -> Path:
    return (home or defaultHome()) / "config.json"


def _expandPath(value: str, base: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def loadConfig(home: Optional[Path] = None) -> AppConfig:
    root = home or defaultHome()
    path = configPath(root)
    if not path.exists():
        raise RuntimeError(
            f"Configuration not found at {path}. Run the 'init' command first."
        )

    with path.open(encoding="utf-8") as stream:
        raw = json.load(stream)

    required = ("gmail_address", "csv_path")
    missing = [name for name in required if not raw.get(name)]
    if missing:
        raise RuntimeError(f"Missing configuration values: {', '.join(missing)}")

    return AppConfig(
        gmailAddress=str(raw["gmail_address"]).strip().lower(),
        csvPath=_expandPath(str(raw["csv_path"]), root),
        googleCredentialsPath=_expandPath(
            str(raw.get("google_credentials_path", "google_credentials.json")), root
        ),
        googleTokenPath=_expandPath(
            str(raw.get("google_token_path", "google_token.json")), root
        ),
        stateDbPath=_expandPath(
            str(raw.get("state_db_path", "state.sqlite3")), root
        ),
        spoolPath=_expandPath(str(raw.get("spool_path", "spool")), root),
        defaultSectionHead=str(raw.get("default_section_head", "")).strip(),
        defaultGroupLeader=str(raw.get("default_group_leader", "")).strip(),
        timezone=str(raw.get("timezone", "America/New_York")),
        maxMessagesPerRun=int(raw.get("max_messages_per_run", 20)),
        maxAttachmentBytes=int(raw.get("max_attachment_bytes", 25_000_000)),
    )


def _atomicJson(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, tempName = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tempPath = Path(tempName)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tempPath, 0o600)
        os.replace(tempPath, path)
    finally:
        if tempPath.exists():
            tempPath.unlink()


def initializeConfig(gmailAddress: str, csvPath: Path, home: Optional[Path] = None) -> Path:
    root = home or defaultHome()
    path = configPath(root)
    if path.exists():
        raise RuntimeError(f"Configuration already exists at {path}")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    value = {
        "csv_path": str(csvPath.expanduser().resolve()),
        "default_group_leader": "",
        "default_section_head": "",
        "gmail_address": gmailAddress.strip().lower(),
        "google_credentials_path": "google_credentials.json",
        "google_token_path": "google_token.json",
        "max_attachment_bytes": 25_000_000,
        "max_messages_per_run": 20,
        "spool_path": "spool",
        "state_db_path": "state.sqlite3",
        "timezone": "America/New_York",
    }
    _atomicJson(path, value)
    return path
