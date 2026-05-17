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
  --no-mcp      Skip the MCP server build (installs extension shell only)
  --help        Show this help message

Requirements:
  Node.js >= 18 and npm are required to build the MCP server.
  Use --no-mcp to skip the MCP build if Node.js is not available.
EOF
}

TARGET_BASE="${HOME}/.gemini"
FORCE=0
NO_MCP=0

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
      NO_MCP=1
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

# Build and install MCP server
if [ "$NO_MCP" -eq 0 ]; then
  echo "Building MCP server..."

  if ! command -v node &>/dev/null; then
    echo "Warning: node not found. Skipping MCP build. Use --no-mcp to suppress this warning." >&2
  elif ! command -v npm &>/dev/null; then
    echo "Warning: npm not found. Skipping MCP build. Use --no-mcp to suppress this warning." >&2
  else
    MCP_SRC="$SCRIPT_DIR/mcp"
    MCP_DEST="$TARGET_DIR/mcp"
    mkdir -p "$MCP_DEST"

    # Install dependencies and compile
    (cd "$MCP_SRC" && npm ci --silent && npm run build --silent)

    # Copy compiled output and runtime dependencies
    cp -r "$MCP_SRC/dist" "$MCP_DEST/"
    cp "$MCP_SRC/package.json" "$MCP_DEST/"
    cp "$MCP_SRC/package-lock.json" "$MCP_DEST/"

    # Install production dependencies in destination
    (cd "$MCP_DEST" && npm ci --omit=dev --silent)

    echo "MCP server installed to $MCP_DEST"
  fi
fi

echo ""
echo "Done. Restart Gemini CLI to activate the extension."
echo ""
echo "Verify with: gemini extensions list"
