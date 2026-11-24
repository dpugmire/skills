import sqlite3
import tempfile
import unittest
from pathlib import Path

from vh_core.state import StateStore


class StateStoreTests(unittest.TestCase):
    def test_migrates_pre_spool_schema_without_dropping_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE submissions (
                    id TEXT PRIMARY KEY,
                    source_message_id TEXT NOT NULL UNIQUE,
                    thread_id TEXT NOT NULL,
                    sender_address TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    has_attachments INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    current_revision INTEGER NOT NULL DEFAULT 0,
                    pending_rows_json TEXT,
                    confirmation_message_id TEXT,
                    committed_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE revisions (
                    submission_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    result_json TEXT NOT NULL,
                    feedback TEXT NOT NULL,
                    approval_message_id TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (submission_id, revision)
                );
                CREATE TABLE processed_messages (
                    message_id TEXT PRIMARY KEY,
                    submission_id TEXT,
                    outcome TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                );
                INSERT INTO submissions (
                    id, source_message_id, thread_id, sender_address, subject,
                    has_attachments, status, created_at, updated_at
                ) VALUES (
                    'VH-ABC123DEF4', 'm1', 't1', 'ada@example.test', 'Paper',
                    0, 'awaiting_approval', 'before', 'before'
                );
                """
            )
            connection.commit()
            connection.close()

            state = StateStore(path)
            submission = state.submission("VH-ABC123DEF4")
            self.assertIsNotNone(submission)
            self.assertEqual(submission["subject"], "Paper")
            self.assertIn("pending_message_id", submission)
            self.assertIn("pending_bundle_path", submission)
            self.assertEqual(submission["pending_feedback"], "")
            with sqlite3.connect(path) as connection:
                processedColumns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(processed_messages)")
                }
            self.assertIn("detail", processedColumns)
