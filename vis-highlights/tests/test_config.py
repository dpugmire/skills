import json
import tempfile
import unittest
from pathlib import Path

from vh_core.config import loadConfig


class ConfigTests(unittest.TestCase):
    def test_loads_optional_organization_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.json").write_text(
                json.dumps(
                    {
                        "gmail_address": "vishighlights@gmail.com",
                        "csv_path": "report.csv",
                        "default_section_head": " Rafael DaSilva ",
                        "default_group_leader": " David Pugmire ",
                    }
                ),
                encoding="utf-8",
            )

            config = loadConfig(root)

            self.assertEqual(config.defaultSectionHead, "Rafael DaSilva")
            self.assertEqual(config.defaultGroupLeader, "David Pugmire")

    def test_missing_organization_defaults_remain_backward_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.json").write_text(
                json.dumps(
                    {
                        "gmail_address": "vishighlights@gmail.com",
                        "csv_path": "report.csv",
                    }
                ),
                encoding="utf-8",
            )

            config = loadConfig(root)

            self.assertEqual(config.defaultSectionHead, "")
            self.assertEqual(config.defaultGroupLeader, "")


if __name__ == "__main__":
    unittest.main()
