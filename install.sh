#!/usr/bin/env bash
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
  --help        Show this help message
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

# Copy hooks
mkdir -p "$TARGET_DIR/hooks"
cp "$SCRIPT_DIR/hooks/"*.py "$TARGET_DIR/hooks/"

# Copy skills
mkdir -p "$TARGET_DIR/skills"
cp "$SCRIPT_DIR/skills/"*.toml "$TARGET_DIR/skills/"

# Copy agents
mkdir -p "$TARGET_DIR/agents"
cp "$SCRIPT_DIR/agents/"*.md "$TARGET_DIR/agents/"

# Copy guidance
cp "$SCRIPT_DIR/GEMINI.md" "$TARGET_DIR/"

echo "Done. Restart Gemini CLI to activate the extension."
echo ""
echo "Verify with: gemini extensions list"
