import re
from html.parser import HTMLParser
from typing import Iterable, List, Optional

from .models import JsonObject, ReplyCommand


class _TextExtractor(HTMLParser):
    _blockTags = {
        "address",
        "article",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "header",
        "li",
        "p",
        "section",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() in self._blockTags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._blockTags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def htmlToText(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line)


_quotedMarkers = (
    re.compile(r"^On .+wrote:\s*$", re.IGNORECASE),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}$", re.IGNORECASE),
    re.compile(r"^From:\s+.+$", re.IGNORECASE),
)

_replySeparator = re.compile(r"^[_=]{4,}\s*$")


def newReplyText(value: str) -> str:
    kept: List[str] = []
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(">"):
            break
        if stripped == "--":
            break
        if _replySeparator.match(stripped):
            break
        if (
            stripped.lower().startswith("on ")
            and index + 1 < len(lines)
            and lines[index + 1].strip().lower() == "wrote:"
        ):
            break
        if any(pattern.match(stripped) for pattern in _quotedMarkers):
            break
        kept.append(line)
    return "\n".join(kept).strip()


_commandPattern = re.compile(
    r"^(APPROVE|CHANGES)\s+(VH-[A-Z0-9]{10})\s+R([1-9][0-9]*)$",
    re.IGNORECASE,
)


def parseReplyCommand(
    value: str,
    submissionId: Optional[str] = None,
    revision: Optional[int] = None,
) -> Optional[ReplyCommand]:
    fresh = newReplyText(value)
    lines = fresh.splitlines()
    firstIndex = next((i for i, line in enumerate(lines) if line.strip()), None)
    if firstIndex is None:
        return None
    match = _commandPattern.match(lines[firstIndex].strip())
    if match:
        feedback = "\n".join(lines[firstIndex + 1 :]).strip()
        return ReplyCommand(
            action=match.group(1).upper(),
            submissionId=match.group(2).upper(),
            revision=int(match.group(3)),
            feedback=feedback,
        )

    if submissionId is None or revision is None:
        return None

    if fresh.casefold() == "approve":
        return ReplyCommand(
            action="APPROVE",
            submissionId=submissionId.upper(),
            revision=revision,
        )

    firstLine = lines[firstIndex].strip()
    if firstLine.casefold() == "changes":
        feedback = "\n".join(lines[firstIndex + 1 :]).strip()
    else:
        feedback = fresh
    return ReplyCommand(
        action="CHANGES",
        submissionId=submissionId.upper(),
        revision=revision,
        feedback=feedback,
    )


def _field(label: str, value: object) -> str:
    rendered = "" if value is None else str(value)
    return f"{label}: {rendered}"


def formatApprovalEmail(
    submissionId: str,
    revision: int,
    subject: str,
    result: JsonObject,
) -> str:
    lines = [
        "VIS Highlights approval request",
        "",
        _field("Submission", submissionId),
        _field("Revision", f"R{revision}"),
        _field("Original subject", subject),
        "",
    ]
    highlights = result.get("highlights", [])
    for index, highlight in enumerate(highlights, start=1):
        lines.extend(
            [
                f"Proposed record {index} of {len(highlights)}",
                _field("Employee", highlight.get("employee", "")),
                _field("Section Head", highlight.get("section_head", "")),
                _field("Group Leader", highlight.get("group_leader", "")),
                _field("Category", highlight.get("category", "")),
                _field("Title", highlight.get("title", "")),
                _field("Details", highlight.get("details", "")),
                _field("URL", highlight.get("url", "")),
                _field("Dates", highlight.get("dates", "")),
                _field("Location", highlight.get("location", "")),
                _field("Admin", highlight.get("admin", "")),
            ]
        )
        sources = highlight.get("source_urls", [])
        if sources:
            lines.append("Sources:")
            lines.extend(f"  - {source}" for source in sources)
        notes = highlight.get("uncertainty_notes", [])
        if notes:
            lines.append("Uncertainties:")
            lines.extend(f"  - {note}" for note in notes)
        lines.append("")

    warnings = result.get("warnings", [])
    if warnings:
        lines.append("Submission warnings:")
        lines.extend(f"  - {warning}" for warning in warnings)
        lines.append("")

    suggestions = result.get("collaboration_suggestions", [])
    if suggestions:
        lines.extend(["FYI: Potentially related work", ""])
        lines.append(
            "These previous highlights may overlap with this work. Consider reviewing them or contacting the listed colleague:"
        )
        for suggestion in suggestions:
            line = f"  - {suggestion.get('employee', '')} — {suggestion.get('title', '')}"
            dates = str(suggestion.get("dates", "")).strip()
            reason = str(suggestion.get("reason", "")).strip()
            if dates:
                line += f" ({dates})"
            if reason:
                line += f"; {reason}"
            lines.append(line)
            url = str(suggestion.get("url", "")).strip()
            if url:
                lines.append(f"    Link: {url}")
        lines.extend(
            [
                "These are possible overlaps only; no collaboration or CSV change is implied.",
                "",
            ]
        )

    lines.extend(
        [
            "To approve the current revision, reply with only:",
            "approve",
            "",
            "To request changes, reply with the correction, for example:",
            "change the date to August 27 2026",
            "",
            "The submission and current revision are identified from this email thread.",
            f"Full commands also work: APPROVE {submissionId} R{revision} or CHANGES {submissionId} R{revision}.",
        ]
    )
    return "\n".join(lines)


def formatConfirmationEmail(submissionId: str, revision: int, rowCount: int) -> str:
    noun = "record" if rowCount == 1 else "records"
    return (
        f"Approved submission {submissionId} R{revision} was added to the CSV "
        f"({rowCount} {noun}).\n"
    )


def formatCommandHelp(submissionId: str, revision: int) -> str:
    return "\n".join(
        [
            "I could not apply your reply to the current approval request.",
            "",
            "To approve, reply with only: approve",
            "To request changes, reply with the correction, for example:",
            "change the date to August 27 2026",
            "",
            f"Full commands also work: APPROVE {submissionId} R{revision} or CHANGES {submissionId} R{revision}.",
        ]
    )
