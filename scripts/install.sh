#!/usr/bin/env bash
set -euo pipefail
TARGET="both"; SCOPE="user"; PROJECT_ROOT="$PWD"; UPGRADE=0
BACKUP_STAMP="$(date +%Y%m%d-%H%M%S)"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="${2,,}"; shift 2 ;;
    --scope) SCOPE="${2,,}"; shift 2 ;;
    --project-root) PROJECT_ROOT="$2"; shift 2 ;;
    --upgrade) UPGRADE=1; shift ;;
    -h|--help) echo "Usage: bash scripts/install.sh [--target codex|claude|both] [--scope user|project] [--project-root PATH] [--upgrade]"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$TARGET" == "codex" || "$TARGET" == "claude" || "$TARGET" == "both" ]] || { echo "Invalid target" >&2; exit 2; }
[[ "$SCOPE" == "user" || "$SCOPE" == "project" ]] || { echo "Invalid scope" >&2; exit 2; }
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$SCOPE" == "user" ]]; then CODEX_ROOT="$HOME/.codex"; CODEX_SKILLS="$HOME/.agents/skills"; CLAUDE_ROOT="$HOME/.claude"; else CODEX_ROOT="$PROJECT_ROOT/.codex"; CODEX_SKILLS="$PROJECT_ROOT/.agents/skills"; CLAUDE_ROOT="$PROJECT_ROOT/.claude"; fi
copy_tree_safe() {
  local src="$1" dst="$2" file rel target
  while IFS= read -r -d '' file; do
    rel="${file#"$src"/}"; target="$dst/$rel"
    if [[ -e "$target" ]]; then
      if [[ "$UPGRADE" -eq 0 ]]; then echo "Skipped existing file: $target"; continue; fi
      cp -p "$target" "$target.bak-$BACKUP_STAMP"
      echo "Backed up: $target.bak-$BACKUP_STAMP"
    fi
    mkdir -p "$(dirname "$target")"; cp -f "$file" "$target"; echo "Installed: $target"
  done < <(find "$src" -type f -print0)
}
retire_legacy_file() {
  local path="$1" backup
  if [[ "$UPGRADE" -eq 0 || ! -e "$path" ]]; then return; fi
  backup="$path.bak-$BACKUP_STAMP"
  mv "$path" "$backup"
  echo "Retired legacy file: $backup"
}
if [[ "$TARGET" == "codex" || "$TARGET" == "both" ]]; then
  copy_tree_safe "$REPO_ROOT/.codex/agents" "$CODEX_ROOT/agents"
  retire_legacy_file "$CODEX_ROOT/agents/implementer.toml"
  copy_tree_safe "$REPO_ROOT/.agents/skills/loop-engineering" "$CODEX_SKILLS/loop-engineering"
  for package in core roles workflows packs; do
    copy_tree_safe "$REPO_ROOT/$package" "$CODEX_SKILLS/loop-engineering/$package"
  done
fi
if [[ "$TARGET" == "claude" || "$TARGET" == "both" ]]; then
  copy_tree_safe "$REPO_ROOT/.claude/agents" "$CLAUDE_ROOT/agents"
  retire_legacy_file "$CLAUDE_ROOT/agents/implementer.md"
  copy_tree_safe "$REPO_ROOT/.claude/skills/loop-engineering" "$CLAUDE_ROOT/skills/loop-engineering"
  for package in core roles workflows packs; do
    copy_tree_safe "$REPO_ROOT/$package" "$CLAUDE_ROOT/skills/loop-engineering/$package"
  done
fi
if [[ "$UPGRADE" -eq 1 ]]; then echo "Done. Existing managed files were backed up and upgraded."; else echo "Done. Existing files were not overwritten."; fi
echo "Merge AGENTS.md / CLAUDE.md manually; installer does not replace them."
