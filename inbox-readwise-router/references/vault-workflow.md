# Vault Workflow

## Scope

This skill is specific to `/Users/dpn/Obsidian/Vault`.

Use it for suggestion and triage work on:

- `Inbox/`
- `Inbox/Readwise/`
- `Inbox/_readwise-routing-state.json`
- `Inbox/Readwise/Readwise Syncs.md`
- `raw/podcasts/`
- `wiki/podcasts/`
- `wiki/podcasts.md`
- `log.md`

## Core Rules

- `raw/` is the source of truth.
- `Inbox/Readwise/` is a disposable sync mirror, not canonical storage.
- Suggest destinations before moving files.
- Move files only after explicit approval.
- Do not delete duplicates, staging files, or sensitive files unless explicitly asked.
- Do not put credentials, recovery keys, private secrets, or security-sensitive images into `raw/` or `wiki/`.

## Readwise Rules

- Read `Inbox/Readwise/Readwise Syncs.md` first.
- If the latest sync says `0 documents`, stop unless the user explicitly requests a full audit.
- If the latest sync lists documents, inspect only those items.
- Compare candidates against `Inbox/_readwise-routing-state.json` by URL, normalized title, and source category.
- Compare uncertain items against `raw/` by normalized title and source URL.
- For podcasts, compare Snipd episode URLs when present.
- Leave duplicate mirror files in `Inbox/Readwise/` unless explicitly asked to clean them up.

## Podcast Organization

- Canonical episode sources live directly under one of:
  - `raw/podcasts/philosophy/`
  - `raw/podcasts/politics/`
  - `raw/podcasts/current_events/`
  - `raw/podcasts/science_tech/`
  - `raw/podcasts/personal/`
  - `raw/podcasts/other/`
- Maintained show-summary pages live at `wiki/podcasts/<Show>.md`.
- `wiki/podcasts.md` is the master podcast index. It contains categorized show-page links followed by a `Singleton Feeds` section with direct links to first episodes whose shows do not yet have summary pages.
- The master index uses the existing headings `Philosophy`, `Current Events`, `Science, Technology, and Health`, and `Personal Development`. Map both `raw/podcasts/politics/` and `raw/podcasts/current_events/` to `Current Events`. Place `other` shows by their actual subject; if the category is unclear, report it rather than inventing a heading.
- Never index an `Inbox/Readwise/` mirror as a canonical episode.

## Podcast Show-Page and Singleton Lifecycle

When considering a podcast candidate:

- Identify the show using `Author`, `Show`, aliases, canonical episode metadata, and stable source identifiers such as the Snipd episode URL.
- Search the show pages, master index, and canonical episodes before deciding whether the candidate belongs to an existing show page, a singleton feed, or a new feed. Deduplicate feed-name variants and aliases rather than treating them as separate shows.
- A substantive episode has saved highlights, transcript material, or notes sufficient to support a useful source-grounded annotation. A link-only, empty, or otherwise content-free capture does not count toward promotion; flag it for keep-or-discard review.
- During the suggestion phase, report the podcast state and the complete proposed maintenance. Do not create or populate a show page, change the master index, or move the source before approval.

After routing the episode is explicitly approved:

1. Use the canonical episode note in `raw/`, never its `Inbox/Readwise/` mirror, as the link and index target.
2. For a new feed's first substantive canonical episode:
   - Do not create a show-summary page.
   - Add one direct canonical episode link under the appropriate category in `wiki/podcasts.md` → `Singleton Feeds`.
3. When a singleton feed gains its second substantive canonical episode:
   - Create `wiki/podcasts/<Show>.md` as part of the approved routing work.
   - Build its summary and recurring themes only from the two canonical sources, noting source limitations where appropriate.
   - Add both canonical episodes once under `Saved episodes`, each with a concise source-grounded annotation.
   - Add `Last reviewed`, useful related pages, and open questions when supported.
   - Replace the direct singleton entry in `wiki/podcasts.md` with one show-page entry under the appropriate main category.
   - Ensure both canonical episode notes link to the show page through existing `Author` or `Show` metadata, or through an established related-note section.
4. For a show with an existing populated summary page:
   - Ensure the canonical episode links to the show page.
   - Add the canonical episode once to `Saved episodes`, preserving the page's structure, ordering, and style.
   - Add a concise annotation supported by the saved highlights or transcript.
   - Review the summary, recurring themes, tags, related links, and open questions. Update only fields materially changed or extended by the new episode; do not rewrite merely for different wording.
   - Update `Last reviewed` when the page content changes.
   - Ensure the show page appears once in the appropriate main category of `wiki/podcasts.md` and not in `Singleton Feeds`.
5. Preserve an existing useful show page even if a later audit finds only one current canonical episode; report possible demotion rather than doing it implicitly.
6. Deduplicate by canonical path, normalized title, source URL, and Snipd episode identifier when available. Never count mirror duplicates as additional episodes.
7. Record each routed, duplicate, merged, or discarded decision in `Inbox/_readwise-routing-state.json`. After approved vault changes, append a short dated entry to `log.md`.

## Common Destinations

- AI, LLM, Codex, model, agent, or tooling references:
  - `raw/reference/ai-ml/`
- Weekly or recurring AI briefings:
  - `raw/reference/ai-ml/briefings/`
- Obsidian, workflow, vault organization, or knowledge-management references:
  - `raw/reference/organization/`
  - `raw/reference/vault-organization/`
- Theology, Mormon history, scripture, ethics, and philosophy:
  - `raw/reference/philosophy/`
- History and politics:
  - `raw/reference/history-politics/`
- Scientific computing and HPC references:
  - `raw/reference/scientific-computing/`
- Project-specific materials:
  - `raw/projects/<project>/`
- General meetings:
  - `raw/meetings/`
- Podcast notes:
  - `raw/podcasts/philosophy/`
  - `raw/podcasts/politics/`
  - `raw/podcasts/science_tech/`
  - `raw/podcasts/current_events/`
  - `raw/podcasts/personal/`
  - `raw/podcasts/other/`

## Suggesting Labels

Prefer small, reusable label sets rather than inventing many new tags.

Examples:

- AI / briefing:
  - `ai-ml`, `briefing`, `current-events`, `openai`, `anthropic`, `nvidia`, `open-source`
- Codex / workflow:
  - `ai-ml`, `codex`, `agents`, `workflow`, `tooling`
- Mormon / theology:
  - `mormonism`, `lds`, `theology`, `institutional-authority`, `truth-claims`
- HPC / scientific computing:
  - `hpc`, `gpu`, `scientific-computing`, `visualization`, `inference`

## Suggesting Internal Links

Prefer stable, high-value related notes already present in the vault.

Examples:

- AI items:
  - `[[OpenAI]]`, `[[Anthropic]]`, `[[NVIDIA]]`, `[[PyTorch]]`, `[[vLLM]]`, `[[llama.cpp]]`, `[[AI4Research]]`
- Mormon / theology items:
  - `[[The Only True and Living Church]]`
  - `[[The Only True Church]]`
  - `[[Ananias and Sapphira History as Parable]]`
  - `[[Why Did So Many People Stop Going to Church - The Atlantic]]`
  - `[[lds_high_low_church_summary]]`
  - `[[ComparsionAmongChristianSects|Mormonism and Comparative Christian Theology]]`

## Sensitive Files

Treat files with names or contents suggesting keys, credentials, account recovery, encryption, or private security material as sensitive.

For those:

- Suggest no `raw/` or `wiki/` destination.
- Recommend leaving them in `Inbox/` or moving them outside the vault to secure storage.
- Do not add labels or links unless the user explicitly wants vault tracking metadata.
