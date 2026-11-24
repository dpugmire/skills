import csv
import tempfile
import unittest
from pathlib import Path

from vh_core.csv_store import (
    applyOrganizationDefaults,
    appendRowsIfMissing,
    materializeRows,
    validateCsv,
)
from vh_core.models import CSV_COLUMNS


def _result():
    return {
        "needs_human_review": False,
        "warnings": [],
        "highlights": [
            {
                "employee": "Ada Lovelace",
                "section_head": "",
                "group_leader": "",
                "category": "Publication",
                "title": "A useful paper",
                "details": "Line one\nLine two, with a comma",
                "url": "https://example.test/paper",
                "dates": "August 2026",
                "location": "",
                "admin": "",
                "source_urls": ["https://example.test/paper"],
                "uncertainty_notes": [],
            }
        ],
    }


class CsvStoreTests(unittest.TestCase):
    def test_organization_defaults_fill_only_missing_values(self):
        result = _result()
        applyOrganizationDefaults(result, "Rafael DaSilva", "David Pugmire")
        highlight = result["highlights"][0]
        self.assertEqual(highlight["section_head"], "Rafael DaSilva")
        self.assertEqual(highlight["group_leader"], "David Pugmire")

        highlight["section_head"] = "Employee-specific section head"
        highlight["group_leader"] = "Employee-specific group leader"
        applyOrganizationDefaults(result, "Rafael DaSilva", "David Pugmire")
        self.assertEqual(highlight["section_head"], "Employee-specific section head")
        self.assertEqual(highlight["group_leader"], "Employee-specific group leader")

    def test_append_is_quoted_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as stream:
                csv.writer(stream, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerow(
                    CSV_COLUMNS
                )
            rows = materializeRows(
                _result(), "America/New_York", True, created="9/1/2026 2:30 PM"
            )
            self.assertEqual(appendRowsIfMissing(path, rows), 1)
            self.assertEqual(appendRowsIfMissing(path, rows), 0)
            self.assertEqual(validateCsv(path), 1)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                record = next(csv.DictReader(stream))
            self.assertEqual(record["Details"], "Line one\nLine two, with a comma")
            self.assertEqual(record["Attachments"], "1")
            self.assertEqual(record["ID"], "")

    def test_append_adds_missing_line_break_after_header(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as stream:
                stream.write(",".join(CSV_COLUMNS))
            rows = materializeRows(
                _result(), "America/New_York", False, created="9/1/2026 2:30 PM"
            )

            self.assertEqual(appendRowsIfMissing(path, rows), 1)
            self.assertEqual(validateCsv(path), 1)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                records = list(csv.DictReader(stream))
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["Employee"], "Ada Lovelace")


if __name__ == "__main__":
    unittest.main()
