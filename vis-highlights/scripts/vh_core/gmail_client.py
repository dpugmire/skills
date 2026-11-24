import base64
import json
import mimetypes
import os
import tempfile
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .mail_text import htmlToText
from .models import AppConfig, Attachment, InboundMessage


GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
LABEL_PREFIX = "VisHighlights"
LABEL_PENDING = f"{LABEL_PREFIX}/Pending Analysis"
LABEL_AWAITING = f"{LABEL_PREFIX}/Awaiting Approval"
LABEL_COMMITTED = f"{LABEL_PREFIX}/Committed"
LABEL_REVISION = f"{LABEL_PREFIX}/Revision Requested"
LABEL_FAILED = f"{LABEL_PREFIX}/Failed"
LABEL_IGNORED = f"{LABEL_PREFIX}/Ignored"
AUTOMATION_HEADER = "X-Vis-Highlights-Automation"


def _atomicCredentials(path: Path, credentials: Credentials) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporaryName = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporaryPath = Path(temporaryName)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(json.loads(credentials.to_json()), stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporaryPath, 0o600)
        os.replace(temporaryPath, path)
    finally:
        if temporaryPath.exists():
            temporaryPath.unlink()


def authorize(config: AppConfig) -> None:
    if not config.googleCredentialsPath.is_file():
        raise RuntimeError(
            f"Google OAuth desktop-client file not found: {config.googleCredentialsPath}"
        )
    flow = InstalledAppFlow.from_client_secrets_file(
        str(config.googleCredentialsPath), [GMAIL_SCOPE]
    )
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    _atomicCredentials(config.googleTokenPath, credentials)


def _credentials(config: AppConfig) -> Credentials:
    if not config.googleTokenPath.is_file():
        raise RuntimeError(
            f"Gmail authorization token not found: {config.googleTokenPath}. Run 'auth'."
        )
    credentials = Credentials.from_authorized_user_file(
        str(config.googleTokenPath), [GMAIL_SCOPE]
    )
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        _atomicCredentials(config.googleTokenPath, credentials)
    if not credentials.valid:
        raise RuntimeError("Gmail authorization is invalid. Run 'auth' again.")
    return credentials


def _decodeBase64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii") + b"=" * (-len(value) % 4))


