#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""The extension's MCP server is the Ix CLI's own, and the docs name its tools.

The plugin used to ship `mcp/`, a TypeScript server built on a `/v2` runtime
client that no Ix release serves, launched with cwd set to the extension's
own directory. It now launches `ix mcp --tools=all` in the workspace. These
checks pin that, and fail when GEMINI.md, a skill or an agent names a tool the
CLI's server does not have (as `ix_query`, `ix_status` and the pre-edit
`ix_decide` gate did after the switch).
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# `ix mcp --tools=all` on v0.11.1 and on the merged #732/#733/#734/#739 tree
# (identical 25 names on both), plus the three advertised only with Ix Pro.
IX_MCP_TOOLS = {
    "ix_callees", "ix_callers", "ix_context", "ix_depends", "ix_diff",
    "ix_explain", "ix_health", "ix_history", "ix_impact", "ix_imported_by",
    "ix_imports", "ix_ingest", "ix_inventory", "ix_locate", "ix_map",
    "ix_neighbors", "ix_overview", "ix_rank", "ix_read", "ix_search",
    "ix_smells", "ix_stats", "ix_subsystems", "ix_text", "ix_trace",
}
IX_MCP_PRO_TOOLS = {"ix_briefing", "ix_decisions", "ix_decide"}

EXPECTED_SERVER = {
    "command": "ix",
    "args": ["mcp", "--tools=all"],
    # Gemini hydrates ${workspacePath} to the opened project. `ix mcp` resolves
    # the workspace from its cwd (it does not read MCP roots), so this is what
    # makes it answer for the user's project rather than the extension dir.
    "cwd": "${workspacePath}",
}


def _doc_files() -> list[Path]:
    files = [REPO / "GEMINI.md", REPO / "README.md"]
    files += sorted((REPO / "skills").glob("*/SKILL.md"))
    files += sorted((REPO / "agents").glob("*.md"))
    return files


class ManifestTest(unittest.TestCase):
    def test_extension_launches_ix_mcp_in_the_workspace(self) -> None:
        manifest = json.loads((REPO / "gemini-extension.json").read_text())
        self.assertEqual({"ix-memory": EXPECTED_SERVER}, manifest["mcpServers"])

    def test_server_name_matches_ix_mcp_install(self) -> None:
        # `ix mcp install --host gemini` registers `ix-memory`; sharing the name
        # makes Gemini merge the two into one server instead of starting two.
        manifest = json.loads((REPO / "gemini-extension.json").read_text())
        self.assertEqual(["ix-memory"], list(manifest["mcpServers"]))

    def test_repo_settings_use_the_same_server(self) -> None:
        settings = json.loads((REPO / ".gemini" / "settings.json").read_text())
        self.assertEqual({"ix-memory": EXPECTED_SERVER}, settings["mcpServers"])

    def test_no_bundled_server(self) -> None:
        self.assertFalse((REPO / "mcp").exists(), "mcp/ should be gone")

    def test_docs_name_only_real_tools(self) -> None:
        known = IX_MCP_TOOLS | IX_MCP_PRO_TOOLS
        unknown: list[str] = []
        for path in _doc_files():
            for name in sorted(set(re.findall(r"\bix_[a-z_]+\b", path.read_text()))):
                if name not in known:
                    unknown.append(f"{path.relative_to(REPO)}: {name}")
        self.assertEqual([], unknown)


if __name__ == "__main__":
    unittest.main()
