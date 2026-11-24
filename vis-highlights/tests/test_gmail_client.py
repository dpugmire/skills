import base64
import tempfile
import unittest
from pathlib import Path

from vh_core.gmail_client import GmailClient
from vh_core.models import AppConfig


def _encoded(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


class _Request:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class _Attachments:
    def get(self, **kwargs):
        return _Request({"data": _encoded(b"%PDF-attachment")})


class _Messages:
    def __init__(self, message):
        self.message = message

    def get(self, **kwargs):
        return _Request(self.message)

    def attachments(self):
        return _Attachments()


class _Users:
    def __init__(self, message):
        self.message = message

    def messages(self):
        return _Messages(self.message)


class _Service:
    def __init__(self, message):
        self.message = message

    def users(self):
        return _Users(self.message)


class GmailClientTests(unittest.TestCase):
    def test_extracts_plain_text_and_remote_attachment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = AppConfig(
                gmailAddress="vishighlights@gmail.com",
                csvPath=root / "report.csv",
                googleCredentialsPath=root / "credentials.json",
                googleTokenPath=root / "token.json",
                stateDbPath=root / "state.sqlite3",
                spoolPath=root / "spool",
            )
            raw = {
                "id": "message-1",
                "threadId": "thread-1",
                "internalDate": "1788264000000",
                "labelIds": ["INBOX", "UNREAD"],
                "payload": {
                    "mimeType": "multipart/mixed",
                    "headers": [
                        {"name": "From", "value": "Ada Lovelace <ada@example.test>"},
                        {"name": "Subject", "value": "A publication"},
                        {"name": "Message-ID", "value": "<message-1@example.test>"},
                    ],
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "filename": "",
                            "body": {"data": _encoded(b"I published a paper.")},
                        },
                        {
                            "mimeType": "application/pdf",
                            "filename": "paper.pdf",
                            "body": {"attachmentId": "attachment-1"},
                        },
                    ],
                },
            }
            gmail = GmailClient.__new__(GmailClient)
            gmail.config = config
            gmail.service = _Service(raw)
            gmail._labelIds = None
            message = gmail.getMessage("message-1")
            self.assertEqual(message.senderAddress, "ada@example.test")
            self.assertEqual(message.text, "I published a paper.")
            self.assertEqual(message.attachments[0].filename, "paper.pdf")
            self.assertEqual(message.attachments[0].data, b"%PDF-attachment")


if __name__ == "__main__":
    unittest.main()
