import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional

from .csv_store import (
    applyHistoricalDirectory,
    applyOrganizationDefaults,
    appendRowsIfMissing,
    findRelatedHighlights,
    materializeRows,
    validateResult,
)
from .gmail_client import (
    LABEL_AWAITING,
    LABEL_COMMITTED,
    LABEL_FAILED,
    LABEL_IGNORED,
    LABEL_PENDING,
    LABEL_REVISION,
    GmailClient,
)
from .mail_text import (
    formatApprovalEmail,
    formatCommandHelp,
    formatConfirmationEmail,
    parseReplyCommand,
)
from .models import AppConfig, InboundMessage, JsonObject, ReplyCommand
from .spool import SpoolStore
from .state import StateStore


def submissionId(messageId: str) -> str:
    digest = hashlib.sha256(messageId.encode("utf-8")).hexdigest()[:10].upper()
    return f"VH-{digest}"


class Workflow:
    def __init__(
        self,
        config: AppConfig,
        gmail: Optional[GmailClient] = None,
        state: Optional[StateStore] = None,
        spool: Optional[SpoolStore] = None,
    ) -> None:
        self.config = config
        self.gmail = gmail or GmailClient(config)
        self.state = state or StateStore(config.stateDbPath)
        self.spool = spool or SpoolStore(config.spoolPath)

    def _successLabels(self, messageId: str, status: str) -> None:
        if status == "committed":
            self.gmail.updateLabels(
                messageId,
                add=(LABEL_COMMITTED,),
                remove=(LABEL_PENDING, LABEL_AWAITING, LABEL_REVISION, LABEL_FAILED),
                markRead=True,
            )
        elif status == "ignored":
            self.gmail.updateLabels(
                messageId,
                add=(LABEL_IGNORED,),
                remove=(
                    LABEL_PENDING,
                    LABEL_AWAITING,
                    LABEL_REVISION,
                    LABEL_COMMITTED,
                    LABEL_FAILED,
                ),
                markRead=True,
            )
        else:
            self.gmail.updateLabels(
                messageId,
                add=(LABEL_AWAITING,),
                remove=(LABEL_PENDING, LABEL_COMMITTED, LABEL_FAILED),
                markRead=True,
            )

    def _recordAndRead(
        self,
        message: InboundMessage,
        submission: Optional[Dict[str, object]],
        outcome: str,
        status: str,
    ) -> None:
        submissionValue = str(submission["id"]) if submission else None
        self.state.recordProcessed(message.messageId, submissionValue, outcome)
        self._successLabels(message.messageId, status)

    def _reject(
        self,
        message: InboundMessage,
        submission: Optional[Dict[str, object]],
        reason: str,
    ) -> Dict[str, object]:
        self.gmail.sendReply(message, message.subject, reason)
        self.state.recordProcessed(
            message.messageId, str(submission["id"]) if submission else None, "rejected"
        )
        self.gmail.updateLabels(
            message.messageId,
            add=(LABEL_IGNORED,),
            remove=(LABEL_PENDING, LABEL_FAILED),
            markRead=True,
        )
        return {"message_id": message.messageId, "outcome": "rejected", "reason": reason}

    def _queueAnalysis(
        self,
        submission: Dict[str, object],
        source: InboundMessage,
        inbound: InboundMessage,
        kind: str,
        priorResult: Optional[JsonObject] = None,
        feedback: str = "",
    ) -> Dict[str, object]:
        identifier = str(submission["id"])
        manifestPath = self.spool.writeBundle(
            identifier,
            kind,
            source,
            inbound,
            priorResult=priorResult,
            feedback=feedback,
        )
        self.state.queueAnalysis(identifier, inbound.messageId, manifestPath, feedback)
        add = (LABEL_PENDING, LABEL_REVISION) if kind == "changes" else (LABEL_PENDING,)
        self.gmail.updateLabels(
            inbound.messageId,
            add=add,
            remove=(LABEL_AWAITING, LABEL_COMMITTED, LABEL_FAILED),
            markRead=False,
        )
        return {
            "message_id": inbound.messageId,
            "submission_id": identifier,
            "outcome": "queued_for_analysis",
            "kind": kind,
            "bundle": str(manifestPath),
        }

    def _recoverStagedAnalysis(
        self, submission: Dict[str, object]
    ) -> Dict[str, object]:
        pendingMessageId = str(submission.get("pending_message_id") or "")
        pendingBundlePath = str(submission.get("pending_bundle_path") or "")
        if not pendingMessageId or not pendingBundlePath:
            return submission
        revision = self.state.revisionForInbound(
            str(submission["id"]), pendingMessageId
        )
        if revision is None or not revision.get("approval_message_id"):
            return submission
        manifest = self.spool.readBundle(Path(pendingBundlePath))
        kind = str(manifest.get("kind", "new"))
        add = (LABEL_AWAITING, LABEL_REVISION) if kind == "changes" else (LABEL_AWAITING,)
        self.gmail.updateLabels(
            pendingMessageId,
            add=add,
            remove=(LABEL_PENDING, LABEL_COMMITTED, LABEL_FAILED),
            markRead=True,
        )
        outcome = "revised" if kind == "changes" else "approval_sent"
        self.state.completeAnalysis(str(submission["id"]), pendingMessageId, outcome)
        refreshed = self.state.submission(str(submission["id"]))
        assert refreshed is not None
        return refreshed

    def _handleCommand(
        self, message: InboundMessage, command: ReplyCommand
    ) -> Dict[str, object]:
        submission = self.state.submission(command.submissionId)
        if submission is None or str(submission["thread_id"]) != message.threadId:
            return self._reject(
                message,
                None,
                "That approval identifier does not belong to this email thread. No CSV data was changed.",
            )
        if str(submission["sender_address"]).lower() != message.senderAddress.lower():
            return self._reject(
                message,
                submission,
                "Only the original submitter can approve or revise this highlight. No CSV data was changed.",
            )

        current = int(submission["current_revision"])
        if command.revision != current:
            return self._reject(
                message,
                submission,
                f"R{command.revision} is not current. The current revision is R{current}; no CSV data was changed.",
            )

        submission = self._recoverStagedAnalysis(submission)
        pendingMessageId = str(submission.get("pending_message_id") or "")
        if command.action == "APPROVE" and pendingMessageId == message.messageId:
            self.state.cancelPendingAnalysis(str(submission["id"]), message.messageId)
            submission = self.state.submission(str(submission["id"]))
            assert submission is not None
            pendingMessageId = ""
        if command.action == "CHANGES":
            if not command.feedback:
                return self._reject(
                    message,
                    submission,
                    formatCommandHelp(str(submission["id"]), current),
                )
            if str(submission["status"]) == "committed":
                return self._reject(
                    message,
                    submission,
                    "This revision was already committed. No CSV data was changed.",
                )
            if pendingMessageId:
                if pendingMessageId == message.messageId:
                    return {
                        "message_id": message.messageId,
                        "submission_id": submission["id"],
                        "outcome": "already_queued",
                    }
                return self._reject(
                    message,
                    submission,
                    "Another correction for this submission is already being analyzed. No CSV data was changed.",
                )
            prior = self.state.currentRevision(str(submission["id"]))["result"]
            original = self.gmail.getMessage(str(submission["source_message_id"]))
            return self._queueAnalysis(
                submission,
                original,
                message,
                "changes",
                priorResult=prior,
                feedback=command.feedback,
            )

        if pendingMessageId:
            return self._reject(
                message,
                submission,
                "A corrected revision is still being prepared. Wait for the next approval request before approving.",
            )
        if str(submission["status"]) not in (
            "awaiting_approval",
            "committing",
            "committed",
        ):
            return self._reject(
                message,
                submission,
                "This revision is not ready for approval. No CSV data was changed.",
            )

        revisionValue = self.state.currentRevision(str(submission["id"]))
        rows = materializeRows(
            revisionValue["result"],
            self.config.timezone,
            bool(submission["has_attachments"]),
        )
        rows = self.state.prepareCommit(str(submission["id"]), current, rows)
        appended = appendRowsIfMissing(self.config.csvPath, rows)
        self.state.finishCommit(str(submission["id"]))

        refreshed = self.state.submission(str(submission["id"]))
        assert refreshed is not None
        if not refreshed.get("confirmation_message_id"):
            confirmationId = self.gmail.sendReply(
                message,
                message.subject,
                formatConfirmationEmail(str(submission["id"]), current, len(rows)),
            )
            self.state.recordConfirmation(str(submission["id"]), confirmationId)
        self._recordAndRead(message, submission, "committed", "committed")
        return {
            "message_id": message.messageId,
            "submission_id": submission["id"],
            "outcome": "committed",
            "revision": current,
            "rows": len(rows),
            "rows_appended": appended,
        }

    def _handleNew(self, message: InboundMessage) -> Dict[str, object]:
        identifier = submissionId(message.messageId)
        submission = self.state.createSubmission(identifier, message)
        submission = self._recoverStagedAnalysis(submission)
        pendingMessageId = str(submission.get("pending_message_id") or "")
        pendingPathValue = str(submission.get("pending_bundle_path") or "")
        if pendingMessageId == message.messageId and pendingPathValue:
            pendingPath = Path(pendingPathValue)
            if pendingPath.is_file():
                return {
                    "message_id": message.messageId,
                    "submission_id": identifier,
                    "outcome": "already_queued",
                    "bundle": str(pendingPath),
                }
        if int(submission["current_revision"]) > 0:
            return self._reject(
                message,
                submission,
                formatCommandHelp(identifier, int(submission["current_revision"])),
            )
        return self._queueAnalysis(submission, message, message, "new")

    def processMessage(self, messageId: str) -> Dict[str, object]:
        message: Optional[InboundMessage] = None
        submission: Optional[Dict[str, object]] = None
        try:
            message = self.gmail.getMessage(messageId)
            submission = self.state.submissionByThread(message.threadId)
            processedOutcome = self.state.processedOutcome(message.messageId)
            if processedOutcome is not None:
                ignoredOutcomes = ("dismissed", "ignored_automation", "rejected")
                status = (
                    "ignored"
                    if processedOutcome in ignoredOutcomes or submission is None
                    else str(submission["status"])
                )
                self._successLabels(message.messageId, status)
                return {"message_id": message.messageId, "outcome": "read_recovered"}

            if message.automationGenerated or message.senderAddress == self.config.gmailAddress:
                self.state.recordProcessed(message.messageId, None, "ignored_automation")
                self.gmail.updateLabels(
                    message.messageId,
                    add=(LABEL_IGNORED,),
                    remove=(LABEL_PENDING, LABEL_FAILED),
                    markRead=True,
                )
                return {"message_id": message.messageId, "outcome": "ignored_automation"}

            isThreadReply = (
                submission is not None
                and str(submission["source_message_id"]) != message.messageId
            )
            command = parseReplyCommand(
                message.text,
                str(submission["id"]) if isThreadReply else None,
                int(submission["current_revision"]) if isThreadReply else None,
            )
            if command is not None:
                submission = self.state.submission(command.submissionId)
                return self._handleCommand(message, command)

            if isThreadReply:
                return self._reject(
                    message,
                    submission,
                    formatCommandHelp(
                        str(submission["id"]), int(submission["current_revision"])
                    ),
                )
            return self._handleNew(message)
        except Exception as error:
            identifier = str(submission["id"]) if submission else submissionId(messageId)
            self.state.recordFailure(identifier, str(error))
            try:
                self.gmail.markFailed(messageId)
            except Exception:
                pass
            raise

    def reprocessMessage(self, messageId: str) -> Dict[str, object]:
        """Reprocess one previously consumed Gmail message after a parser fix."""
        self.state.forgetProcessed(messageId)
        return self.processMessage(messageId)

    def dryRunMessage(self, messageId: str) -> Dict[str, object]:
        message = self.gmail.getMessage(messageId)
        submission = self.state.submissionByThread(message.threadId)
        isThreadReply = (
            submission is not None
            and str(submission["source_message_id"]) != message.messageId
        )
        command = parseReplyCommand(
            message.text,
            str(submission["id"]) if isThreadReply else None,
            int(submission["current_revision"]) if isThreadReply else None,
        )
        if command is not None:
            return {
                "message_id": message.messageId,
                "thread_id": message.threadId,
                "dry_run": True,
                "command": {
                    "action": command.action,
                    "submission_id": command.submissionId,
                    "revision": command.revision,
                    "feedback": command.feedback,
                },
            }
        if message.automationGenerated or message.senderAddress == self.config.gmailAddress:
            return {
                "message_id": message.messageId,
                "dry_run": True,
                "outcome": "would_ignore_automation",
            }
        return {
            "message_id": message.messageId,
            "thread_id": message.threadId,
            "dry_run": True,
            "outcome": "would_queue_for_analysis",
            "sender": message.senderAddress,
            "subject": message.subject,
            "attachments": [attachment.filename for attachment in message.attachments],
            "warnings": message.warnings,
        }

    def _preparedResult(
        self,
        result: JsonObject,
        manifest: JsonObject,
    ) -> JsonObject:
        prepared = json.loads(json.dumps(result))
        warnings: List[str] = []
        for key in ("source", "inbound"):
            message = manifest.get(key, {})
            if isinstance(message, dict):
                warnings.extend(str(value) for value in message.get("warnings", []))
        if warnings:
            current = prepared.setdefault("warnings", [])
            if not isinstance(current, list):
                raise RuntimeError("Result warnings must be a list")
            for warning in warnings:
                if warning not in current:
                    current.append(warning)
            prepared["needs_human_review"] = True
        prepared = applyHistoricalDirectory(prepared, self.config.csvPath)
        prepared = applyOrganizationDefaults(
            prepared,
            self.config.defaultSectionHead,
            self.config.defaultGroupLeader,
        )
        prepared["collaboration_suggestions"] = findRelatedHighlights(
            prepared, self.config.csvPath
        )
        validateResult(prepared)
        return prepared

    def _approvalAttachments(self, result: JsonObject) -> List[Path]:
        values = result.get("publication_artifacts", [])
        if not isinstance(values, list):
            raise RuntimeError("publication_artifacts must be a list")
        paths: List[Path] = []
        for value in values:
            path = Path(str(value)).expanduser()
            if path.suffix.lower() not in (".pptx", ".rtf"):
                raise RuntimeError(f"Unsupported approval attachment type: {path}")
            paths.append(path)
        return paths

    def stage(self, identifier: str, result: JsonObject) -> Dict[str, object]:
        submission = self.state.submission(identifier.upper())
        if submission is None:
            raise RuntimeError(f"Unknown submission: {identifier}")
        pendingMessageId = str(submission.get("pending_message_id") or "")
        pendingBundlePath = str(submission.get("pending_bundle_path") or "")
        if not pendingMessageId or not pendingBundlePath:
            raise RuntimeError(f"Submission has no pending analysis: {identifier}")

        manifestPath = Path(pendingBundlePath)
        try:
            manifest = self.spool.readBundle(manifestPath)
            if str(manifest.get("submission_id", "")) != str(submission["id"]):
                raise RuntimeError("Analysis bundle submission identifier does not match state")
            inbound = self.spool.inboundMessage(manifestPath)
            if inbound.messageId != pendingMessageId:
                raise RuntimeError("Analysis bundle inbound message does not match state")
            prepared = self._preparedResult(result, manifest)

            revisionValue = self.state.revisionForInbound(
                str(submission["id"]), pendingMessageId
            )
            if revisionValue is None:
                revision = self.state.saveRevision(
                    str(submission["id"]),
                    prepared,
                    str(submission.get("pending_feedback") or ""),
                    pendingMessageId,
                )
                revisionValue = self.state.currentRevision(str(submission["id"]))
            else:
                revision = int(revisionValue["revision"])
                if revisionValue["result"] != prepared:
                    raise RuntimeError(
                        "A different result is already staged for this inbound message"
                    )

            if not revisionValue.get("approval_message_id"):
                approvalBody = formatApprovalEmail(
                    str(submission["id"]),
                    revision,
                    str(submission["subject"]),
                    prepared,
                )
                approvalAttachments = self._approvalAttachments(prepared)
                if approvalAttachments:
                    sentId = self.gmail.sendReply(
                        inbound,
                        inbound.subject,
                        approvalBody,
                        attachments=approvalAttachments,
                    )
                else:
                    sentId = self.gmail.sendReply(inbound, inbound.subject, approvalBody)
                self.state.recordApprovalSent(str(submission["id"]), revision, sentId)

            kind = str(manifest.get("kind", "new"))
            add = (LABEL_AWAITING, LABEL_REVISION) if kind == "changes" else (LABEL_AWAITING,)
            self.gmail.updateLabels(
                pendingMessageId,
                add=add,
                remove=(LABEL_PENDING, LABEL_COMMITTED, LABEL_FAILED),
                markRead=True,
            )
            outcome = "revised" if kind == "changes" else "approval_sent"
            self.state.completeAnalysis(str(submission["id"]), pendingMessageId, outcome)
            return {
                "message_id": pendingMessageId,
                "submission_id": submission["id"],
                "outcome": outcome,
                "revision": revision,
            }
        except Exception as error:
            self.state.recordFailure(str(submission["id"]), str(error))
            try:
                self.gmail.markFailed(pendingMessageId)
            except Exception:
                pass
            raise

    def dismiss(self, identifier: str, reason: str) -> Dict[str, object]:
        reason = reason.strip()
        if not reason:
            raise RuntimeError("Dismissal reason must not be empty")

        submission = self.state.submission(identifier.upper())
        if submission is None:
            raise RuntimeError(f"Unknown submission: {identifier}")
        pendingMessageId = str(submission.get("pending_message_id") or "")
        pendingBundlePath = str(submission.get("pending_bundle_path") or "")
        if not pendingMessageId or not pendingBundlePath:
            raise RuntimeError(f"Submission has no pending analysis: {identifier}")

        manifestPath = Path(pendingBundlePath)
        manifest = self.spool.readBundle(manifestPath)
        if str(manifest.get("submission_id", "")) != str(submission["id"]):
            raise RuntimeError("Analysis bundle submission identifier does not match state")
        inbound = self.spool.inboundMessage(manifestPath)
        if inbound.messageId != pendingMessageId:
            raise RuntimeError("Analysis bundle inbound message does not match state")

        self._successLabels(pendingMessageId, "ignored")
        self.state.dismissAnalysis(
            str(submission["id"]),
            pendingMessageId,
            reason,
        )
        return {
            "message_id": pendingMessageId,
            "submission_id": submission["id"],
            "outcome": "dismissed",
            "reason": reason,
        }

    def run(self, dryRun: bool = False) -> List[Dict[str, object]]:
        values: List[Dict[str, object]] = []
        messageIds = self.gmail.pendingMessageIds(
            self.config.maxMessagesPerRun, createLabels=not dryRun
        )
        for messageId in messageIds:
            try:
                value = self.dryRunMessage(messageId) if dryRun else self.processMessage(messageId)
                values.append(value)
            except Exception as error:
                values.append(
                    {
                        "message_id": messageId,
                        "outcome": "failed",
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
        return values
