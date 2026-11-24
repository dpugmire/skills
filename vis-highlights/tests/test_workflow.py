import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from vh_core.csv_store import validateCsv
from vh_core.gmail_client import LABEL_IGNORED
from vh_core.models import AppConfig, CSV_COLUMNS, InboundMessage
from vh_core.state import StateStore
from vh_core.workflow import Workflow, submissionId


def _result(title="A useful paper"):
    return {
        "needs_human_review": False,
        "warnings": [],
        "highlights": [
            {
                "employee": "Ada Lovelace",
                "section_head": "Section Person",
                "group_leader": "Group Person",
                "category": "Publication",
                "title": title,
                "details": "Ada Lovelace published a paper with Charles Babbage.",
                "url": "https://example.test/paper",
                "dates": "August 2026",
                "location": "",
                "admin": "Admin Person",
                "source_urls": ["https://example.test/paper"],
                "uncertainty_notes": [],
            }
        ],
    }


class _Gmail:
    def __init__(self):
        self.messages = {}
        self.sent = []
        self.updates = []
        self.failNextUpdateFor = None

    def getMessage(self, messageId):
        return self.messages[messageId]

    def sendReply(self, message, subject, body):
        identifier = f"sent-{len(self.sent) + 1}"
        self.sent.append((identifier, message.messageId, subject, body))
        return identifier

    def updateLabels(self, messageId, add=(), remove=(), markRead=False):
        if self.failNextUpdateFor == messageId:
            self.failNextUpdateFor = None
            raise RuntimeError("label update failed")
        self.updates.append((messageId, tuple(add), tuple(remove), markRead))

    def markFailed(self, messageId):
        self.updates.append((messageId, ("failed",), (), False))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.csvPath = root / "report.csv"
        with self.csvPath.open("w", encoding="utf-8-sig", newline="") as stream:
            csv.writer(stream, quoting=csv.QUOTE_ALL, lineterminator="\r\n").writerow(
                CSV_COLUMNS
            )
        self.config = AppConfig(
            gmailAddress="vishighlights@gmail.com",
            csvPath=self.csvPath,
            googleCredentialsPath=root / "credentials.json",
            googleTokenPath=root / "token.json",
            stateDbPath=root / "state.sqlite3",
            spoolPath=root / "spool",
            defaultSectionHead="Rafael DaSilva",
            defaultGroupLeader="David Pugmire",
        )
        self.gmail = _Gmail()
        self.state = StateStore(self.config.stateDbPath)
        self.workflow = Workflow(self.config, gmail=self.gmail, state=self.state)

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def _message(messageId, text, thread="thread-1"):
        return InboundMessage(
            messageId=messageId,
            threadId=thread,
            senderName="Ada Lovelace",
            senderAddress="ada@example.test",
            subject="New highlight",
            receivedAt="2026-09-01T12:00:00+00:00",
            text=text,
            rfcMessageId=f"<{messageId}@example.test>",
            references="",
        )

    def test_approval_gate_and_idempotent_commit(self):
        original = self._message("original-1", "I published a paper.")
        self.gmail.messages[original.messageId] = original
        first = self.workflow.processMessage(original.messageId)
        self.assertEqual(first["outcome"], "queued_for_analysis")
        self.assertEqual(validateCsv(self.csvPath), 0)
        self.assertFalse(self.gmail.updates[-1][-1])

        identifier = submissionId(original.messageId)
        staged = self.workflow.stage(identifier, _result())
        self.assertEqual(staged["outcome"], "approval_sent")
        self.assertEqual(staged["revision"], 1)
        self.assertTrue(self.gmail.updates[-1][-1])
        self.assertEqual(validateCsv(self.csvPath), 0)

        approval = self._message("approval-1", f"APPROVE {identifier} R1")
        self.gmail.messages[approval.messageId] = approval
        committed = self.workflow.processMessage(approval.messageId)
        self.assertEqual(committed["rows_appended"], 1)
        self.assertEqual(validateCsv(self.csvPath), 1)
        self.assertTrue(self.gmail.updates[-1][-1])

        duplicate = self._message("approval-2", f"APPROVE {identifier} R1")
        self.gmail.messages[duplicate.messageId] = duplicate
        retried = self.workflow.processMessage(duplicate.messageId)
        self.assertEqual(retried["rows_appended"], 0)
        self.assertEqual(validateCsv(self.csvPath), 1)
        self.assertEqual(len(self.gmail.sent), 2)

    def test_stage_fills_configured_organization_defaults(self):
        original = self._message("organization-1", "I published a paper.")
        self.gmail.messages[original.messageId] = original
        identifier = submissionId(original.messageId)
        self.workflow.processMessage(original.messageId)
        result = _result()
        result["highlights"][0]["section_head"] = ""
        result["highlights"][0]["group_leader"] = ""

        self.workflow.stage(identifier, result)

        prepared = self.state.currentRevision(identifier)["result"]["highlights"][0]
        self.assertEqual(prepared["section_head"], "Rafael DaSilva")
        self.assertEqual(prepared["group_leader"], "David Pugmire")
        self.assertIn("Section Head: Rafael DaSilva", self.gmail.sent[-1][3])
        self.assertIn("Group Leader: David Pugmire", self.gmail.sent[-1][3])

    def test_approval_includes_recent_related_work_for_other_employees(self):
        with self.csvPath.open("a", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
            writer.writerow({
                **{column: "" for column in CSV_COLUMNS},
                "Employee": "Grace Hopper",
                "Category": "Publication",
                "Title": "GPU visualization of correlated uncertainty",
                "Details": "A visualization method for correlated uncertainty in scientific data.",
                "URL": "https://example.test/related",
                "Dates": "September 2026",
            })
        original = self._message("related-original", "I published a paper.")
        self.gmail.messages[original.messageId] = original
        self.workflow.processMessage(original.messageId)
        identifier = submissionId(original.messageId)
        result = _result()
        result["highlights"][0]["details"] = (
            "Ada Lovelace published a GPU visualization study of correlated uncertainty."
        )
        self.workflow.stage(identifier, result)
        body = self.gmail.sent[-1][3]
        self.assertIn("FYI: Potentially related work", body)
        self.assertIn("Grace Hopper", body)
        self.assertIn("https://example.test/related", body)

    def test_related_work_includes_same_employee_but_skips_non_reportable_categories(self):
        from vh_core.csv_store import findRelatedHighlights

        with self.csvPath.open("a", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
            writer.writerow({
                **{column: "" for column in CSV_COLUMNS},
                "Employee": "Ada Lovelace",
                "Category": "Publication",
                "Title": "GPU visualization of correlated uncertainty",
                "Details": "A visualization method for correlated uncertainty in scientific data.",
                "Dates": "September 2026",
            })
            writer.writerow({
                **{column: "" for column in CSV_COLUMNS},
                "Employee": "Grace Hopper",
                "Category": "Honor/Award",
                "Title": "GPU visualization of correlated uncertainty",
                "Details": "A visualization method for correlated uncertainty in scientific data.",
                "Dates": "September 2026",
            })
        result = _result()
        result["highlights"][0]["title"] = "GPU visualization of correlated uncertainty"
        result["highlights"][0]["details"] = (
            "Ada Lovelace published a GPU visualization study of correlated uncertainty."
        )
        suggestions = findRelatedHighlights(result, self.csvPath)
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["employee"], "Ada Lovelace")

    def test_related_work_includes_project_activity(self):
        from vh_core.csv_store import findRelatedHighlights

        with self.csvPath.open("a", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, quoting=csv.QUOTE_ALL)
            writer.writerow({
                **{column: "" for column in CSV_COLUMNS},
                "Employee": "Grace Hopper",
                "Category": "Project",
                "Title": "LaserNetUS scientist meeting",
                "Details": "Met with scientists on the LaserNetUS project.",
                "Dates": "September 2026",
            })
        result = _result("LaserNetUS scientist meeting")
        result["highlights"][0]["details"] = "Met with scientists on the LaserNetUS project."
        suggestions = findRelatedHighlights(result, self.csvPath)
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["employee"], "Grace Hopper")

    def test_correction_creates_new_revision_without_csv_write(self):
        original = self._message("original-2", "I published a paper.")
        self.gmail.messages[original.messageId] = original
        self.workflow.processMessage(original.messageId)
        identifier = submissionId(original.messageId)
        self.workflow.stage(identifier, _result())
        correction = self._message(
            "change-1", f"CHANGES {identifier} R1\nUse the final title."
        )
        self.gmail.messages[correction.messageId] = correction
        result = self.workflow.processMessage(correction.messageId)
        self.assertEqual(result["outcome"], "queued_for_analysis")
        self.assertEqual(result["kind"], "changes")
        self.assertFalse(self.gmail.updates[-1][-1])
        staged = self.workflow.stage(identifier, _result("Corrected paper"))
        self.assertEqual(staged["outcome"], "revised")
        self.assertEqual(staged["revision"], 2)
        self.assertEqual(validateCsv(self.csvPath), 0)
        self.assertTrue(self.gmail.updates[-1][-1])

    def test_short_approval_infers_submission_and_revision_from_thread(self):
        original = self._message("short-original", "I published a paper.")
        self.gmail.messages[original.messageId] = original
        self.workflow.processMessage(original.messageId)
        identifier = submissionId(original.messageId)
        self.workflow.stage(identifier, _result())

        approval = self._message("short-approval", "approve")
        self.gmail.messages[approval.messageId] = approval
        result = self.workflow.processMessage(approval.messageId)

        self.assertEqual(result["outcome"], "committed")
        self.assertEqual(result["submission_id"], identifier)
        self.assertEqual(result["revision"], 1)
        self.assertEqual(validateCsv(self.csvPath), 1)

    def test_short_approval_recovers_if_previously_queued_as_correction(self):
        original = self._message("recovery-original", "I published a paper.")
        self.gmail.messages[original.messageId] = original
        self.workflow.processMessage(original.messageId)
        identifier = submissionId(original.messageId)
        self.workflow.stage(identifier, _result())

        approval = self._message(
            "recovery-approval",
            "approve\n\nOn Wed, Sep 2, 2026 at 10:55 AM Person <person@example.test>\n"
            "wrote:\n\n> old message",
        )
        self.gmail.messages[approval.messageId] = approval
        self.state.queueAnalysis(
            identifier,
            approval.messageId,
            Path(self.temporary.name) / "misclassified-bundle.json",
            approval.text,
        )

        result = self.workflow.processMessage(approval.messageId)

        self.assertEqual(result["outcome"], "committed")
        self.assertEqual(result["revision"], 1)
        self.assertEqual(validateCsv(self.csvPath), 1)
        self.assertIsNone(self.state.submission(identifier)["pending_message_id"])

    def test_natural_language_reply_queues_correction_from_thread(self):
        original = self._message("natural-original", "I published a paper.")
        self.gmail.messages[original.messageId] = original
        self.workflow.processMessage(original.messageId)
        identifier = submissionId(original.messageId)
        self.workflow.stage(identifier, _result())

        correction = self._message(
            "natural-correction", "change the date to August 27 2026"
        )
        self.gmail.messages[correction.messageId] = correction
        result = self.workflow.processMessage(correction.messageId)

        self.assertEqual(result["outcome"], "queued_for_analysis")
        self.assertEqual(result["kind"], "changes")
        pending = self.state.pendingAnalyses()[0]
        self.assertEqual(pending["pending_feedback"], "change the date to August 27 2026")
        self.assertEqual(validateCsv(self.csvPath), 0)

    def test_short_approval_from_wrong_sender_is_rejected(self):
        original = self._message("sender-original", "I published a paper.")
        self.gmail.messages[original.messageId] = original
        self.workflow.processMessage(original.messageId)
        identifier = submissionId(original.messageId)
        self.workflow.stage(identifier, _result())

        approval = self._message("wrong-sender", "approve")
        approval = InboundMessage(
            **{
                **approval.__dict__,
                "senderAddress": "mallory@example.test",
            }
        )
        self.gmail.messages[approval.messageId] = approval
        result = self.workflow.processMessage(approval.messageId)

        self.assertEqual(result["outcome"], "rejected")
        self.assertIn("Only the original submitter", result["reason"])
        self.assertEqual(validateCsv(self.csvPath), 0)

    def test_invalid_stage_stays_unread_and_does_not_write_csv(self):
        original = self._message("original-3", "I published a paper.")
        self.gmail.messages[original.messageId] = original
        self.workflow.processMessage(original.messageId)
        with self.assertRaisesRegex(RuntimeError, "at least one highlight"):
            self.workflow.stage(submissionId(original.messageId), {"highlights": []})
        self.assertEqual(validateCsv(self.csvPath), 0)
        self.assertEqual(self.gmail.updates[-1], (original.messageId, ("failed",), (), False))

    def test_approval_is_rejected_while_correction_is_pending(self):
        original = self._message("original-4", "I published a paper.")
        self.gmail.messages[original.messageId] = original
        identifier = submissionId(original.messageId)
        self.workflow.processMessage(original.messageId)
        self.workflow.stage(identifier, _result())

        correction = self._message(
            "change-4", f"CHANGES {identifier} R1\nUse the final title."
        )
        self.gmail.messages[correction.messageId] = correction
        self.workflow.processMessage(correction.messageId)
        approval = self._message("approval-4", f"APPROVE {identifier} R1")
        self.gmail.messages[approval.messageId] = approval
        result = self.workflow.processMessage(approval.messageId)
        self.assertEqual(result["outcome"], "rejected")
        self.assertEqual(validateCsv(self.csvPath), 0)

    def test_stage_retry_does_not_resend_approval(self):
        original = self._message("original-5", "I published a paper.")
        self.gmail.messages[original.messageId] = original
        identifier = submissionId(original.messageId)
        self.workflow.processMessage(original.messageId)

        self.gmail.failNextUpdateFor = original.messageId
        with self.assertRaisesRegex(RuntimeError, "label update failed"):
            self.workflow.stage(identifier, _result())
        self.assertEqual(len(self.gmail.sent), 1)

        result = self.workflow.stage(identifier, _result())
        self.assertEqual(result["outcome"], "approval_sent")
        self.assertEqual(len(self.gmail.sent), 1)
        self.assertEqual(self.state.pendingAnalyses(), [])

    def test_approval_recovers_after_stage_label_failure(self):
        original = self._message("original-6", "I published a paper.")
        self.gmail.messages[original.messageId] = original
        identifier = submissionId(original.messageId)
        self.workflow.processMessage(original.messageId)

        self.gmail.failNextUpdateFor = original.messageId
        with self.assertRaisesRegex(RuntimeError, "label update failed"):
            self.workflow.stage(identifier, _result())

        approval = self._message("approval-6", f"APPROVE {identifier} R1")
        self.gmail.messages[approval.messageId] = approval
        result = self.workflow.processMessage(approval.messageId)
        self.assertEqual(result["outcome"], "committed")
        self.assertEqual(result["rows_appended"], 1)
        self.assertEqual(validateCsv(self.csvPath), 1)
        self.assertEqual(self.state.pendingAnalyses(), [])

    def test_dismiss_new_submission_marks_read_without_writing_csv(self):
        original = self._message("original-7", "This is not a highlight.")
        self.gmail.messages[original.messageId] = original
        identifier = submissionId(original.messageId)
        queued = self.workflow.processMessage(original.messageId)
        bundlePath = Path(queued["bundle"])

        result = self.workflow.dismiss(identifier, "Not a reportable activity")

        self.assertEqual(result["outcome"], "dismissed")
        self.assertEqual(self.state.submission(identifier)["status"], "ignored")
        self.assertEqual(self.state.pendingAnalyses(), [])
        self.assertTrue(self.state.isProcessed(original.messageId))
        self.assertTrue(bundlePath.is_file())
        self.assertEqual(validateCsv(self.csvPath), 0)
        self.assertEqual(self.gmail.sent, [])
        self.assertEqual(
            self.gmail.updates[-1],
            (
                original.messageId,
                (LABEL_IGNORED,),
                (
                    "VisHighlights/Pending Analysis",
                    "VisHighlights/Awaiting Approval",
                    "VisHighlights/Revision Requested",
                    "VisHighlights/Committed",
                    "VisHighlights/Failed",
                ),
                True,
            ),
        )
        with sqlite3.connect(self.config.stateDbPath) as connection:
            outcome, detail = connection.execute(
                "SELECT outcome, detail FROM processed_messages WHERE message_id = ?",
                (original.messageId,),
            ).fetchone()
        self.assertEqual(outcome, "dismissed")
        self.assertEqual(detail, "Not a reportable activity")

    def test_dismiss_correction_restores_previous_approval_state(self):
        original = self._message("original-8", "I published a paper.")
        self.gmail.messages[original.messageId] = original
        identifier = submissionId(original.messageId)
        self.workflow.processMessage(original.messageId)
        self.workflow.stage(identifier, _result())

        correction = self._message(
            "change-8", f"CHANGES {identifier} R1\nNever mind."
        )
        self.gmail.messages[correction.messageId] = correction
        self.workflow.processMessage(correction.messageId)
        self.workflow.dismiss(identifier, "Correction does not require a new revision")

        submission = self.state.submission(identifier)
        self.assertEqual(submission["status"], "awaiting_approval")
        self.assertEqual(submission["current_revision"], 1)
        self.assertIsNone(submission["pending_message_id"])
        self.assertEqual(self.state.pendingAnalyses(), [])
        self.assertEqual(validateCsv(self.csvPath), 0)
        self.assertEqual(len(self.gmail.sent), 1)
        self.assertEqual(self.gmail.updates[-1][1], (LABEL_IGNORED,))
        self.assertTrue(self.gmail.updates[-1][-1])

        recovered = self.workflow.processMessage(correction.messageId)
        self.assertEqual(recovered["outcome"], "read_recovered")
        self.assertEqual(self.gmail.updates[-1][1], (LABEL_IGNORED,))
        self.assertTrue(self.gmail.updates[-1][-1])


if __name__ == "__main__":
    unittest.main()
