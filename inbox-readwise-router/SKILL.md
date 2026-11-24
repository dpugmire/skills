---
name: inbox-readwise-router
description: Inspect /Users/dpn/Obsidian/Vault/Inbox and /Users/dpn/Obsidian/Vault/Inbox/Readwise for new content, compare Readwise sync items against raw/ and the routing ledger, suggest routing, labels, and links, and maintain the vault's podcast show pages, master index, and singleton lifecycle after approved routing. Use when asked to process Inbox or Readwise, route new notes, identify duplicates, or maintain podcast intake. Do not move, delete, or rewrite source notes without explicit approval.
---

# Inbox Readwise Router

Read `/Users/dpn/Obsidian/Vault/AGENTS.md` first.

Read `references/vault-workflow.md` before making routing suggestions or maintaining podcast pages or indexes.

## Workflow

1. Inspect `Inbox/Readwise/Readwise Syncs.md` first.
2. If the latest sync reports `0 documents`, do not scan the full Readwise mirror unless the user explicitly asks for a full audit.
3. Read `Inbox/_readwise-routing-state.json` before suggesting routing for Readwise items.
4. For Readwise, inspect only the files listed in the latest non-zero sync entry unless the user asked for broader processing.
5. Compare candidates against the routing ledger first, then against `raw/` by URL, normalized title, and source category.
6. For each podcast candidate, identify the show from `Author`, `Show`, aliases, canonical metadata, and stable episode identifiers. Check `wiki/podcasts/<Show>.md`, the categorized show entries and `Singleton Feeds` section in `wiki/podcasts.md`, and canonical episodes in `raw/podcasts/`.
7. Classify the show as an existing show page, a singleton feed, or a new feed. Count only substantive canonical episodes; link-only or content-free captures do not qualify for singleton promotion.
8. Include the applicable podcast maintenance in the routing proposal: maintain an existing show page, add a first substantive episode to `Singleton Feeds`, or promote a singleton to a show page when its second substantive episode is approved. Report sparse or ambiguous cases for review.
9. After explicit approval, follow `references/vault-workflow.md`: route only the canonical source, perform the proposed show-page and master-index maintenance, deduplicate links, update the routing ledger, and append a short `log.md` entry. Do not create or populate a show page during the suggestion phase.
10. For general Inbox work, list top-level files in `Inbox/` and the relevant Readwise files, then suggest destinations, labels, and high-value internal links before moving anything.
11. Treat `raw/` as source of truth. Rewrite source notes only for light metadata cleanup when explicitly asked or clearly useful.
12. Never route credentials, recovery keys, encryption keys, or other security-sensitive files into `raw/` or `wiki/`.

## Output

For each candidate, report:

- File
- Suggested location
- Suggested labels
- Suggested related links
- Podcast state—existing show page, singleton, or new feed—and the proposed show-page and master-index maintenance
- Duplicate, sensitive, or approval notes

If no new Readwise content is present, say so explicitly and stop short of mirror-wide scanning unless the user requested it.
