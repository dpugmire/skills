import os
import stat
import tempfile
import unittest
from pathlib import Path

from vh_core.models import Attachment, InboundMessage
from vh_core.spool import SpoolStore


class SpoolStoreTests(unittest.TestCase):
    def test_bundle_is_private_and_sanitizes_attachment_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            message = InboundMessage(
                messageId="m1",
                threadId="t1",
                senderName="Grace Hopper",
                senderAddress="grace@example.test",
                subject="Talk",
                receivedAt="2026-09-01T12:00:00+00:00",
                text="I gave a talk.",
                rfcMessageId="<m1@example.test>",
                references="",
                attachments=[
                    Attachment("../../agenda.pdf", "application/pdf", b"%PDF-test")
                ],
            )
            spool = SpoolStore(root / "spool")
            manifestPath = spool.writeBundle("VH-ABC123DEF4", "new", message, message)
            manifest = spool.readBundle(manifestPath)
            attachmentPath = manifestPath.parent / manifest["source"]["attachments"][0]["path"]
            self.assertEqual(attachmentPath.parent, manifestPath.parent / "source_attachments")
            self.assertEqual(attachmentPath.read_bytes(), b"%PDF-test")
            self.assertNotIn("..", attachmentPath.name)
            self.assertEqual(stat.S_IMODE(manifestPath.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(attachmentPath.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(spool.root.stat().st_mode), 0o700)
            self.assertFalse(os.access(root / "agenda.pdf", os.F_OK))


if __name__ == "__main__":
    unittest.main()
