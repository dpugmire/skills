import argparse
import importlib.metadata
import json
import os
import ssl
import stat
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional

from .config import defaultHome, initializeConfig, loadConfig
from .csv_store import validateCsv
from .gmail_client import GmailClient, authorize
from .spool import SpoolStore
from .state import StateStore
from .workflow import Workflow


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vis_highlights.py",
        description="Process Gmail highlight submissions with an email approval gate.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    initialize = subparsers.add_parser("init", help="Create the local configuration")
    initialize.add_argument("--gmail-address", required=True)
    initialize.add_argument("--csv-path", type=Path, required=True)

    subparsers.add_parser("auth", help="Authorize the configured Gmail account")
    subparsers.add_parser("doctor", help="Check configuration and credentials")

    sync = subparsers.add_parser(
        "sync", help="Download unread submissions and process approval commands"
    )
    sync.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect unread messages without modifying Gmail, state, the spool, or CSV",
    )

    run = subparsers.add_parser("run", help="Alias for sync")
    run.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)

    subparsers.add_parser("pending", help="List private bundles awaiting Codex analysis")

    stage = subparsers.add_parser(
        "stage", help="Validate a Codex result and send it to the submitter for approval"
    )
    stage.add_argument("--submission-id", required=True)
    stage.add_argument("--result-json", type=Path, required=True)

    dismiss = subparsers.add_parser(
        "dismiss", help="Mark a pending non-highlight as read and ignored"
    )
    dismiss.add_argument("--submission-id", required=True)
    dismiss.add_argument("--reason", required=True)

    subparsers.add_parser("status", help="Show recent local submission state")

    retry = subparsers.add_parser(
        "retry-failed", help="Remove the failure label so an unread message can retry"
    )
    retry.add_argument("--message-id", required=True)

    reprocess = subparsers.add_parser(
        "reprocess", help="Reprocess one previously consumed Gmail message"
    )
    reprocess.add_argument("--message-id", required=True)
    return parser


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def _init(arguments: argparse.Namespace) -> int:
    path = initializeConfig(arguments.gmail_address, arguments.csv_path)
    config = loadConfig()
    rows = validateCsv(config.csvPath)
    StateStore(config.stateDbPath)
    _print(
        {
            "config": str(path),
            "csv": str(config.csvPath),
            "existing_rows": rows,
            "gmail_address": config.gmailAddress,
            "spool": str(config.spoolPath),
            "state": str(config.stateDbPath),
        }
    )
    return 0


def _auth() -> int:
    config = loadConfig()
    authorize(config)
    gmail = GmailClient(config)
    address = gmail.accountAddress()
    if address != config.gmailAddress:
        raise RuntimeError(
            f"Authorized {address}, but configuration expects {config.gmailAddress}"
        )
    gmail.ensureLabels()
    _print({"authorized": address, "token": str(config.googleTokenPath)})
    return 0


def _doctor() -> int:
    checks: List[Dict[str, object]] = []
    okay = True

    def check(name: str, status: bool, detail: str) -> None:
        nonlocal okay
        okay = okay and status
        checks.append({"check": name, "ok": status, "detail": detail})

    try:
        config = loadConfig()
        check("configuration", True, str(defaultHome() / "config.json"))
    except Exception as error:
        check("configuration", False, str(error))
        _print({"ok": False, "checks": checks})
        return 1

    try:
        rows = validateCsv(config.csvPath)
        writable = os.access(config.csvPath, os.W_OK)
        check("csv", writable, f"{config.csvPath} ({rows} data rows)")
    except Exception as error:
        check("csv", False, str(error))

    for package in ("google-api-python-client", "google-auth-oauthlib"):
        try:
            version = importlib.metadata.version(package)
            check(f"dependency:{package}", True, version)
        except importlib.metadata.PackageNotFoundError:
            check(f"dependency:{package}", False, "not installed")

    pythonSupported = sys.version_info >= (3, 10) and "LibreSSL" not in ssl.OPENSSL_VERSION
    check(
        "python_runtime",
        pythonSupported,
        f"Python {sys.version.split()[0]}; {ssl.OPENSSL_VERSION} (Python 3.10+ with OpenSSL required)",
    )

    check(
        "google_credentials",
        config.googleCredentialsPath.is_file(),
        str(config.googleCredentialsPath),
    )
    check("google_token", config.googleTokenPath.is_file(), str(config.googleTokenPath))

    if config.googleTokenPath.is_file():
        try:
            address = GmailClient(config).accountAddress()
            check(
                "gmail_account",
                address == config.gmailAddress,
                f"authorized={address}; configured={config.gmailAddress}",
            )
        except Exception as error:
            check("gmail_account", False, str(error))

    for privatePath in (
        defaultHome() / "config.json",
        config.googleCredentialsPath,
        config.googleTokenPath,
        config.stateDbPath,
        config.spoolPath,
    ):
        if not privatePath.exists():
            continue
        mode = stat.S_IMODE(privatePath.stat().st_mode)
        check(
            f"permissions:{privatePath.name}",
            mode & 0o077 == 0,
            f"mode {mode:04o}",
        )

    _print({"ok": okay, "checks": checks})
    return 0 if okay else 1


