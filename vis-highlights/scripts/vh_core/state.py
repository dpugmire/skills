import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence

from .models import InboundMessage, JsonObject


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._initialize()
        os.chmod(path, 0o600)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS submissions (
                    id TEXT PRIMARY KEY,
                    source_message_id TEXT NOT NULL UNIQUE,
                    thread_id TEXT NOT NULL,
                    sender_address TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    has_attachments INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    current_revision INTEGER NOT NULL DEFAULT 0,
                    pending_message_id TEXT,
                    pending_bundle_path TEXT,
                    pending_feedback TEXT NOT NULL DEFAULT '',
                    pending_rows_json TEXT,
                    confirmation_message_id TEXT,
                    committed_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS submissions_thread_id
                    ON submissions(thread_id);
                CREATE TABLE IF NOT EXISTS revisions (
                    submission_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    result_json TEXT NOT NULL,
                    feedback TEXT NOT NULL,
                    inbound_message_id TEXT,
                    approval_message_id TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (submission_id, revision),
                    FOREIGN KEY (submission_id) REFERENCES submissions(id)
                );
                CREATE TABLE IF NOT EXISTS processed_messages (
                    message_id TEXT PRIMARY KEY,
                    submission_id TEXT,
                    outcome TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    processed_at TEXT NOT NULL
                );
                """
            )
            submissionColumns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(submissions)")
            }
            for name, declaration in (
                ("pending_message_id", "TEXT"),
                ("pending_bundle_path", "TEXT"),
                ("pending_feedback", "TEXT NOT NULL DEFAULT ''"),
            ):
                if name not in submissionColumns:
                    connection.execute(
                        f"ALTER TABLE submissions ADD COLUMN {name} {declaration}"
                    )
            revisionColumns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(revisions)")
            }
            if "inbound_message_id" not in revisionColumns:
                connection.execute(
                    "ALTER TABLE revisions ADD COLUMN inbound_message_id TEXT"
                )
            processedColumns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(processed_messages)")
            }
            if "detail" not in processedColumns:
                connection.execute(
                    "ALTER TABLE processed_messages "
                    "ADD COLUMN detail TEXT NOT NULL DEFAULT ''"
                )

    @staticmethod
    def _row(row: Optional[sqlite3.Row]) -> Optional[Dict[str, object]]:
        return dict(row) if row is not None else None

    def createSubmission(self, submissionId: str, message: InboundMessage) -> Dict[str, object]:
        now = _now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO submissions (
                    id, source_message_id, thread_id, sender_address, subject,
                    has_attachments, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'awaiting_analysis', ?, ?)
                """,
                (
                    submissionId,
                    message.messageId,
                    message.threadId,
                    message.senderAddress.lower(),
                    message.subject,
                    1 if message.attachments else 0,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM submissions WHERE source_message_id = ?",
                (message.messageId,),
            ).fetchone()
            assert row is not None
            return dict(row)

    def queueAnalysis(
        self,
        submissionId: str,
        messageId: str,
        bundlePath: Path,
        feedback: str,
    ) -> None:
        now = _now()
        with self._connection() as connection:
            updated = connection.execute(
                """
                UPDATE submissions
                SET status = 'awaiting_analysis', pending_message_id = ?,
                    pending_bundle_path = ?, pending_feedback = ?, last_error = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (messageId, str(bundlePath), feedback, now, submissionId),
            )
            if updated.rowcount != 1:
                raise RuntimeError(f"Unknown submission: {submissionId}")

    def pendingAnalyses(self) -> List[Dict[str, object]]:
        with self._connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT id, status, current_revision, sender_address, subject,
                           pending_message_id, pending_bundle_path, pending_feedback,
                           last_error, created_at, updated_at
                    FROM submissions
                    WHERE pending_message_id IS NOT NULL
                      AND pending_bundle_path IS NOT NULL
                    ORDER BY updated_at, id
                    """
                ).fetchall()
            ]

    def submission(self, submissionId: str) -> Optional[Dict[str, object]]:
        with self._connection() as connection:
            return self._row(
                connection.execute(
                    "SELECT * FROM submissions WHERE id = ?", (submissionId,)
                ).fetchone()
            )

    def submissionByThread(self, threadId: str) -> Optional[Dict[str, object]]:
        with self._connection() as connection:
            return self._row(
                connection.execute(
                    "SELECT * FROM submissions WHERE thread_id = ? ORDER BY created_at DESC LIMIT 1",
                    (threadId,),
                ).fetchone()
            )

    def submissionBySource(self, messageId: str) -> Optional[Dict[str, object]]:
        with self._connection() as connection:
            return self._row(
                connection.execute(
                    "SELECT * FROM submissions WHERE source_message_id = ?", (messageId,)
                ).fetchone()
            )

    def saveRevision(
        self,
        submissionId: str,
        result: JsonObject,
        feedback: str,
        inboundMessageId: str,
    ) -> int:
        now = _now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT current_revision, pending_message_id
                FROM submissions WHERE id = ?
                """,
                (submissionId,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Unknown submission: {submissionId}")
            if str(row["pending_message_id"] or "") != inboundMessageId:
                raise RuntimeError(
                    f"Message {inboundMessageId} is not pending for {submissionId}"
                )
            revision = int(row["current_revision"]) + 1
            connection.execute(
                """
                INSERT INTO revisions (
                    submission_id, revision, result_json, feedback,
                    inbound_message_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    submissionId,
                    revision,
                    json.dumps(result, sort_keys=True),
                    feedback,
                    inboundMessageId,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE submissions
                SET current_revision = ?, status = 'draft_ready', pending_rows_json = NULL,
                    last_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (revision, now, submissionId),
            )
            return revision

    def revisionForInbound(
        self, submissionId: str, inboundMessageId: str
    ) -> Optional[Dict[str, object]]:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM revisions
                WHERE submission_id = ? AND inbound_message_id = ?
                ORDER BY revision DESC LIMIT 1
                """,
                (submissionId, inboundMessageId),
            ).fetchone()
            if row is None:
                return None
            value = dict(row)
            value["result"] = json.loads(str(value.pop("result_json")))
            return value

    def currentRevision(self, submissionId: str) -> Dict[str, object]:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT r.* FROM revisions r
                JOIN submissions s ON s.id = r.submission_id
                WHERE s.id = ? AND r.revision = s.current_revision
                """,
                (submissionId,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Submission has no revision: {submissionId}")
            value = dict(row)
            value["result"] = json.loads(str(value.pop("result_json")))
            return value

    def recordApprovalSent(self, submissionId: str, revision: int, messageId: str) -> None:
        now = _now()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE revisions SET approval_message_id = ?
                WHERE submission_id = ? AND revision = ?
                """,
                (messageId, submissionId, revision),
            )
            connection.execute(
                """
                UPDATE submissions SET status = 'awaiting_approval', updated_at = ?
                WHERE id = ? AND current_revision = ?
                """,
                (now, submissionId, revision),
            )

    def completeAnalysis(
        self,
        submissionId: str,
        inboundMessageId: str,
        outcome: str,
    ) -> None:
        now = _now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT pending_message_id FROM submissions WHERE id = ?",
                (submissionId,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Unknown submission: {submissionId}")
            pending = str(row["pending_message_id"] or "")
            if pending and pending != inboundMessageId:
                raise RuntimeError(
                    f"Message {inboundMessageId} is no longer pending for {submissionId}"
                )
            connection.execute(
                """
                INSERT OR REPLACE INTO processed_messages (
                    message_id, submission_id, outcome, processed_at
                ) VALUES (?, ?, ?, ?)
                """,
                (inboundMessageId, submissionId, outcome, now),
            )
            connection.execute(
                """
                UPDATE submissions
                SET pending_message_id = NULL, pending_bundle_path = NULL,
                    pending_feedback = '', last_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, submissionId),
            )

    def dismissAnalysis(
        self,
        submissionId: str,
        inboundMessageId: str,
        reason: str,
    ) -> None:
        now = _now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT current_revision, pending_message_id "
                "FROM submissions WHERE id = ?",
                (submissionId,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Unknown submission: {submissionId}")
            if str(row["pending_message_id"] or "") != inboundMessageId:
                raise RuntimeError(
                    f"Message {inboundMessageId} is not pending for {submissionId}"
                )
            connection.execute(
                """
                INSERT OR REPLACE INTO processed_messages (
                    message_id, submission_id, outcome, detail, processed_at
                ) VALUES (?, ?, 'dismissed', ?, ?)
                """,
                (inboundMessageId, submissionId, reason, now),
            )
            connection.execute(
                """
                UPDATE submissions
                SET status = CASE
                        WHEN current_revision = 0 THEN 'ignored'
                        ELSE 'awaiting_approval'
                    END,
                    pending_message_id = NULL, pending_bundle_path = NULL,
                    pending_feedback = '', last_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, submissionId),
            )

    def cancelPendingAnalysis(self, submissionId: str, inboundMessageId: str) -> None:
        now = _now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT current_revision, pending_message_id "
                "FROM submissions WHERE id = ?",
                (submissionId,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Unknown submission: {submissionId}")
            if int(row["current_revision"]) < 1:
                raise RuntimeError(f"Submission has no revision: {submissionId}")
            if str(row["pending_message_id"] or "") != inboundMessageId:
                raise RuntimeError(
                    f"Message {inboundMessageId} is not pending for {submissionId}"
                )
            connection.execute(
                """
                UPDATE submissions
                SET status = 'awaiting_approval', pending_message_id = NULL,
                    pending_bundle_path = NULL, pending_feedback = '',
                    last_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, submissionId),
            )

    def prepareCommit(self, submissionId: str, revision: int, rows: Sequence[Dict[str, str]]) -> List[Dict[str, str]]:
        now = _now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM submissions WHERE id = ?", (submissionId,)
            ).fetchone()
            if row is None:
                raise RuntimeError(f"Unknown submission: {submissionId}")
            if int(row["current_revision"]) != revision:
                raise RuntimeError(
                    f"Revision R{revision} is stale; current revision is R{row['current_revision']}"
                )
            if row["status"] == "committed":
                pending = row["pending_rows_json"]
                return json.loads(str(pending)) if pending else []
            pending = row["pending_rows_json"]
            materialized = json.loads(str(pending)) if pending else list(rows)
            connection.execute(
                """
                UPDATE submissions
                SET status = 'committing', pending_rows_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(materialized, sort_keys=True), now, submissionId),
            )
            return materialized

    def finishCommit(self, submissionId: str) -> None:
        now = _now()
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE submissions
                SET status = 'committed', committed_at = ?, last_error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, now, submissionId),
            )

    def recordConfirmation(self, submissionId: str, messageId: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE submissions SET confirmation_message_id = ?, updated_at = ? WHERE id = ?",
                (messageId, _now(), submissionId),
            )

    def recordFailure(self, submissionId: Optional[str], error: str) -> None:
        if not submissionId:
            return
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE submissions
                SET status = CASE
                        WHEN status IN (
                            'processing', 'awaiting_analysis', 'draft_ready', 'failed'
                        ) THEN 'failed'
                        ELSE status
                    END,
                    last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (error[:4000], _now(), submissionId),
            )

    def processedOutcome(self, messageId: str) -> Optional[str]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT outcome FROM processed_messages WHERE message_id = ?",
                (messageId,),
            ).fetchone()
            return str(row["outcome"]) if row is not None else None

    def isProcessed(self, messageId: str) -> bool:
        return self.processedOutcome(messageId) is not None

    def forgetProcessed(self, messageId: str) -> None:
        """Allow an operator to safely reprocess a previously consumed message."""
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM processed_messages WHERE message_id = ?",
                (messageId,),
            )

    def recordProcessed(self, messageId: str, submissionId: Optional[str], outcome: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO processed_messages (
                    message_id, submission_id, outcome, processed_at
                ) VALUES (?, ?, ?, ?)
                """,
                (messageId, submissionId, outcome, _now()),
            )
            if submissionId:
                connection.execute(
                    "UPDATE submissions SET last_error = NULL, updated_at = ? WHERE id = ?",
                    (_now(), submissionId),
                )

    def summary(self) -> List[Dict[str, object]]:
        with self._connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT id, status, current_revision, sender_address, subject,
                           pending_message_id, pending_bundle_path,
                           created_at, updated_at, committed_at, last_error
                    FROM submissions ORDER BY created_at DESC
                    """
                ).fetchall()
            ]
