---
name: workout-tracker
description: Process workout tables, screenshots, plans, and completed lifting summaries for /Users/dpn/Obsidian/Vault/Weight Lifting; create or update canonical workout notes and maintain the Workouts hub and workout-type indexes. Use when asked to record, import, reconcile, generate, summarize, audit, or correct weight-training workouts in this Obsidian vault. Do not use for general fitness questions that do not require querying or modifying the vault.
---

# Workout Tracker

Read `/Users/dpn/Obsidian/Vault/AGENTS.md` first.
All workouts will appear in /Users/dpn/Obsidian/Vault/Inbox

Use the vault documents as the authoritative contracts:

- For generated plans, read:
  `/Users/dpn/Obsidian/Vault/Weight Lifting/Configuration/Workout Generation.md`
- For completed tables or imported workout results, read:
  `/Users/dpn/Obsidian/Vault/Weight Lifting/Configuration/Workout Summary Format.md`
- For programming or progression decisions, also read:
  `/Users/dpn/Obsidian/Vault/Weight Lifting/Configuration/Training Configuration.md`
  and the applicable lift configuration.
- Read recent completed workouts only when needed for generation, comparison, or summary updates.

## Core rules

- Treat workout Markdown and YAML as the source of truth.
- Store canonical dated workouts only in `Weight Lifting/Workouts/`.
- Preserve every supplied weight, repetition, RPE, note, calorie value, and set classification.
- Treat health-derived `Workout Calories` as the authoritative calorie metric. Preserve historical `Notebook calories` and daily activity totals as provenance only; do not substitute them for workout calories or include them in calorie trend queries.
- Never invent unclear or missing results. Leave the field empty and explain the ambiguity.
- Deduplicate by `(date, workout_type)`.
- Do not count an Inbox capture, duplicate, superseded plan, or mirror as another workout.
- Do not overwrite a completed workout unless the user explicitly approves a correction or merge.
- Follow the vault's approval requirements before writing, moving, replacing, or deleting files.

## Processing a completed workout

1. Identify the workout date, canonical workout type, session name, status, calories, and performed sets.
2. Normalize only fields governed by the vault contracts, such as supported set types and established exercise names.
3. Preserve source order and explanatory notes when classification or transcription required judgment.
4. Search `Weight Lifting/Workouts/` for the same `(date, workout_type)`.
5. Classify the input as:
   - new canonical workout;
   - update or correction to an existing workout;
   - duplicate;
   - possible replacement requiring approval;
   - ambiguous input requiring clarification.
6. Before writing, report:
   - source;
   - proposed canonical path;
   - parsed session information;
   - unclear values or assumptions;
   - proposed index and summary updates.
7. After approval, create or update the canonical note using the Workout Summary Format.
8. After the canonical note, hub link, workout-type link, and validation checks succeed, move the processed original Inbox capture to recoverable macOS Trash by default. Preserve the original `source_file` path in the canonical note and record the move in `log.md`. Do not delete or move captures classified as duplicates, superseded plans, ambiguous inputs, or failed/partially validated imports; leave those in Inbox unless the user explicitly requests cleanup.
9. When health workout calories are unavailable, leave `Workout Calories` empty. Never infer it from notebook calories, daily active energy, or other non-workout totals.

## Generating a workout

Follow `Workout Generation.md`.

- Use only completed canonical history when selecting loads.
- Fill an existing planned shell in place when applicable.
- Never replace completed results.
- Add the required workout-type and Workouts navigation links.
- Add the planned note once to the applicable indexes.

## Graph and index maintenance

For every canonical dated workout:

1. Ensure the workout links to:
   - `Weight Lifting/Workouts.md`;
   - its applicable page in `Weight Lifting/Workout Types/`.
2. Ensure `Weight Lifting/Workouts.md` links to the dated workout exactly once.
3. Ensure the applicable workout-type page links to it exactly once.
4. Map historical `bench` notes to Chest Workouts and historical `deadlift` notes to Back Workouts without changing their stored YAML values.
5. Update counts and status descriptions on the Workouts hub.
6. Update the workout-type summary only when new completed results materially change the supported history.
7. Update `Last reviewed` whenever an index or summary page changes.
8. Append a concise entry to `/Users/dpn/Obsidian/Vault/log.md`.

## Auditing

When asked to audit workout history:

- Compare dated workout files against the Workouts hub and all five type pages.
- Report missing, duplicate, unresolved, or misclassified links before editing.
- Distinguish completed, planned, skipped, duplicate, and superseded sessions.
- Do not modify files unless the user requested changes and approved the plan.

## Validation

After approved changes, verify:

- Required YAML fields follow the applicable contract.
- Completed set-table notes have the required columns.
- Unknown results remain empty rather than inferred.
- The canonical `(date, workout_type)` is unique.
- The workout has both navigation backlinks.
- The Workouts hub contains one canonical link.
- The applicable type page contains one canonical link.
- No Inbox or duplicate file was indexed.
- The processed source capture was moved to recoverable Trash only after all canonical validation checks passed; duplicates, superseded plans, ambiguous inputs, and failed imports remain in Inbox.
- `log.md` records the change.

Report the files changed, validation performed, and any unresolved ambiguity.
