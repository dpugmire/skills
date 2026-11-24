#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
INSTALL_DIR="${HOME}/.agents/skills"
BACKUP_DIR=""

skills=(
  "hatch-pet|hatch-pet"
  "inbox-readwise-router|inbox-readwise-router"
  "repo-architecture-review|repo-architecture-review"
  "vis-highlights|vis-highlights"
  "workout-tracker|workout-tracker"
  "caveman|third-party/caveman/skills/caveman"
  "feynman-technique|third-party/knowledge-skills/feynman-technique"
  "find-skills|third-party/vercel-skills/skills/find-skills"
  "grill-me|third-party/mattpocock-skills/skills/productivity/grill-me"
  "growth-log|third-party/ecc/skills/growth-log"
  "study|third-party/flc-skills/skills/study"
  "web-design-guidelines|third-party/vercel-agent-skills/skills/web-design-guidelines"
  "devils-advocate|devils-advocate"
)

for entry in "${skills[@]}"; do
  IFS='|' read -r name relative_path <<< "$entry"
  if [[ ! -f "${REPO_DIR}/${relative_path}/SKILL.md" ]]; then
    printf 'Missing %s/SKILL.md. Initialize submodules with:\n' "$relative_path" >&2
    printf '  git -C "%s" submodule update --init --recursive\n' "$REPO_DIR" >&2
    exit 1
  fi
done

mkdir -p "$INSTALL_DIR"

for entry in "${skills[@]}"; do
  IFS='|' read -r name relative_path <<< "$entry"
  source_dir="$(cd "${REPO_DIR}/${relative_path}" && pwd -P)"
  destination="${INSTALL_DIR}/${name}"

  if [[ -L "$destination" && "$(readlink "$destination")" == "$source_dir" ]]; then
    printf 'Already linked: %s\n' "$name"
    continue
  fi

  if [[ -e "$destination" || -L "$destination" ]]; then
    if [[ -z "$BACKUP_DIR" ]]; then
      stamp="$(date '+%Y%m%d-%H%M%S')"
      BACKUP_DIR="${HOME}/.agents/skills.BACKUP-${stamp}"
      suffix=1
      while [[ -e "$BACKUP_DIR" ]]; do
        BACKUP_DIR="${HOME}/.agents/skills.BACKUP-${stamp}-${suffix}"
        suffix=$((suffix + 1))
      done
      mkdir -p "$BACKUP_DIR"
    fi
    mv "$destination" "${BACKUP_DIR}/${name}"
    printf 'Backed up existing skill: %s\n' "$name"
  fi

  ln -s "$source_dir" "$destination"
  printf 'Installed: %s\n' "$name"
done

if [[ -n "$BACKUP_DIR" ]]; then
  printf 'Existing skill copies preserved in: %s\n' "$BACKUP_DIR"
fi
printf 'Skills linked from: %s\n' "$REPO_DIR"
