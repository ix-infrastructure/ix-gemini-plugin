#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""What the extension adds to every Gemini session, and a ceiling on it.

Gemini loads the extension's context file (GEMINI.md) and the name and
description of every skill and agent into every session, before the user asks
anything, and resends them with every request. These tests measure that text,
fail when it grows past the ceilings below (README "Always-on context" states
the same numbers), and keep contributor notes out of the context file: they
belong in CONTRIBUTING.md, which Gemini does not load.

The MCP tool catalog (`ix mcp --tools=all`) is also sent every session, but it
is the Ix CLI's, not a file in this repo, so it is not measured here.

    python3 hooks/tests/test_context_size.py --report   # print the sizes
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONTEXT_FILE = REPO / "GEMINI.md"
CONTRIBUTOR_DOC = REPO / "CONTRIBUTING.md"

# Ceilings in UTF-8 bytes. Raise one only on purpose, and update README with it.
CONTEXT_FILE_MAX_BYTES = 2500
ALWAYS_ON_MAX_BYTES = 5000

# Text that is about editing this repository rather than using Ix.
CONTRIBUTOR_MARKERS = (
    "this repo", "repo structure", "contributor", "hooks.json", "common.py",
    "install.sh", "install.ps1", "gemini-extension.json", "hookspecificoutput",
    ".gemini/settings.json",
)

_BLOCK_SCALAR_HEADER = re.compile(r"[|>](?:[+-]?[1-9]?|[1-9][+-])")


def _frontmatter(path: Path) -> dict[str, str]:
    """Top-level `key: value` pairs of a Markdown file's YAML frontmatter.

    A value that goes on over indented lines (a `|` or `>` block scalar, or a
    plain scalar wrapped onto the next line) is joined with single spaces, so
    a multi-line description is measured in full rather than as its first line.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    key: str | None = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if match:
            key = match.group(1)
            value = match.group(2).strip()
            # A block scalar header (`|`, `>-`, `|2+` ...) holds no text itself.
            fields[key] = "" if _BLOCK_SCALAR_HEADER.fullmatch(value) else value
        elif key is not None and line[:1].isspace() and line.strip():
            fields[key] = f"{fields[key]} {line.strip()}".lstrip()
    return fields


def _listing_bytes(paths: list[Path]) -> int:
    """Bytes of the name and description Gemini lists for each skill or agent."""
    total = 0
    for path in paths:
        fields = _frontmatter(path)
        total += len(fields.get("name", "").encode("utf-8"))
        total += len(fields.get("description", "").encode("utf-8"))
    return total


def measure() -> dict[str, int]:
    sizes = {
        "context file (GEMINI.md)": len(CONTEXT_FILE.read_bytes()),
        "skill names and descriptions": _listing_bytes(sorted(REPO.glob("skills/*/SKILL.md"))),
        "agent names and descriptions": _listing_bytes(sorted(REPO.glob("agents/*.md"))),
    }
    sizes["total"] = sum(sizes.values())
    return sizes


class AlwaysOnContextTest(unittest.TestCase):
    def test_context_file_within_ceiling(self) -> None:
        size = measure()["context file (GEMINI.md)"]
        self.assertLessEqual(size, CONTEXT_FILE_MAX_BYTES, "GEMINI.md grew; trim it or raise the ceiling")

    def test_always_on_total_within_ceiling(self) -> None:
        sizes = measure()
        self.assertLessEqual(sizes["total"], ALWAYS_ON_MAX_BYTES, sizes)

    def test_readme_states_the_ceilings(self) -> None:
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        for ceiling in (CONTEXT_FILE_MAX_BYTES, ALWAYS_ON_MAX_BYTES):
            self.assertRegex(readme, rf"\b{ceiling:,}\b|\b{ceiling}\b")

    def test_skills_and_agents_have_descriptions(self) -> None:
        # A missing description would make the listing look small for the wrong reason.
        for path in sorted(REPO.glob("skills/*/SKILL.md")) + sorted(REPO.glob("agents/*.md")):
            with self.subTest(path=path.relative_to(REPO)):
                self.assertTrue(_frontmatter(path).get("description"))

    def test_multi_line_descriptions_are_measured_in_full(self) -> None:
        # A description wrapped over several lines must not be measured as its
        # first line (or as the `|` / `>` header) only.
        cases = {
            "block": "description: >-\n  one two\n  three\n",
            "literal": "description: |\n  one two\n  three\n",
            "plain": "description: one two\n  three\n",
        }
        with tempfile.TemporaryDirectory() as tmp:
            for label, body in cases.items():
                with self.subTest(style=label):
                    path = Path(tmp) / f"{label}.md"
                    path.write_text(f"---\nname: x\n{body}tools:\n  - Bash\n---\n# x\n", encoding="utf-8")
                    self.assertEqual("one two three", _frontmatter(path)["description"])
                    self.assertEqual(len("x") + len("one two three"), _listing_bytes([path]))

    def test_context_file_has_no_contributor_notes(self) -> None:
        text = CONTEXT_FILE.read_text(encoding="utf-8").lower()
        found = [marker for marker in CONTRIBUTOR_MARKERS if marker in text]
        self.assertEqual([], found, "move these to CONTRIBUTING.md")

    def test_contributor_doc_exists_and_is_not_installed(self) -> None:
        self.assertTrue(CONTRIBUTOR_DOC.exists())
        for installer in ("install.sh", "install.ps1"):
            with self.subTest(installer=installer):
                self.assertNotIn("CONTRIBUTING", (REPO / installer).read_text(encoding="utf-8"))

    def test_extension_loads_the_default_context_file(self) -> None:
        # With no contextFileName, Gemini loads GEMINI.md from the extension
        # directory and nothing else; naming another file would bypass the checks above.
        manifest = json.loads((REPO / "gemini-extension.json").read_text(encoding="utf-8"))
        self.assertIn(manifest.get("contextFileName", "GEMINI.md"), ("GEMINI.md", ["GEMINI.md"]))

    def test_no_session_start_message(self) -> None:
        # The context file is already in every session; a SessionStart message
        # repeated it and cost an `ix status` call per session.
        hooks = json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        self.assertNotIn("SessionStart", hooks)
        self.assertFalse((REPO / "hooks" / "session_start.py").exists())


if __name__ == "__main__":
    if "--report" in sys.argv[1:]:
        for label, size in measure().items():
            print(f"{label}: {size} bytes")
        sys.exit(0)
    unittest.main()