def _decodeHeader(value: str) -> str:
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _headers(payload: Dict[str, object]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for item in payload.get("headers", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).lower()
        value = _decodeHeader(str(item.get("value", "")))
        if name:
            values[name] = value
    return values


class GmailClient:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.service = build("gmail", "v1", credentials=_credentials(config), cache_discovery=False)
        self._labelIds: Optional[Dict[str, str]] = None

    def accountAddress(self) -> str:
        profile = self.service.users().getProfile(userId="me").execute()
        return str(profile.get("emailAddress", "")).lower()

    def _labels(self) -> Dict[str, str]:
        if self._labelIds is None:
            response = self.service.users().labels().list(userId="me").execute()
            self._labelIds = {
                str(label["name"]): str(label["id"])
                for label in response.get("labels", [])
            }
        return self._labelIds

    def ensureLabels(self) -> Dict[str, str]:
        labels = self._labels()
        for name in (
            LABEL_PENDING,
            LABEL_AWAITING,
            LABEL_COMMITTED,
            LABEL_REVISION,
            LABEL_FAILED,
            LABEL_IGNORED,
        ):
            if name in labels:
                continue
            result = (
                self.service.users()
                .labels()
                .create(
                    userId="me",
                    body={
                        "name": name,
                        "labelListVisibility": "labelShow",
                        "messageListVisibility": "show",
                    },
                )
                .execute()
            )
            labels[name] = str(result["id"])
        return labels

    def pendingMessageIds(self, maximum: int, createLabels: bool = True) -> List[str]:
        labels = self.ensureLabels() if createLabels else self._labels()
        failedId = labels.get(LABEL_FAILED)
        values: List[str] = []
        pageToken: Optional[str] = None
        while len(values) < maximum:
            response = (
                self.service.users()
                .messages()
                .list(
                    userId="me",
                    #q="in:inbox is:unread",
                    q="in:inbox is:unread subject:Highlight",
                    maxResults=min(maximum - len(values), 100),
                    pageToken=pageToken,
                )
                .execute()
            )
            for item in response.get("messages", []):
                messageId = str(item["id"])
                metadata = (
                    self.service.users()
                    .messages()
                    .get(userId="me", id=messageId, format="minimal")
                    .execute()
                )
                if not failedId or failedId not in metadata.get("labelIds", []):
                    values.append(messageId)
                if len(values) >= maximum:
                    break
            pageToken = response.get("nextPageToken")
            if not pageToken:
                break
        return values

    def getMessage(self, messageId: str) -> InboundMessage:
        raw = (
            self.service.users()
            .messages()
            .get(userId="me", id=messageId, format="full")
            .execute()
        )
        payload = raw.get("payload", {})
        headers = _headers(payload)
        senderName, senderAddress = parseaddr(headers.get("from", ""))
        plainParts: List[str] = []
        htmlParts: List[str] = []
        attachments: List[Attachment] = []
        warnings: List[str] = []

        def visit(part: Dict[str, object]) -> None:
            mimeType = str(part.get("mimeType", "application/octet-stream"))
            filename = str(part.get("filename", "")).strip()
            body = part.get("body", {})
            if not isinstance(body, dict):
                body = {}
            data = body.get("data")
            attachmentId = body.get("attachmentId")
            content = b""
            if data:
                content = _decodeBase64(str(data))
            elif attachmentId:
                response = (
                    self.service.users()
                    .messages()
                    .attachments()
                    .get(userId="me", messageId=messageId, id=str(attachmentId))
                    .execute()
                )
                content = _decodeBase64(str(response.get("data", "")))

            if filename:
                if len(content) > self.config.maxAttachmentBytes:
                    warnings.append(
                        f"Skipped attachment {filename!r}: {len(content)} bytes exceeds the configured limit."
                    )
                else:
                    attachments.append(
                        Attachment(filename=filename, mimeType=mimeType, data=content)
                    )
            elif mimeType == "text/plain" and content:
                plainParts.append(content.decode("utf-8", errors="replace"))
            elif mimeType == "text/html" and content:
                htmlParts.append(content.decode("utf-8", errors="replace"))

            for child in part.get("parts", []):
                if isinstance(child, dict):
                    visit(child)

        visit(payload)
        text = "\n\n".join(part.strip() for part in plainParts if part.strip())
        if not text:
            text = "\n\n".join(htmlToText(part) for part in htmlParts if part.strip())
        if not text:
            text = str(raw.get("snippet", "")).strip()

        try:
            receivedAt = datetime.fromtimestamp(
                int(raw.get("internalDate", "0")) / 1000, timezone.utc
            ).isoformat()
        except (TypeError, ValueError, OSError):
            receivedAt = ""

        return InboundMessage(
            messageId=str(raw["id"]),
            threadId=str(raw["threadId"]),
            senderName=senderName,
            senderAddress=senderAddress.lower(),
            subject=headers.get("subject", "(no subject)"),
            receivedAt=receivedAt,
            text=text,
            rfcMessageId=headers.get("message-id", ""),
            references=headers.get("references", ""),
            labelIds=[str(value) for value in raw.get("labelIds", [])],
            attachments=attachments,
            warnings=warnings,
            automationGenerated=headers.get(AUTOMATION_HEADER.lower(), "").lower()
            == "true",
        )

    def sendReply(
        self,
        message: InboundMessage,
        subject: str,
        body: str,
        attachments: Iterable[Path] = (),
    ) -> str:
        reply = EmailMessage()
        reply["To"] = message.senderAddress
        reply["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        if message.rfcMessageId:
            reply["In-Reply-To"] = message.rfcMessageId
            prior = message.references.strip()
            reply["References"] = f"{prior} {message.rfcMessageId}".strip()
        reply[AUTOMATION_HEADER] = "true"
        reply.set_content(body)
        for path in attachments:
            filePath = Path(path)
            if not filePath.is_file():
                raise RuntimeError(f"Approval attachment not found: {filePath}")
            mimeType, _ = mimetypes.guess_type(filePath.name)
            maintype, subtype = (mimeType or "application/octet-stream").split("/", 1)
            reply.add_attachment(
                filePath.read_bytes(),
                maintype=maintype,
                subtype=subtype,
                filename=filePath.name,
            )
        encoded = base64.urlsafe_b64encode(reply.as_bytes()).decode("ascii")
        result = (
            self.service.users()
            .messages()
            .send(userId="me", body={"raw": encoded, "threadId": message.threadId})
            .execute()
        )
        return str(result["id"])

    def updateLabels(
        self,
        messageId: str,
        add: Iterable[str] = (),
        remove: Iterable[str] = (),
        markRead: bool = False,
    ) -> None:
        labels = self.ensureLabels()
        addIds = [labels[name] for name in add]
        removeIds = [labels[name] for name in remove]
        if markRead:
            removeIds.append("UNREAD")
        self.service.users().messages().modify(
            userId="me",
            id=messageId,
            body={"addLabelIds": sorted(set(addIds)), "removeLabelIds": sorted(set(removeIds))},
        ).execute()

    def markFailed(self, messageId: str) -> None:
        self.updateLabels(messageId, add=(LABEL_FAILED,))

    def retryFailed(self, messageId: str) -> None:
        labels = self.ensureLabels()
        self.service.users().messages().modify(
            userId="me",
            id=messageId,
            body={
                "addLabelIds": ["UNREAD"],
                "removeLabelIds": [labels[LABEL_FAILED]],
            },
        ).execute()
