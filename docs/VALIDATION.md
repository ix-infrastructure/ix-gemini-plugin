# ix-gemini-plugin — Validation Findings

**Last updated:** 2026-05-17  
**Source:** Gemini CLI extension reference (`docs/extensions/reference.md`) and hooks reference (`docs/hooks/reference.md`) from https://github.com/google-gemini/gemini-cli

---

## Summary

Four bugs were found and fixed across two validation passes. Bugs 1–3 were found in the first pass (2026-05-16). Bugs 4–5 were found from a live validation run (2026-05-17).

| Bug | Symptom | Fixed in |
|---|---|---|
| 1 | Hooks silently ignored — defined in wrong file | `hooks/hooks.json` created |
| 2 | Skills not discoverable — wrong format | `skills/*/SKILL.md` converted |
| 3 | Hook matcher wrong tool name | `hooks.json` updated |
| 4 | MCP tools not connected | `gemini-extension.json` updated |
| 5 | `AfterTool` hook crashing | `hooks/after_tool.py`, `common.py`, `session_end.py` hardened |

---

## Bug 1 — Hooks defined in `gemini-extension.json` (INVALID)

### What was wrong

The extension manifest had a top-level `hooks` array:

```json
{
  "hooks": [
    { "event": "SessionStart", "command": "python3 ${extensionPath}/hooks/session_start.py" },
    ...
  ]
}
```

### Why it fails

The Gemini CLI extension reference states:

> Hooks are not defined in the `gemini-extension.json` manifest.  
> Define hooks in a `hooks/hooks.json` file within your extension directory.

The `hooks` key in `gemini-extension.json` is **not a recognized field**. Gemini CLI ignores it. None of the Python hooks were firing.

### Fix

- Removed `hooks` array from `gemini-extension.json`
- Created `hooks/hooks.json` with the correct nested format matching `settings.json` hook schema

### Correct `hooks/hooks.json` format

```json
{
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "..." }] }],
    "BeforeTool": [{ "matcher": "run_shell_command", "hooks": [{ "type": "command", "command": "..." }] }]
  }
}
```

---

## Bug 2 — Skills defined as `.toml` array in `gemini-extension.json` (INVALID)

### What was wrong

The manifest had a `skills` array pointing to `.toml` files:

```json
{
  "skills": [
    "skills/ix-understand.toml",
    "skills/ix-investigate.toml",
    ...
  ]
}
```

### Why it fails

The Gemini CLI extension reference states:

> Bundle agent skills by placing skill definitions in a `skills/` directory.  
> For example, `skills/security-audit/SKILL.md` exposes a `security-audit` skill.

Skills are **automatically discovered** from `skills/<name>/SKILL.md` subdirectories. There is no `skills` array in the manifest schema. The `.toml` format is Claude Code's skill format, not Gemini CLI's. None of the skills were discoverable.

### Fix

- Removed `skills` array from `gemini-extension.json`
- Converted skills to `skills/<name>/SKILL.md`
- Removed the legacy Claude-style `skills/*.toml` artifacts from the Gemini plugin tree

---

## Bug 3 — Hook matcher `"shell"` is wrong tool name

### What was wrong

`BeforeTool` and `AfterTool` used `"matcher": "shell"`. Gemini CLI's built-in shell tool is named `run_shell_command`, not `shell`. The regex `shell` would not match `run_shell_command`.

### Fix

Updated `hooks/hooks.json` to use `"matcher": "run_shell_command"`.

---

## Bug 4 — MCP tools not connected (live validation, 2026-05-17)

### What was wrong

`gemini-extension.json` had no `mcpServers` field. The Gemini CLI extension reference confirms that `mcpServers` **is** a valid field in `gemini-extension.json`. Without it, Gemini never starts the MCP server, so `ix_status`, `ix_query`, etc. are absent from Gemini's toolset.

Additionally:
- `.gemini/settings.json` used `${workspaceRoot}` (invalid) and `${workspaceId}` (not a Gemini CLI variable). The correct variable is `${workspacePath}`.
- `install.ps1` was missing the MCP build step entirely.

### Fix

Added `mcpServers` to `gemini-extension.json` using `${extensionPath}` — the variable Gemini CLI expands to the extension's installation directory:

```json
"mcpServers": {
  "ix-memory": {
    "command": "node",
    "args": ["dist/server.js"],
    "cwd": "${extensionPath}/mcp",
    "env": { "IX_RUNTIME_URL": "http://localhost:8090" }
  }
}
```

