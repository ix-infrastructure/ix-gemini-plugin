#!/usr/bin/env bash
# Copyright 2026 Ix Infrastructure Inc.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

print_help() {
  cat <<'EOF'
ix-gemini-plugin installer

Usage:
  ./install.sh              # install to ~/.gemini/extensions/ix-memory/
  ./install.sh --repo DIR   # install to DIR/.gemini/extensions/ix-memory/
  ./install.sh --help       # show this help

Options:
  --repo DIR    Install to a specific project directory instead of ~/.gemini
  --force       Overwrite existing installation without prompting
  --no-mcp      Accepted for compatibility; nothing is built any more
  --help        Show this help message

Requirements:
  The Ix CLI (>= 0.11.0) on PATH. The extension's MCP server is the CLI's
  own `ix mcp --tools=all`; this plugin no longer ships or builds one.
EOF
}

TARGET_BASE="${HOME}/.gemini"
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      shift
      TARGET_BASE="$1/.gemini"
      ;;
    --force)
      FORCE=1
      ;;
    --no-mcp)
      ;;
    --help|-h)
      print_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      print_help
      exit 1
      ;;
  esac
  shift
done

TARGET_DIR="${TARGET_BASE}/extensions/ix-memory"

if [ -d "$TARGET_DIR" ] && [ "$FORCE" -eq 0 ]; then
  echo "Extension already installed at $TARGET_DIR"
  echo "Use --force to overwrite."
  exit 1
fi

echo "Installing ix-memory extension to $TARGET_DIR ..."

mkdir -p "$TARGET_DIR"

# Copy extension manifest
cp "$SCRIPT_DIR/gemini-extension.json" "$TARGET_DIR/"

# Copy hooks (scripts + hooks.json)
mkdir -p "$TARGET_DIR/hooks"
cp "$SCRIPT_DIR/hooks/"*.py "$TARGET_DIR/hooks/"
cp "$SCRIPT_DIR/hooks/hooks.json" "$TARGET_DIR/hooks/"

# Copy skills as Gemini-native SKILL.md directories
for skill_dir in "$SCRIPT_DIR/skills"/*/; do
  skill_name="$(basename "$skill_dir")"
  if [ -f "$skill_dir/SKILL.md" ]; then
    mkdir -p "$TARGET_DIR/skills/$skill_name"
    cp "$skill_dir/SKILL.md" "$TARGET_DIR/skills/$skill_name/SKILL.md"
  fi
done

# Copy agents
mkdir -p "$TARGET_DIR/agents"
cp "$SCRIPT_DIR/agents/"*.md "$TARGET_DIR/agents/"

# Copy guidance
cp "$SCRIPT_DIR/GEMINI.md" "$TARGET_DIR/"

# The MCP server is the Ix CLI's own (`ix mcp --tools=all`, declared in
# gemini-extension.json), so there is nothing to build. `--tools` arrived in
# Ix 0.11.0; an older CLI rejects it and the server never starts.
if ! command -v ix >/dev/null 2>&1; then
  echo "Warning: ix not found on PATH. Install the Ix CLI (>= 0.11.0) for the MCP tools and hooks." >&2
elif ! ix mcp --help 2>/dev/null | grep -q -- "--tools"; then
  echo "Warning: this ix has no 'ix mcp --tools'. Run 'ix upgrade' (needs >= 0.11.0)." >&2
fi

echo ""
echo "Done. Restart Gemini CLI to activate the extension."
echo ""
echo "Verify with: gemini extensions list"
