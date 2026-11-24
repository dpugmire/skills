import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from .models import Attachment, InboundMessage, JsonObject


SCHEMA_VERSION = 1


def _privateDirectory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)


def _atomicWrite(path: Path, data: bytes) -> None:
    _privateDirectory(path.parent)
    descriptor, temporaryName = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporaryPath = Path(temporaryName)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporaryPath, 0o600)
        os.replace(temporaryPath, path)
    finally:
        if temporaryPath.exists():
            temporaryPath.unlink()


def _safeName(value: str, fallback: str) -> str:
    name = Path(value.replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return (name or fallback)[:120]


def _bundleName(messageId: str) -> str:
    readable = _safeName(messageId, "message")[:48]
    digest = hashlib.sha256(messageId.encode("utf-8")).hexdigest()[:10]
    return f"{readable}-{digest}"


class SpoolStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        _privateDirectory(self.root)

    def _messageData(
        self,
        bundlePath: Path,
        section: str,
        message: InboundMessage,
    ) -> Dict[str, object]:
        attachments: List[Dict[str, object]] = []
        attachmentDirectory = bundlePath / f"{section}_attachments"
        for index, attachment in enumerate(message.attachments):
            filename = _safeName(attachment.filename, f"attachment-{index + 1}")
            stored = attachmentDirectory / f"{index:03d}-{filename}"
            _atomicWrite(stored, attachment.data)
            attachments.append(
                {
                    "filename": attachment.filename,
                    "mime_type": attachment.mimeType,
                    "path": str(stored.relative_to(bundlePath)),
                    "sha256": hashlib.sha256(attachment.data).hexdigest(),
                    "size": len(attachment.data),
                }
            )
        return {
            "message_id": message.messageId,
            "thread_id": message.threadId,
            "sender_name": message.senderName,
            "sender_address": message.senderAddress,
            "subject": message.subject,
            "received_at": message.receivedAt,
            "text": message.text,
            "rfc_message_id": message.rfcMessageId,
            "references": message.references,
            "label_ids": list(message.labelIds),
            "warnings": list(message.warnings),
            "attachments": attachments,
        }

    def writeBundle(
        self,
        submissionId: str,
        kind: str,
        source: InboundMessage,
        inbound: InboundMessage,
        priorResult: Optional[JsonObject] = None,
        feedback: str = "",
    ) -> Path:
        if kind not in ("new", "changes"):
            raise RuntimeError(f"Unsupported analysis kind: {kind}")
        submissionDirectory = self.root / _safeName(submissionId, "submission")
        bundlePath = submissionDirectory / _bundleName(inbound.messageId)
        _privateDirectory(bundlePath)

        sourceData = self._messageData(bundlePath, "source", source)
        if inbound.messageId == source.messageId:
            inboundData = dict(sourceData)
        else:
            inboundData = self._messageData(bundlePath, "inbound", inbound)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "submission_id": submissionId,
            "kind": kind,
            "feedback": feedback,
            "prior_result": priorResult,
            "source": sourceData,
            "inbound": inboundData,
        }
        manifestPath = bundlePath / "bundle.json"
        _atomicWrite(
            manifestPath,
            (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            ),
        )
        return manifestPath

    def readBundle(self, manifestPath: Path) -> JsonObject:
        path = manifestPath.expanduser().resolve()
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise RuntimeError(f"Bundle is outside the configured spool: {path}") from error
        if path.name != "bundle.json" or not path.is_file():
            raise RuntimeError(f"Analysis bundle does not exist: {path}")
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
        if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
            raise RuntimeError(f"Unsupported analysis bundle: {path}")
        return value

    def inboundMessage(self, manifestPath: Path) -> InboundMessage:
        manifest = self.readBundle(manifestPath)
        raw = manifest.get("inbound")
        if not isinstance(raw, dict):
            raise RuntimeError("Analysis bundle has no inbound message")
        attachments: List[Attachment] = []
        bundlePath = manifestPath.expanduser().resolve().parent
        for item in raw.get("attachments", []):
            if not isinstance(item, dict):
                continue
            relative = Path(str(item.get("path", "")))
            attachmentPath = (bundlePath / relative).resolve()
            try:
                attachmentPath.relative_to(bundlePath)
            except ValueError as error:
                raise RuntimeError("Attachment path escapes its analysis bundle") from error
            attachments.append(
                Attachment(
                    filename=str(item.get("filename", attachmentPath.name)),
                    mimeType=str(item.get("mime_type", "application/octet-stream")),
                    data=attachmentPath.read_bytes(),
                )
            )
        return InboundMessage(
            messageId=str(raw.get("message_id", "")),
            threadId=str(raw.get("thread_id", "")),
            senderName=str(raw.get("sender_name", "")),
            senderAddress=str(raw.get("sender_address", "")),
            subject=str(raw.get("subject", "(no subject)")),
            receivedAt=str(raw.get("received_at", "")),
            text=str(raw.get("text", "")),
            rfcMessageId=str(raw.get("rfc_message_id", "")),
            references=str(raw.get("references", "")),
            labelIds=[str(value) for value in raw.get("label_ids", [])],
            attachments=attachments,
            warnings=[str(value) for value in raw.get("warnings", [])],
        )
