# Skills

A personal collection of reusable AI agent skills. This repository keeps locally maintained skills together and records upstream sources for third-party skills, so their origins remain easy to inspect and update.

## Layout

Each locally maintained skill lives in its own top-level directory and contains a `SKILL.md` plus any supporting files it needs:

- `hatch-pet/` — locally maintained pet creation and validation workflow, with its own scripts, tests, and references. It carries the included Apache 2.0 license and is based on the [Codex pet skill](https://github.com/openai/skills/tree/main/skills/.curated/hatch-pet).
- `inbox-readwise-router/` — process and route Obsidian Inbox and Readwise captures.
- `repo-architecture-review/` — perform read-only, repo-wide architecture and maintainability reviews.
- `vis-highlights/` — process publication highlight emails and prepare highlight slides and CSV updates.
- `workout-tracker/` — import and maintain workout notes in the Obsidian vault.

Third-party source repositories are Git submodules under `third-party/`. They are kept as upstream references rather than copied into the locally maintained skill directories.

| Installed skill | Upstream repository | Skill path in source repository |
| --- | --- | --- |
| `caveman` | [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman) | `skills/caveman/` |
| `feynman-technique` | [deciqAI/knowledge-skills](https://github.com/deciqAI/knowledge-skills) | `feynman-technique/` |
| `find-skills` | [vercel-labs/skills](https://github.com/vercel-labs/skills) | `skills/find-skills/` |
| `grill-me` | [mattpocock/skills](https://github.com/mattpocock/skills) | `skills/productivity/grill-me/` |
| `growth-log` | [affaan-m/ECC](https://github.com/affaan-m/ECC) | `skills/growth-log/` |
| `study` | [flc1125/skills](https://github.com/flc1125/skills) | `skills/study/` |
| `devils-advocate` | [tech-leads-club/agent-skills](https://github.com/tech-leads-club/agent-skills) | Local copy: `devils-advocate/`; upstream: `packages/skills-catalog/skills/(decision-making)/the-fool/` |
| `web-design-guidelines` | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) | `skills/web-design-guidelines/` |

The `devils-advocate` skill is adapted from Tech Leads Club's `the-fool` skill and licensed under CC-BY-4.0. Retain upstream attribution when redistributing or adapting it. The upstream repository remains available as a submodule for reference and updates.

## Clone and update

Clone with upstream repositories included:

```bash
git clone --recurse-submodules https://github.com/dpugmire/skills.git
```

If you already cloned without submodules:

```bash
git submodule update --init --recursive
```

To advance upstream references deliberately:

```bash
git submodule update --remote --merge
```

Review and commit the changed submodule pointers. The local skill snapshots do not update automatically when an upstream submodule changes.

## Use with Codex

Run the installer from this checkout to link the local skills and third-party skills into `~/.agents/skills/`:

```bash
./setup.sh
```

The script checks that all skill sources are present, including initialized submodules. It creates symlinks, so changes in this checkout are immediately reflected in the installed skills. If a destination skill with the same name already exists, the script moves that entry into a timestamped `~/.agents/skills.BACKUP-*` directory before linking the repo copy. It does not delete existing files.

Codex can also discover project-specific skills under `<project>/.agents/skills/`. See [OpenAI's skill documentation](https://developers.openai.com/plugins/concepts/skills) for current behavior.
