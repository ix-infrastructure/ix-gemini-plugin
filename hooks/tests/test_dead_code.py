#!/usr/bin/env python3
# Copyright 2026 Ix Infrastructure Inc.

"""No hook module defines something no hook uses.

A dead-code check in the spirit of `vulture`, using only the standard library
so it runs wherever the other tests do. `common.py` once carried an
error-capture subsystem nothing called, which read as if hook failures were
logged to disk when they were not, and a runner only a test used.

A top-level function, class or constant, or a method, in `hooks/*.py` counts
as used only when the hook code itself refers to it. A use by a test does not
count, nor a use from inside another unused definition, so a whole chain of
dead helpers is reported, not just its head.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]


def _defined(tree: ast.Module) -> dict[str, ast.AST]:
    found: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found[node.name] = node
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not (
                        item.name.startswith("__") and item.name.endswith("__")
                    ):
                        found[item.name] = item
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    found[target.id] = node
    return found


def _referenced(node: ast.AST, skip: set[int]) -> set[str]:
    names: set[str] = set()
    stack = [node]
    while stack:
        current = stack.pop()
        if id(current) in skip:
            continue
        if isinstance(current, ast.Name) and isinstance(current.ctx, ast.Load):
            names.add(current.id)
        elif isinstance(current, ast.Attribute):
            names.add(current.attr)
        elif isinstance(current, ast.ImportFrom):
            names.update(alias.name for alias in current.names)
        stack.extend(ast.iter_child_nodes(current))
    return names


def unused_definitions(directory: Path) -> list[str]:
    trees = {path.name: ast.parse(path.read_text()) for path in sorted(directory.glob("*.py"))}
    defined = {
        name: (module, node) for module, tree in trees.items() for name, node in _defined(tree).items()
    }
    dead: set[str] = set()
    while True:
        skip = {id(defined[name][1]) for name in dead}
        used: set[str] = set()
        for tree in trees.values():
            used |= _referenced(tree, skip)
        newly = {name for name in defined if name not in used} - dead
        if not newly:
            break
        dead |= newly
    return sorted(f"{defined[name][0]}: {name}" for name in dead)


class DeadCodeTest(unittest.TestCase):
    def test_hooks_define_nothing_unused(self) -> None:
        self.assertEqual([], unused_definitions(HOOKS))

    def test_check_reports_a_dead_chain(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "mod.py").write_text(
                "LIVE = 1\nDEAD = 2\n"
                "def helper():\n    return DEAD\n"
                "def head():\n    return helper()\n"
                "def main():\n    return LIVE\n"
                "if __name__ == '__main__':\n    main()\n"
            )
            self.assertEqual(
                ["mod.py: DEAD", "mod.py: head", "mod.py: helper"], unused_definitions(Path(tmp))
            )


if __name__ == "__main__":
    unittest.main()
