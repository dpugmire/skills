import unittest

from vh_core.mail_text import newReplyText, parseReplyCommand


class MailTextTests(unittest.TestCase):
    def test_approval_command_must_be_first_fresh_line(self):
        command = parseReplyCommand(
            "APPROVE VH-ABC123DEF4 R2\n\nOn Tue, Person wrote:\nAPPROVE VH-ABC123DEF4 R1"
        )
        self.assertIsNotNone(command)
        self.assertEqual(command.action, "APPROVE")
        self.assertEqual(command.revision, 2)

    def test_quoted_command_is_ignored(self):
        self.assertIsNone(
            parseReplyCommand("Sounds good\n\nOn Tue, Person wrote:\nAPPROVE VH-ABC123DEF4 R1")
        )

    def test_changes_capture_only_fresh_feedback(self):
        command = parseReplyCommand(
            "CHANGES VH-ABC123DEF4 R3\nUse the journal publication date.\n> old text"
        )
        self.assertIsNotNone(command)
        self.assertEqual(command.feedback, "Use the journal publication date.")

    def test_short_approval_uses_thread_context(self):
        command = parseReplyCommand("approve", "VH-ABC123DEF4", 4)
        self.assertIsNotNone(command)
        self.assertEqual(command.action, "APPROVE")
        self.assertEqual(command.submissionId, "VH-ABC123DEF4")
        self.assertEqual(command.revision, 4)

    def test_short_approval_ignores_standard_signature(self):
        command = parseReplyCommand(
            "APPROVE\n\n-- \nAda Lovelace", "VH-ABC123DEF4", 2
        )
        self.assertIsNotNone(command)
        self.assertEqual(command.action, "APPROVE")

    def test_short_approval_ignores_outlook_underscore_separator(self):
        command = parseReplyCommand(
            "Approve\n\n____________________________\n"
            "From: Vis Highlights <vishighlights@gmail.com>\n"
            "Subject: Re: Junghoon's highlights",
            "VH-ABC123DEF4",
            2,
        )
        self.assertIsNotNone(command)
        self.assertEqual(command.action, "APPROVE")

    def test_short_approval_ignores_wrapped_gmail_quote_marker(self):
        command = parseReplyCommand(
            "approve\n\nOn Wed, Sep 2, 2026 at 10:55 AM Person <person@example.test>\n"
            "wrote:\n\n> old message",
            "VH-ABC123DEF4",
            2,
        )
        self.assertIsNotNone(command)
        self.assertEqual(command.action, "APPROVE")

    def test_natural_language_reply_becomes_change_feedback(self):
        command = parseReplyCommand(
            "change the date to August 27 2026", "VH-ABC123DEF4", 5
        )
        self.assertIsNotNone(command)
        self.assertEqual(command.action, "CHANGES")
        self.assertEqual(command.revision, 5)
        self.assertEqual(command.feedback, "change the date to August 27 2026")

    def test_changes_keyword_is_not_included_in_feedback(self):
        command = parseReplyCommand(
            "CHANGES\nchange the date to August 27 2026", "VH-ABC123DEF4", 5
        )
        self.assertIsNotNone(command)
        self.assertEqual(command.action, "CHANGES")
        self.assertEqual(command.feedback, "change the date to August 27 2026")

    def test_quoted_short_approval_is_ignored(self):
        self.assertIsNone(
            parseReplyCommand(
                "> approve\n> previous message", "VH-ABC123DEF4", 1
            )
        )


if __name__ == "__main__":
    unittest.main()
