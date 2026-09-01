#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_DIR="$SCRIPT_DIR/mcp"

echo "==> Building MCP server"
(cd "$MCP_DIR" && npm run build --silent)

echo "==> Running local MCP tests"
(cd "$MCP_DIR" && npm test --silent)

echo "==> Running hook unit tests"
python3 "$SCRIPT_DIR/hooks/tests/test_pro_detection.py"

if command -v gemini >/dev/null 2>&1; then
  echo "==> Gemini CLI detected"
  echo "Live Gemini validation remains manual: run the roadmap checks for hooks, GEMINI.md injection, and golden cases."
else
  echo "==> Gemini CLI not installed"
  echo "Skipping live Gemini validation (hooks, GEMINI.md injection, golden cases)."
fi
