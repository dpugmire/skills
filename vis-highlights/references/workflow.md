# Workflow and data contract

## State transitions

```text
new email -> awaiting_analysis -> draft_ready -> awaiting_approval
               |                                      |
               +-- dismiss -> ignored                 +-- APPROVE -> committing -> committed

awaiting_approval -- CHANGES -> awaiting_analysis -> draft_ready -> awaiting_approval
                                      |
                                      +-- dismiss -> awaiting_approval
```

`sync` writes new submissions and valid corrections to a private bundle and leaves them unread. `stage` records a revision, sends its approval request, and only then marks that inbound message read. Approval replies are marked read only after the idempotent CSV commit and required confirmation complete. Failures remain unread and receive `VisHighlights/Failed`.

`dismiss --submission-id ID --reason REASON` is only for a pending bundle that clearly contains no reportable activity. It records the reason in local state, preserves the bundle, adds `VisHighlights/Ignored`, removes other workflow labels, and marks that inbound message read. It never sends mail or changes the CSV. Dismissing a new submission sets it to `ignored`; dismissing a pending correction restores its prior revision to `awaiting_approval`.

If a private bundle is already listed by `pending`, correct its result and rerun `stage`; a successful stage removes the failure label. For failures that occurred before a bundle was queued, use `retry-failed --message-id MESSAGE_ID` to remove the failure label and restore the unread label before the next `sync`.

The preferred approval reply is simply:

```text
approve
```

Any other non-empty fresh reply in the approval thread is treated as correction feedback. For example:

```text
change the date to August 27 2026
```

The script infers the submission and current revision from the Gmail thread. The original full commands remain supported for compatibility:

```text
APPROVE VH-XXXXXXXXXX R1
CHANGES VH-XXXXXXXXXX R1
Describe the correction here.
```

Only the original sender can approve or request changes. Only the current revision can be approved. A shorthand approval must contain only `approve` after quoted content, common reply separators (including Outlook underscore lines), and a standard `--` signature are removed. Quoted copies of older replies are ignored.

Only one correction can be pending for a submission. An approval received while a corrected revision is being prepared is rejected without changing the CSV. Corrections received after a revision is committed are also rejected because appending a replacement would not remove the already approved row.

## Category values

Use exactly one of:

- `Conference/Workshop`
- `Publication`
- `Symposia/Meeting`
- `Software`
- `Professional Society Service`
- `Honor/Award`
- `Other`
- `Mentorship`
- `Project`

Typical mappings:

- conference presentation, workshop participation, or conference organization -> `Conference/Workshop`
- journal or proceedings paper accepted or published -> `Publication`
- journal review, committee work, editorial activity, or professional-society duty -> `Professional Society Service`
- invited university or laboratory seminar that is not a conference -> `Other`
- hosted visitor or guest -> `Other`

## CSV columns

The output header, in order, is:

```text
ID, Created, Employee, Section Head, Group Leader, Category, Title,
Details, URL, Dates, Location, Attachments, Admin,
CCSD form (supporting documents), Created By, CCSD Form ID,
Date Submitted (CCSD)
```

For approved rows:

- leave `ID`, `CCSD form (supporting documents)`, `Created By`, `CCSD Form ID`, and `Date Submitted (CCSD)` blank;
- set `Created` at the first commit attempt and retain it during retries;
- set `Attachments` to `1` when the original submission had any attachment, otherwise `0`;
- preserve non-empty organizational fields in the staged result;
- otherwise use the latest non-empty historical organizational mapping when `Employee` exactly matches an existing CSV value;
- otherwise fill `Section Head` and `Group Leader` from the configured global defaults;
- preserve multiline `Details` using normal RFC 4180 CSV quoting.

The commit process stores the complete materialized rows in SQLite before writing. On retry it checks for those exact rows under a file lock, preventing a crash between CSV append and state update from creating duplicates.

## Research and provenance

Codex may use web search to fill or verify event dates, locations, agenda titles, journal or proceedings names, co-authors, and public URLs. It must leave unsupported fields blank and disclose uncertainty. Approval emails show the primary CSV URL, additional source URLs, and uncertainty notes.

For publication, conference/workshop, symposia/meeting, and project drafts, approval emails also include an optional `FYI: Potentially related work` section. Travel to meet scientists or project collaborators is treated as meeting/project activity. In the current proof-of-concept mode it compares the draft with existing approved CSV entries without excluding the same employee, includes up to five newest potential overlaps, and preserves any existing record URL. Restore same-employee exclusion after the demonstration. These are advisory suggestions only; they never change the CSV or notify the referenced employee.

## Staged result contract

The JSON passed to `stage` has this shape:

```json
{
  "needs_human_review": false,
  "warnings": [],
  "highlights": [
    {
      "employee": "Person receiving the highlight",
      "section_head": "",
      "group_leader": "",
      "category": "Publication",
      "title": "Concise title",
      "details": "Self-contained factual summary",
      "url": "https://canonical.example/item",
      "dates": "August 2026",
      "location": "",
      "admin": "",
      "source_urls": ["https://evidence.example/item"],
      "uncertainty_notes": []
    }
  ]
}
```

Return one object per distinct reportable activity. Every object must use an allowed category, a non-empty title of at most 255 characters, non-empty details, and lists for `source_urls` and `uncertainty_notes`. Set `needs_human_review` and add a concise uncertainty note when a material fact is unresolved. The deterministic stage fills missing organizational fields first from an exact employee-name match in the historical CSV, then from configured global defaults.
