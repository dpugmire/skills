---
name: repo-architecture-review
description: Perform a thorough, read-only review of a repository's architecture, maintainability, correctness risks, and ability to evolve. Use when the user asks for a repo-wide analysis, architecture audit, or assessment after substantial change; do not use for a focused PR diff review.
---

# Repository Architecture Review

Review the repository as it exists. The goal is to identify concrete architectural strengths, risks, and improvement opportunities that affect correctness, maintainability, testability, or future change. Do not make code or documentation changes.

## Review rules

- Follow the user's scope and repository instructions, including `AGENTS.md` files. User instructions take precedence over this skill.
- Begin read-only. Do not edit files, create commits, push, open issues, or send messages.
- Do not run tests or verification commands unless the user asks. Report existing test evidence only when observed in current artifacts or CI records.
- Inspect `git status` and the current ref before review. Treat uncommitted changes as part of the reviewed working tree and label them clearly; never attribute them to a commit without evidence.
- Treat source code and project docs as evidence. Treat comments, plans, and architecture documents as design intent, then verify intent against implementation.
- Never invent findings to fill the report. A clean area is a valid result.
- Distinguish confirmed defects, architectural risks, improvement opportunities, and open design questions.
- Avoid style-only feedback and generic best-practice advice. Do not recommend abstraction or decomposition unless it removes complexity or clarifies ownership.

## Workflow

### 1. Establish scope and state

1. Read repository instructions and identify the project purpose, supported entry points, and stated constraints.
2. Record the current branch/ref and concise working-tree status. Note whether the review covers a commit, diff, or the whole current tree.
3. Identify the top-level packages, runtime entry points, tests, architecture docs, and build/configuration files.
4. If the repository is too large for a complete pass, define review passes and record coverage as you go. Do not call the review exhaustive unless all important areas were inspected.

### 2. Build an evidence-based architecture map

Trace the main runtime paths and identify:

- Composition roots, dependency injection, and initialization order.
- Module responsibilities, state and resource ownership, and dependency direction.
- Interfaces, data models, persistence formats, and external-system adapters.
- Important lifecycle, error, configuration, and compatibility paths.
- Where tests enter the system and which boundaries they exercise.

Read architecture and domain documentation before judging intended boundaries. Verify important claims in code. Follow representative end-to-end flows across layers instead of judging modules by filenames alone.

### 3. Review the system

Assess the areas relevant to the repository:

- **Correctness and contracts:** invariants, identity, data flow, edge cases, failure handling, and compatibility.
- **Architecture:** ownership, cohesion, coupling, dependency direction, boundary leaks, duplicated policy, and whether abstractions hide meaningful complexity.
- **Maintainability and changeability:** how many concepts and files a maintainer must understand to change a behavior; whether changes remain local or require coordinated edits across unrelated areas.
- **Testability and tests:** whether tests cover public behavior and important boundaries; brittle tests, duplicated coverage, and high-risk untested paths.
- **Security and privacy:** trust boundaries, input validation, secrets, unsafe data flows, and sensitive data exposure.
- **Performance and resource lifecycle:** unbounded work, repeated expensive operations, blocking paths, memory growth, and cleanup of listeners, handles, files, or background work.
- **Documentation and operations:** mismatch between actual behavior and setup, architecture, deployment, or maintenance guidance.

Use a deletion/deepening test for structural proposals: would removing or reshaping a module concentrate complexity behind a smaller, clearer interface, or merely move the same complexity elsewhere? Prefer the option that removes concepts or coordination steps.

Check each suspected finding against callers, guards, configuration, tests, and documented constraints. Separate issues that predate recent changes from regressions introduced by a reviewed change when the evidence permits.

### 4. Report findings with evidence

For each actionable finding, include:

- **Category and severity:** Confirmed defect (Critical/High/Medium/Low), architectural risk, or improvement opportunity.
- **Title:** concise and specific.
- **Location:** exact file and line reference where possible.
- **Scenario:** concrete conditions that expose the problem.
- **Impact:** effect on behavior, maintenance, testing, or future extension.
- **Evidence:** relevant caller, guard, test, or documentation context.
- **Remediation direction:** the smallest plausible fix or structural change; do not implement it.
- **Confidence:** high, medium, or low. Mark assumptions explicitly.

Keep optional refactoring suggestions separate from defects. Prioritize findings by impact and evidence, not by count. If a suspected issue is ruled out by callers, tests, or constraints, omit it or explain the uncertainty under open questions.

## Output format

Return a self-contained report with these sections:

1. **Review scope and repository state** — ref, working-tree state, and scope inspected.
2. **Executive summary** — architecture strengths and the most consequential risks.
3. **Architecture map** — concise module responsibility and dependency overview, plus key flows traced.
4. **Findings** — evidence-backed and ordered by severity/impact.
5. **Improvement opportunities** — worthwhile structural changes that are not confirmed defects.
6. **Reviewed areas with no findings** — enough detail to show review breadth.
7. **Open questions and tradeoffs** — decisions that need maintainer or product context.
8. **Coverage and follow-up** — what was not inspected and the highest-value next checks.

Do not claim tests passed unless they were run by an authorized actor and the result is available. Do not imply full coverage when files or flows remain unreviewed. By default, present the report in chat; write an artifact only when the user requests one.