After install, `${extensionPath}/mcp` resolves to `~/.gemini/extensions/ix-memory/mcp`, and `dist/server.js` is present there after the build step.

Also fixed:
- `.gemini/settings.json`: `${workspaceRoot}` → `${workspacePath}`, removed `IX_WORKSPACE_ID` (optional in config, no Gemini variable to set it)
- `install.sh`: removed the now-redundant manual "Add to settings.json" instructions
- `install.ps1`: added the MCP build, copy, and `npm ci --omit=dev` steps

---

## Bug 5 — AfterTool hook crashing (live validation, 2026-05-17)

### What was wrong

`spawn_background_ix_map()` in `common.py` had no exception handling around `subprocess.Popen()`. If `ix` is not in the subprocess PATH (e.g., shell env differs from the user's login env), `Popen(["ix", "map"])` raises `FileNotFoundError`. This propagated unhandled through `after_tool.py`'s `main()` and `session_end.py`'s `main()`, producing a non-zero exit. Gemini CLI marks any hook with non-zero exit as failed.

The `shutil.which("ix")` guard in `ix_healthy()` is not sufficient protection because Gemini CLI may invoke the hook script with a different PATH than the parent shell — particularly on systems where `ix` is installed in a user-local path that isn't set in the hook's environment.

### Fix

Two-layer defence:

1. `common.py` — `spawn_background_ix_map()` now catches all exceptions and logs to stderr (never stdout):

```python
def spawn_background_ix_map(cwd: str | Path | None) -> None:
    try:
        subprocess.Popen(["ix", "map"], ...)
    except Exception as exc:
        log(f"[ix] spawn_background_ix_map failed (non-fatal): {exc}")
```

2. `after_tool.py` and `session_end.py` — `main()` now wraps all logic in try/except so any unexpected exception produces a stderr log and exits 0.

Also removed the unused `emit_json` import from `after_tool.py` and `session_end.py`.

---

## Hook code review — `hooks/*.py`

| File | Assessment |
|---|---|
| `common.py` | Fixed — `spawn_background_ix_map` wrapped in try/except |
| `session_start.py` | Correct — emits `additionalContext` |
| `before_agent.py` | Correct — emits `additionalContext`, TTL-gated briefing |
| `before_tool.py` | Correct — emits `decision: allow` + `systemMessage` |
| `after_tool.py` | Fixed — main() fail-safe; unused import removed |
| `session_end.py` | Fixed — main() fail-safe; unused import removed |

---

## Extension manifest review — `gemini-extension.json`

After fixes:

| Field | Status |
|---|---|
| `name` | Valid |
| `version` | Valid |
| `description` | Valid |
| `author` | Valid (not in spec but harmless) |
| `hooks` | **Removed** — was invalid |
| `skills` | **Removed** — was invalid |

Skills will be auto-discovered from `skills/<name>/SKILL.md` once converted. Hooks will be loaded from `hooks/hooks.json`.

---

## Local verification performed (2026-05-17)

- [x] `python3 hooks/tests/test_hooks.py` — 11 tests pass (after_tool, session_end, before_tool, _is_write_command)
- [x] `npm test` in `mcp/` — 6 TypeScript tests pass (tool registration, runtime degradation, secret redaction)
- [x] `node dist/server.js` starts and responds to MCP `initialize` with correct server name and tool capabilities
- [x] `after_tool.py` exits 0 on empty stdin, malformed JSON, non-write commands, write commands (even without `ix` installed)
- [x] `session_end.py` exits 0 on empty stdin and malformed JSON
- [x] `gemini-extension.json` now contains `mcpServers` with `${extensionPath}` path that resolves correctly after install

---

## Remaining live Gemini CLI checks

The following require a running Gemini CLI installation to verify:

- [ ] `gemini extensions install .` succeeds and extension appears in `gemini extensions list`
- [ ] MCP server starts automatically from `gemini-extension.json` — `ix_status`, `ix_query`, `ix_decide`, `ix_ingest` visible in Gemini's tool list
- [ ] `SessionStart` hook fires and `additionalContext` is injected
- [ ] `BeforeAgent` hook fires and briefing is injected (when Ix Pro available)
- [ ] `BeforeTool` fires on `run_shell_command` grep/cat calls and injects `systemMessage`
- [ ] `AfterTool` fires after file-writing shell commands without error
- [ ] `SessionEnd` hook fires without error
- [ ] Hook failure (missing `ix`) does not crash Gemini CLI — logs to stderr only
- [ ] Skills appear in `/skills list`
- [ ] `ix_ingest` MCP call succeeds after a file write
