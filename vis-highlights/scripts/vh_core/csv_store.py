import csv
import fcntl
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple
from zoneinfo import ZoneInfo

from .models import CATEGORIES, CSV_COLUMNS, JsonObject


# Related-work matching covers research, project, and meeting activity.  The
# proof-of-concept intentionally does not filter by employee name.
_RELATED_CATEGORIES = {"Publication", "Conference/Workshop", "Symposia/Meeting", "Project"}
_STOP_WORDS = {
    "about", "after", "and", "at", "for", "from", "into", "with", "this",
    "that", "the", "their", "using", "were", "work", "paper", "results",
    "study", "research", "group", "visualization", "visualisation",
}


def _tokens(value: object) -> set[str]:
    words = re.findall(r"[a-z0-9]{4,}", str(value or "").casefold())
    return {word for word in words if word not in _STOP_WORDS}


def _dateSortKey(value: object) -> tuple[int, int, int]:
    text = str(value or "").casefold()
    years = [int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", text)]
    year = max(years, default=0)
    months = (
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    )
    month = next((index + 1 for index, name in enumerate(months) if name in text), 0)
    numbers = [int(number) for number in re.findall(r"\b([0-3]?\d)\b", text)]
    day = next((number for number in numbers if 1 <= number <= 31), 0)
    return year, month, day


def _samePerson(first: object, second: object) -> bool:
    return " ".join(str(first or "").casefold().split()) == " ".join(
        str(second or "").casefold().split()
    )


def findRelatedHighlights(result: JsonObject, path: Path) -> List[Dict[str, str]]:
    """Find up to five older, potentially related approved highlights."""
    candidates: List[Dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if (row.get("Category") or "").strip() not in _RELATED_CATEGORIES:
                continue
            candidates.append(row)

    suggestions: List[Dict[str, str]] = []
    for highlight in result.get("highlights", []):
        category = str(highlight.get("category", "")).strip()
        if category not in _RELATED_CATEGORIES:
            continue
        employee = highlight.get("employee", "")
        currentTokens = _tokens(
            " ".join(
                [
                    str(highlight.get("title", "")),
                    str(highlight.get("details", "")),
                ]
            )
        )
        for row in candidates:
            # Proof-of-concept mode: include same-employee records so matching
            # can be demonstrated before the employee-name filter is restored.
            overlap = currentTokens & _tokens(
                " ".join([row.get("Title", ""), row.get("Details", "")])
            )
            if len(overlap) < 2:
                continue
            suggestions.append(
                {
                    "employee": (row.get("Employee") or "").strip(),
                    "title": (row.get("Title") or "").strip(),
                    "url": (row.get("URL") or "").strip(),
                    "dates": (row.get("Dates") or "").strip(),
                    "reason": "shared terms: " + ", ".join(sorted(overlap)[:5]),
                    "_sort": _dateSortKey(row.get("Dates")),
                }
            )

    suggestions.sort(key=lambda value: value["_sort"], reverse=True)
    unique: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for suggestion in suggestions:
        key = (suggestion["employee"], suggestion["title"])
        if key in seen:
            continue
        seen.add(key)
        suggestion.pop("_sort", None)
        unique.append(suggestion)
        if len(unique) == 5:
            break
    return unique


def _cleanHeader(values: Sequence[str]) -> Tuple[str, ...]:
    if not values:
        return tuple()
    first = values[0].lstrip("\ufeff")
    return (first, *values[1:])


def validateCsv(path: Path) -> int:
    if not path.is_file():
        raise RuntimeError(f"CSV file does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        try:
            header = _cleanHeader(next(reader))
        except StopIteration as error:
            raise RuntimeError(f"CSV file is empty: {path}") from error
        if header != CSV_COLUMNS:
            raise RuntimeError(
                "CSV header mismatch. Expected "
                + json.dumps(CSV_COLUMNS)
                + " but found "
                + json.dumps(header)
            )
        return sum(1 for _ in reader)


def historicalDirectory(path: Path) -> Dict[str, Dict[str, str]]:
    directory: Dict[str, Dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            employee = (row.get("Employee") or "").strip()
            if not employee:
                continue
            current = directory.setdefault(employee, {})
            for column, key in (
                ("Section Head", "section_head"),
                ("Group Leader", "group_leader"),
                ("Admin", "admin"),
            ):
                value = (row.get(column) or "").strip()
                if value:
                    current[key] = value
    return directory


def applyHistoricalDirectory(result: JsonObject, path: Path) -> JsonObject:
    directory = historicalDirectory(path)
    for highlight in result.get("highlights", []):
        employee = str(highlight.get("employee", "")).strip()
        mapping = directory.get(employee, {})
        for key in ("section_head", "group_leader", "admin"):
            if not str(highlight.get(key, "")).strip() and mapping.get(key):
                highlight[key] = mapping[key]
    return result


def applyOrganizationDefaults(
    result: JsonObject,
    sectionHead: str,
    groupLeader: str,
) -> JsonObject:
    defaults = {
        "section_head": sectionHead.strip(),
        "group_leader": groupLeader.strip(),
    }
    for highlight in result.get("highlights", []):
        for key, value in defaults.items():
            if value and not str(highlight.get(key, "")).strip():
                highlight[key] = value
    return result


def validateResult(result: JsonObject) -> None:
    if not isinstance(result, dict):
        raise RuntimeError("Model output is not an object")
    highlights = result.get("highlights")
    if not isinstance(highlights, list) or not highlights:
        raise RuntimeError("Model output must contain at least one highlight")
    for index, highlight in enumerate(highlights, start=1):
        if not isinstance(highlight, dict):
            raise RuntimeError(f"Highlight {index} is not an object")
        category = highlight.get("category")
        if category not in CATEGORIES:
            raise RuntimeError(f"Highlight {index} has invalid category: {category!r}")
        title = str(highlight.get("title", "")).strip()
        details = str(highlight.get("details", "")).strip()
        if not title:
            raise RuntimeError(f"Highlight {index} has an empty title")
        if len(title) > 255:
            raise RuntimeError(f"Highlight {index} title exceeds 255 characters")
        if not details:
            raise RuntimeError(f"Highlight {index} has empty details")
        for listKey in ("source_urls", "uncertainty_notes"):
            if not isinstance(highlight.get(listKey, []), list):
                raise RuntimeError(f"Highlight {index} field {listKey} is not a list")


def _timestamp(timezone: str) -> str:
    now = datetime.now(ZoneInfo(timezone))
    return f"{now.month}/{now.day}/{now.year} {now.strftime('%I').lstrip('0')}:{now:%M %p}"


def materializeRows(
    result: JsonObject,
    timezone: str,
    hasAttachments: bool,
    created: str = "",
) -> List[Dict[str, str]]:
    validateResult(result)
    createdValue = created or _timestamp(timezone)
    rows: List[Dict[str, str]] = []
    for highlight in result["highlights"]:
        row = {column: "" for column in CSV_COLUMNS}
        row.update(
            {
                "Created": createdValue,
                "Employee": str(highlight.get("employee", "")).strip(),
                "Section Head": str(highlight.get("section_head", "")).strip(),
                "Group Leader": str(highlight.get("group_leader", "")).strip(),
                "Category": str(highlight.get("category", "")).strip(),
                "Title": str(highlight.get("title", "")).strip(),
                "Details": str(highlight.get("details", "")).strip(),
                "URL": str(highlight.get("url", "")).strip(),
                "Dates": str(highlight.get("dates", "")).strip(),
                "Location": str(highlight.get("location", "")).strip(),
                "Attachments": "1" if hasAttachments else "0",
                "Admin": str(highlight.get("admin", "")).strip(),
            }
        )
        rows.append(row)
    return rows


def appendRowsIfMissing(path: Path, rows: Sequence[Mapping[str, str]]) -> int:
    if not rows:
        return 0
    with path.open("r+", encoding="utf-8-sig", newline="") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            stream.seek(0)
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise RuntimeError(f"CSV file has no header: {path}")
            reader.fieldnames = list(_cleanHeader(reader.fieldnames))
            if tuple(reader.fieldnames) != CSV_COLUMNS:
                raise RuntimeError(f"CSV header changed before append: {path}")
            existing = {
                tuple((row.get(column) or "") for column in CSV_COLUMNS)
                for row in reader
            }
            missing = [
                {column: str(row.get(column, "")) for column in CSV_COLUMNS}
                for row in rows
                if tuple(str(row.get(column, "")) for column in CSV_COLUMNS)
                not in existing
            ]
            if not missing:
                return 0
            size = os.fstat(stream.fileno()).st_size
            needsLineBreak = (
                size > 0
                and os.pread(stream.fileno(), 1, size - 1) not in (b"\r", b"\n")
            )
            stream.seek(0, os.SEEK_END)
            if needsLineBreak:
                stream.write("\r\n")
            writer = csv.DictWriter(
                stream,
                fieldnames=list(CSV_COLUMNS),
                quoting=csv.QUOTE_ALL,
                lineterminator="\r\n",
            )
            writer.writerows(missing)
            stream.flush()
            os.fsync(stream.fileno())
            return len(missing)
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