def _sync(dryRun: bool) -> int:
    config = loadConfig()
    validateCsv(config.csvPath)
    if dryRun:
        with tempfile.TemporaryDirectory(prefix="vis-highlights-dry-run-") as directory:
            root = Path(directory)
            isolated = replace(
                config,
                stateDbPath=root / "state.sqlite3",
                spoolPath=root / "spool",
            )
            results = Workflow(isolated).run(dryRun=True)
    else:
        results = Workflow(config).run(dryRun=False)
    _print({"dry_run": dryRun, "processed": len(results), "results": results})
    return 1 if any(result.get("outcome") == "failed" for result in results) else 0


def _pending() -> int:
    config = loadConfig()
    state = StateStore(config.stateDbPath)
    spool = SpoolStore(config.spoolPath)
    values: List[Dict[str, object]] = []
    for item in state.pendingAnalyses():
        value = dict(item)
        value["submission_id"] = value.pop("id")
        path = Path(str(value["pending_bundle_path"]))
        try:
            manifest = spool.readBundle(path)
            value["kind"] = manifest.get("kind", "new")
            value["suggested_result_path"] = str(path.parent / "result.json")
        except Exception as error:
            value["bundle_error"] = str(error)
        values.append(value)
    _print({"pending": values})
    return 1 if any("bundle_error" in value for value in values) else 0


def _stage(identifier: str, resultPath: Path) -> int:
    config = loadConfig()
    validateCsv(config.csvPath)
    submission = StateStore(config.stateDbPath).submission(identifier.upper())
    if submission is None:
        raise RuntimeError(f"Unknown submission: {identifier}")
    bundleValue = str(submission.get("pending_bundle_path") or "")
    if not bundleValue:
        raise RuntimeError(f"Submission has no pending analysis: {identifier}")
    bundleDirectory = Path(bundleValue).expanduser().resolve().parent
    path = resultPath.expanduser().resolve()
    try:
        path.relative_to(bundleDirectory)
    except ValueError as error:
        raise RuntimeError("Result JSON must be stored inside its private bundle") from error
    if not path.is_file():
        raise RuntimeError(f"Result JSON does not exist: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise RuntimeError(f"Result JSON must be owner-only (mode 0600), found {mode:04o}")
    with path.open(encoding="utf-8") as stream:
        result = json.load(stream)
    if not isinstance(result, dict):
        raise RuntimeError("Result JSON must contain an object")
    value = Workflow(config).stage(identifier, result)
    _print(value)
    return 0


def _status() -> int:
    config = loadConfig()
    state = StateStore(config.stateDbPath)
    _print({"submissions": state.summary()})
    return 0


def _dismiss(identifier: str, reason: str) -> int:
    config = loadConfig()
    value = Workflow(config).dismiss(identifier, reason)
    _print(value)
    return 0


def _retry(messageId: str) -> int:
    config = loadConfig()
    GmailClient(config).retryFailed(messageId)
    _print({"message_id": messageId, "retry_enabled": True})
    return 0


def _reprocess(messageId: str) -> int:
    config = loadConfig()
    value = Workflow(config).reprocessMessage(messageId)
    _print(value)
    return 1 if value.get("outcome") == "failed" else 0


def main(argv: Optional[List[str]] = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "init":
            return _init(arguments)
        if arguments.command == "auth":
            return _auth()
        if arguments.command == "doctor":
            return _doctor()
        if arguments.command in ("sync", "run"):
            return _sync(arguments.dry_run)
        if arguments.command == "pending":
            return _pending()
        if arguments.command == "stage":
            return _stage(arguments.submission_id, arguments.result_json)
        if arguments.command == "dismiss":
            return _dismiss(arguments.submission_id, arguments.reason)
        if arguments.command == "status":
            return _status()
        if arguments.command == "retry-failed":
            return _retry(arguments.message_id)
        if arguments.command == "reprocess":
            return _reprocess(arguments.message_id)
        raise RuntimeError(f"Unsupported command: {arguments.command}")
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
