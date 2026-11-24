# Configuration and authentication

The workflow uses a local configuration directory, defaulting to `~/.config/vis-highlights`. Override it with `VIS_HIGHLIGHTS_HOME` when testing or isolating an installation.

## Initial setup

From `/Users/dpn/proj/IPA`:

```bash
/Users/dpn/venv/bin/python .agents/skills/vis-highlights/scripts/vis_highlights.py init \
  --gmail-address vishighlights@gmail.com \
  --csv-path /Users/dpn/proj/IPA/CSMD_Data_Report.csv
```

Use Python 3.10 or newer linked against OpenSSL. Python 3.12 is recommended.

The command creates `config.json` and `state.sqlite3` with owner-only permissions. The private spool defaults to `~/.config/vis-highlights/spool`; override it with `spool_path` in `config.json` only when needed.

Optional organization defaults fill blank staged fields after any exact employee match from the historical CSV:

```json
{
  "default_section_head": "Rafael DaSilva",
  "default_group_leader": "David Pugmire"
}
```

These are interim global defaults. Keep them configurable so a future employee-to-group-leader mapping can replace the global fallback without changing the approval workflow.

## Google OAuth client

1. Create a Google Cloud project and enable the Gmail API.
2. Configure the Google Auth consent screen as an external app for the personal Gmail account.
3. Add `vishighlights@gmail.com` as a test user while the app remains in testing.
4. Create an OAuth client with application type **Desktop app**.
5. Download its JSON and save it as `~/.config/vis-highlights/google_credentials.json`.
6. Run:

```bash
/Users/dpn/venv/bin/python .agents/skills/vis-highlights/scripts/vis_highlights.py auth
```

The workflow requests the `gmail.modify` scope. That scope supports reading messages, retrieving attachments, sending replies, and changing message labels. The generated refresh token is stored in `google_token.json` with owner-only permissions.

## Preflight

Run `doctor`. A live run requires:

- a valid configuration and exact CSV header;
- Google desktop-client credentials and an authorized token;
- a writable CSV directory;
- Python 3.10 or newer linked against OpenSSL;
- the two Google dependencies in `requirements.txt`.

No separate model API key is used. Codex reads private spool files and performs the analysis during an on-demand or scheduled skill run. Gmail OAuth remains necessary for downloading messages, sending approval replies, applying labels, and marking completed messages read.
