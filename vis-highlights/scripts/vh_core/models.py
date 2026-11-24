from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


CSV_COLUMNS = (
    "ID",
    "Created",
    "Employee",
    "Section Head",
    "Group Leader",
    "Category",
    "Title",
    "Details",
    "URL",
    "Dates",
    "Location",
    "Attachments",
    "Admin",
    "CCSD form (supporting documents)",
    "Created By",
    "CCSD Form ID",
    "Date Submitted (CCSD)",
)

CATEGORIES = (
    "Conference/Workshop",
    "Publication",
    "Symposia/Meeting",
    "Software",
    "Professional Society Service",
    "Honor/Award",
    "Other",
    "Mentorship",
    "Project",
)


@dataclass(frozen=True)
class AppConfig:
    gmailAddress: str
    csvPath: Path
    googleCredentialsPath: Path
    googleTokenPath: Path
    stateDbPath: Path
    spoolPath: Path
    defaultSectionHead: str = ""
    defaultGroupLeader: str = ""
    timezone: str = "America/New_York"
    maxMessagesPerRun: int = 20
    maxAttachmentBytes: int = 25_000_000


@dataclass(frozen=True)
class Attachment:
    filename: str
    mimeType: str
    data: bytes


@dataclass(frozen=True)
class InboundMessage:
    messageId: str
    threadId: str
    senderName: str
    senderAddress: str
    subject: str
    receivedAt: str
    text: str
    rfcMessageId: str
    references: str
    labelIds: List[str] = field(default_factory=list)
    attachments: List[Attachment] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    automationGenerated: bool = False


@dataclass(frozen=True)
class ReplyCommand:
    action: str
    submissionId: str
    revision: int
    feedback: str = ""


JsonObject = Dict[str, Any]
