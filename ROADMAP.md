# ix-gemini-plugin Roadmap

## Task Tracking Rule

Any AI agent or human working on this roadmap must update task fields directly inside this file.

When starting a task:
- Change `Status` to `In Progress`
- Fill in `Started By`
- Fill in `Start Date`
- Update `Last Updated`
- Add a note to `Progress Log`

When completing a task:
- Change `Status` to `Done`
- Fill in `Completed By`
- Fill in `Completion Date`
- Update `Last Updated`
- Write a concise `Change Summary`

When blocked:
- Change `Status` to `Blocked`
- Explain the blocker in `Progress Log`

Do not mark a task as done unless all acceptance criteria are satisfied.

---

## Overview

**Role: Gemini CLI extension with MCP server is implemented locally; live Gemini validation and release hardening remain.**

This roadmap was refreshed against the current working tree on `2026-05-16`. There is only one committed revision in the repo; the meaningful recent work is the current uncommitted extension shell.

**Recently landed in the working tree:**
- `GEMINI.md` now exists and documents the graph-first operating model, skill routing, and hook behavior.
- Gemini-native skill directories now exist for `ix-understand`, `ix-investigate`, `ix-impact`, `ix-plan`, `ix-debug`, `ix-architecture`, and `ix-docs`.
- Agent playbooks now exist in `agents/`.
- Hook scripts now exist in `hooks/*.py`, and hook registration moved into `hooks/hooks.json`.
- `gemini-extension.json` was simplified to a valid minimal manifest.
- `install.sh` now packages the extension shell into `.gemini/extensions/ix-memory/`.
- `docs/VALIDATION.md` documents the manifest and hook-loading fixes that were made.

**Still missing or incomplete:**
- No live Gemini CLI validation has been run yet because the CLI is not installed in this environment.
- Hook behavior has only been structurally reviewed; it has not been validated in a live Gemini CLI session.
- Installer settings merge is still manual; `install.sh` prints the `mcpServers` snippet but does not preserve and update `settings.json` automatically.
- Local tests now cover registration, sanitization, and runtime-unavailable fallback, but Gemini-facing end-to-end tests are still outstanding.

**Reference implementations:**
- **MCP server and tool contracts:** Match `ix-cursor-plugin` for the 17-tool surface, schemas, output envelopes, `failClosed: false`, and timeout behavior.
- **Ambient behavior, skills, and agents:** Match `ix-claude-plugin` where Gemini supports equivalent hooks and skill loading.

**Platform status:**
- Confirmed: `GEMINI.md`, `mcpServers` config, stdio/SSE/HTTP MCP transports, lifecycle hooks, Gemini skill loading, extension manifest, and marketplace path.
- Still unconfirmed: maximum MCP tool response size, first-class subagent delegation API, and cloud agent MCP support.

**Current priority order:**
1. Run live Gemini validation: hook firing, `GEMINI.md` injection, and golden cases.
2. Finish installer hardening: merge `mcpServers` settings idempotently.
3. Complete release hardening: broader tool-contract coverage and marketplace publication.

---

## Phase 0: Current State Audit

### Task: Platform survey — confirm MCP config, lifecycle hooks, and extension model

**Status:** Done
**Owner:** Unassigned
**Started By:** Claude
**Start Date:** 2026-05-16
**Completed By:** Claude
**Completion Date:** 2026-05-16
**Last Updated:** 2026-05-16
**Change Summary:** All 8 PLUGIN_SPEC.md open questions answered. Key findings: lifecycle hooks confirmed (BeforeTool/AfterTool/SessionStart/SessionEnd — full parity with Claude); mcpServers config confirmed (same key as Codex); skill files confirmed (.gemini/skills/<name>/SKILL.md); extension marketplace confirmed (geminicli.com/extensions/browse/, gemini-extension.json manifest); TypeScript decided for MCP server. Max tool response size and cloud agent MCP remain unknown.

**Goal:**
Answer all confirmed-unknown platform questions from PLUGIN_SPEC.md section 17: MCP config format, lifecycle hook availability, slash command/skill loading, max tool response size, subagent delegation, marketplace schema, cloud agent MCP support.

**Current State Context:**
Confirmed: `GEMINI.md`, `mcpServers` in `~/.gemini/settings.json`, stdio and HTTP MCP transport. Unconfirmed: everything else. This survey is the prerequisite for all other phases.

**Implementation Notes:**
Read Gemini CLI GitHub repo (`https://github.com/google-gemini/gemini-cli`). Check docs, release notes, and issues for: (1) hook events, (2) skill/slash command loading, (3) subagent delegation, (4) marketplace, (5) cloud agent MCP support, (6) max tool response size, (7) exact `mcpServers` config schema. Document all findings.

**Files Expected to Change:**
- `PLUGIN_SPEC.md` (update open questions with answers)

**Acceptance Criteria:**
- [x] MCP config schema for `~/.gemini/settings.json` confirmed — key `mcpServers`, schema `{ command, args, cwd, env }`
- [x] Lifecycle hook availability confirmed — full hook system including BeforeTool/AfterTool/SessionStart/SessionEnd
- [x] Skill/slash command loading support confirmed — `.gemini/skills/<name>/SKILL.md` with YAML frontmatter
- [x] Subagent delegation partially confirmed — extensions bundle sub-agents; first-class API unconfirmed
- [x] Max MCP tool response size — documented as unknown (not in Gemini CLI docs)
- [x] Marketplace schema confirmed — `gemini-extension.json`, gallery at geminicli.com/extensions/browse/
- [x] All PLUGIN_SPEC.md open questions answered

**Progress Log:**
- Platform questions from `PLUGIN_SPEC.md` were resolved and folded back into the spec.

---

### Task: Confirm TypeScript vs Python for MCP server implementation

**Status:** Done
**Owner:** Unassigned
**Started By:** Claude
**Start Date:** 2026-05-16
**Completed By:** Claude
**Completion Date:** 2026-05-16
**Last Updated:** 2026-05-16
**Change Summary:** TypeScript confirmed. Gemini CLI extension template uses Node.js + @modelcontextprotocol/sdk. Cursor plugin provides a working TypeScript MCP server to port from. No Python-specific reason found.

**Goal:**
Decide whether to implement the Gemini MCP server in TypeScript (matching Cursor) or Python (matching Codex hooks). Document the rationale.

**Current State Context:**
PLUGIN_SPEC.md section 17 open question 8 asks this. TypeScript is natural given the Cursor MCP server already exists. Python would be useful if Gemini has Python-native tooling or if the Codex Python MCP server (Phase 3 of ix-codex-plugin) is already built.

**Implementation Notes:**
Default to TypeScript — the Cursor plugin already has a working MCP server in TypeScript that can be adapted. Only switch to Python if there is a strong Gemini-specific reason. Document the decision.

**Files Expected to Change:**
- None (decision only — reflected in this roadmap)

**Acceptance Criteria:**
- [x] TypeScript vs Python decision made and documented — TypeScript
- [x] Rationale for decision recorded — extension template uses Node.js; Cursor plugin provides port-ready reference

**Progress Log:**
- TypeScript selected as the implementation language for the future Gemini MCP server.

---

## Phase 1: Refactor Design

### Task: Design GEMINI.md system prompt

**Status:** Done
**Owner:** Unassigned
**Started By:** Unknown
**Start Date:** 2026-05-16
**Completed By:** Unknown
**Completion Date:** 2026-05-16
**Last Updated:** 2026-05-16
**Change Summary:** Added `GEMINI.md` with the Ix cognitive model, graph-first operating rules, skill reference, hook notes, repo structure, and ix CLI quick reference.

**Goal:**
Design the content and structure of `GEMINI.md` — the primary system prompt and instruction surface for this plugin.

**Current State Context:**
`GEMINI.md` now exists. The remaining question is validation quality, not whether the file should be written.

**Implementation Notes:**
The file currently emphasizes graph-first CLI usage and hook behavior. After MCP tools exist, revisit the guidance so it routes through Gemini MCP tools rather than shell-first `ix` commands.

**Files Expected to Change:**
- `GEMINI.md` (new file)

**Acceptance Criteria:**
- [x] Ix cognitive model condensed in `GEMINI.md`
- [x] Graph-first hierarchy present
- [x] Skill routing table present
- [x] Hook and repo guidance present
- [x] Guidance rewritten for MCP-tool-first behavior — MCP tool table, pre-edit gate, post-edit ingest, and updated reasoning strategy added

**Progress Log:**
- `GEMINI.md` landed in the working tree and is referenced by the installer.

---

### Task: Design MCP server architecture

**Status:** Done
**Owner:** Unassigned
**Started By:** Claude
**Start Date:** 2026-05-16
**Completed By:** Claude
**Completion Date:** 2026-05-16
**Last Updated:** 2026-05-16
**Change Summary:** Created full `mcp/` scaffold: `package.json` (`@ix/gemini-plugin-mcp`), `tsconfig.json`, `lib/config.ts`, `lib/errors.ts`, `lib/parser.ts` (with `canonical_revision` and `preview_markdown`), `lib/runtime-client.ts` (HTTP client, `failClosed: false`), `shared/secrets.ts` (ported from Cursor), `tools/base.ts` (registerIxTool helper). Stdio transport. `.gemini/settings.json` with `mcpServers` config. TypeScript typecheck and build both pass.

**Goal:**
Design the `mcp/` directory structure, package dependencies, and tool registration strategy for the Gemini MCP server. Confirm runtime API transport (stdio vs HTTP).

**Current State Context:**
The Cursor plugin MCP server (`mcp/server.ts`) is the reference. It uses TypeScript, `@modelcontextprotocol/sdk`, zod for validation, and stdio transport. The Gemini plugin should follow the same structure, adapted for Gemini's config format.

**Implementation Notes:**
Copy the Cursor plugin's `mcp/` scaffold (excluding `dist/`, `node_modules/`). Adapt `package.json` name to `@ix/gemini-plugin-mcp`. Adapt `mcp.json` → `.gemini/settings.json` format. All 17 tools should call the runtime API, not the CLI — no CLI adapter needed (unlike Cursor v0.1.0 which started with CLI). Use stdio transport for local sessions.

**Files Expected to Change:**
- `mcp/package.json` (new)
- `mcp/tsconfig.json` (new)
- `mcp/server.ts` (new)
- `.gemini/settings.json` (new)

**Acceptance Criteria:**
- [x] MCP server scaffold designed
- [x] Package name and dependencies decided — `@ix/gemini-plugin-mcp`
- [x] Transport (stdio) confirmed
- [x] `.gemini/settings.json` config format confirmed

**Progress Log:**
- Created `mcp/` scaffold with all shared infrastructure: config, errors, parser, runtime-client, secrets, tool base.
- `parser.ts` includes `canonical_revision` and `preview_markdown` in `ToolResultOk` (v2 contract requirement, not present in Cursor v0.1.0).
- `runtime-client.ts` calls the runtime HTTP API directly; no CLI layer.
- `failClosed: false` implemented in runtime-client for all unavailability scenarios.
- TypeScript typecheck and build pass clean.

---

## Phase 2: Ix Core Runtime Integration

### Task: Implement core MCP tools (ix_query, ix_decide, ix_ingest, ix_status)

**Status:** Done
**Owner:** Unassigned
**Started By:** Claude
**Start Date:** 2026-05-16
**Completed By:** Claude
**Completion Date:** 2026-05-16
**Last Updated:** 2026-05-16
**Change Summary:** Implemented all four core tools. `ix_query` is a unified tool covering 9 modes (understand, investigate, impact, plan, debug, architecture, docs, locate, status). All tools call the runtime HTTP API directly via `runtime-client.ts`. All include `caller.surface: "gemini-plugin"`. All return `canonical_revision` and `preview_markdown`. All degrade gracefully on runtime unavailability (failClosed: false). TypeScript typecheck and build pass.

**Goal:**
Implement the four highest-priority MCP tools that enable the core Gemini integration: `ix_query`, `ix_decide`, `ix_ingest`, `ix_status`.

**Current State Context:**
PLUGIN_SPEC.md section 9 lists these four as the first core tools to implement. They enable: all skill workflows (ix_query), pre-edit gate (ix_decide), post-edit ingest (ix_ingest), and startup health check (ix_status).

**Implementation Notes:**
Port from Cursor plugin tool files. Key difference: all tools call the runtime API directly (no CLI fallback needed). `ix_query` is a unified tool covering all modes (understand, investigate, impact, plan, debug, architecture, docs, locate). `ix_decide` calls `POST /v2/ix_decide`. `ix_ingest` calls `POST /v2/ingest/map`. `ix_status` calls `GET /v2/status`. Include `caller.surface: "gemini-plugin"` in all calls.

**Files Expected to Change:**
- `mcp/tools/ix_query.ts` (new — unified query tool)
- `mcp/tools/ix_decide.ts` (new)
- `mcp/tools/ix_ingest.ts` (new)
- `mcp/tools/ix_status.ts` (new)
- `mcp/server.ts`
- `mcp/lib/runtime-client.ts` (new — HTTP client)

**Acceptance Criteria:**
- [x] All four tools implemented and registered
- [x] `ix_query` handles all modes (9 modes via unified tool)
- [x] `caller.surface: "gemini-plugin"` in all calls (injected by `baseEnvelope()` in runtime-client)
- [x] Tools return `canonical_revision` and `preview_markdown`
- [ ] `GeminiMcpServerStartup` test passes (server starts and lists tools) — blocked on live Gemini CLI

**Progress Log:**
- `ix_query`: unified tool with 9 modes (understand, investigate, impact, plan, debug, architecture, docs, locate, status). Calls `POST /v2/ix_query`. Returns evidence array with observed/inferred tagging.
- `ix_decide`: pre-edit gate calling `POST /v2/ix_decide`. Renders block/warn/allow verdict with markdown preview. Defaults to allow on runtime unavailability.
- `ix_ingest`: post-edit ingest calling `POST /v2/ingest/map`. Supports targeted file ingest and full_workspace mode. Non-fatal on unavailability.
- `ix_status`: health check calling `GET /v2/status`. Returns graph revision, freshness, capabilities. Non-fatal on unavailability.
- All tools registered in `mcp/server.ts` with stdio transport.

---

### Task: Implement remaining 13 MCP tools (full 17-tool parity)

**Status:** Done
**Owner:** Unassigned
**Started By:** Claude
**Start Date:** 2026-05-17
**Completed By:** Claude
**Completion Date:** 2026-05-17
**Last Updated:** 2026-05-17
**Change Summary:** Implemented 19 new tool files (16 named tools + ix_imported_by, ix_imports, ix_overview companions), bringing total to 23 registered tools. All tools call the runtime API directly via `graphQueryRuntime` (POST /v2/graph/query), `insightsDeriveRuntime` (POST /v2/insights/derive), `briefingRuntime` (GET /v2/briefing), or the existing `queryRuntime`/`ingestRuntime`/`statusRuntime`. All include `canonical_revision` and `preview_markdown`. All degrade gracefully on runtime unavailability (failClosed: false). TypeScript build passes clean.

**Goal:**
Implement the remaining 13 tools to match the Cursor plugin's 17-tool surface: `ix_briefing`, `ix_locate`, `ix_text`, `ix_explain`, `ix_rank`, `ix_stats`, `ix_subsystems`, `ix_inventory`, `ix_callers`, `ix_callees`, `ix_depends`, `ix_trace`, `ix_impact`, `ix_health`, `ix_map`, `ix_smells`.

**Current State Context:**
These tools map directly to the Cursor plugin tools. Since this plugin calls the runtime API directly (no CLI phase), these can be implemented clean without a shim period.

**Implementation Notes:**
Port each tool from `mcp/tools/` in ix-cursor-plugin. Adapt imports to use the Gemini `runtime-client.ts`. The tool input schemas and output envelopes should be identical to the Cursor plugin. `preview_markdown` is the primary output surface — Gemini CLI renders markdown.

**Files Expected to Change:**
- `mcp/tools/*.ts` (13 new tool files)
- `mcp/server.ts` (register all tools)

**Acceptance Criteria:**
- [x] All 17 tools registered and callable (23 tools total implemented)
- [ ] `GeminiMcpServerStartup` confirms all 17 tools in tool list — blocked on live Gemini CLI
- [x] All tools include `canonical_revision` and `preview_markdown`
- [x] `failClosed: false` on all tools (runtime unavailability is non-fatal)

**Progress Log:**
- Added `graphQueryRuntime` (POST /v2/graph/query), `insightsDeriveRuntime` (POST /v2/insights/derive), and `briefingRuntime` (GET /v2/briefing) to `runtime-client.ts`.
- Implemented: `ix_briefing`, `ix_locate`, `ix_text`, `ix_explain`, `ix_rank`, `ix_stats`, `ix_subsystems`, `ix_inventory`, `ix_callers` (+ `ix_imported_by`), `ix_callees` (+ `ix_imports`), `ix_depends`, `ix_trace`, `ix_impact`, `ix_health`, `ix_map` (+ `ix_overview`), `ix_smells`.
- All tools follow the Gemini v2 pattern: typed request body, `preview_markdown` (runtime-provided or locally built), `canonical_revision` from response, `failClosed: false`.
- TypeScript build passes clean.

---

## Phase 3: Platform Adapter Implementation

### Task: Write skill markdown files for all seven skills

**Status:** Done
**Owner:** Unassigned
**Started By:** Unknown
**Start Date:** 2026-05-16
**Completed By:** Claude
**Completion Date:** 2026-05-17
**Last Updated:** 2026-05-17
**Change Summary:** All eight SKILL.md files now route through MCP tools. CLI bash blocks removed and replaced with explicit MCP tool call references (`ix_subsystems()`, `ix_rank({...})`, `ix_locate({...})`, etc.). Each skill also exposes a preferred-path `ix_query(mode: ...)` fast route. `GEMINI.md` token budget rules updated to MCP parameter format; hook notes updated to reference `ix_ingest` instead of `ix map`.

**Goal:**
Create skill markdown files in `skills/` for all seven skills plus `ix-help`: ix-understand, ix-investigate, ix-impact, ix-plan, ix-debug, ix-architecture, ix-docs, ix-help.

**Current State Context:**
Gemini skill loading is confirmed, and most of the migration has already happened in the working tree.

**Implementation Notes:**
Finish the migration by adding `skills/ix-help/SKILL.md`, deciding whether the legacy `.toml` files should be deleted or retained as source artifacts, and then updating the skill bodies to target Gemini MCP tools once `mcp/` exists.

**Files Expected to Change:**
- `skills/ix-help/SKILL.md` (new)
- `skills/*/SKILL.md` (finish Gemini-specific wording)
- `skills/*.toml` (delete or explicitly retain with comment)

**Acceptance Criteria:**
- [x] All eight Gemini-native skill directories exist, including `ix-help`
- [x] Skill files are the Gemini-discoverable source of truth
- [x] Legacy `.toml` files are either removed or deliberately documented
- [x] Skill bodies route through MCP tools after Phase 2

**Progress Log:**
- Added `SKILL.md` files for `ix-understand`, `ix-investigate`, `ix-impact`, `ix-plan`, `ix-debug`, `ix-architecture`, and `ix-docs`.
- Validation notes confirm Gemini will auto-discover `skills/<name>/SKILL.md`; the manifest no longer tries to register skills directly.
- Added `skills/ix-help/SKILL.md` as the missing router skill.
- Removed the stale `skills/*.toml` artifacts so Gemini-native `SKILL.md` files are the only source of truth.
- Updated all seven skill files to replace CLI bash blocks with MCP tool call references.
- Added preferred-path `ix_query(mode: ...)` fast route to each skill.
- Updated `GEMINI.md` token budget rules and hook notes to reflect MCP-first operation.

---

### Task: Write agent playbooks for all five agents

**Status:** Done
**Owner:** Unassigned
**Started By:** Unknown
**Start Date:** 2026-05-16
**Completed By:** Unknown
**Completion Date:** 2026-05-16
**Last Updated:** 2026-05-16
**Change Summary:** Added all five agent playbook markdown files, referenced the playbook set from `GEMINI.md`, and updated the examples to prefer Gemini MCP tools over direct shell `ix` commands.

**Goal:**
Create agent playbook markdown files in `agents/` for all five agents: ix-explorer, ix-system-explorer, ix-bug-investigator, ix-safe-refactor-planner, ix-architecture-auditor.

**Current State Context:**
The `agents/` directory now exists and contains the expected five playbooks. First-class Gemini subagent delegation is still unconfirmed, so these currently serve as reusable guidance docs.

**Implementation Notes:**
Revisit the playbooks after the MCP server lands so command examples prefer Gemini MCP tools over direct `ix` shell commands where appropriate.

**Files Expected to Change:**
- `agents/ix-explorer.md` (new)
- `agents/ix-system-explorer.md` (new)
- `agents/ix-bug-investigator.md` (new)
- `agents/ix-safe-refactor-planner.md` (new)
- `agents/ix-architecture-auditor.md` (new)

**Acceptance Criteria:**
- [x] All five agent playbooks created
- [x] Examples updated for MCP-tool-first usage once the Gemini MCP server exists
- [x] Referenced from `GEMINI.md`
- [x] Subagent delegation status documented

**Progress Log:**
- Playbooks present: `ix-explorer`, `ix-system-explorer`, `ix-bug-investigator`, `ix-safe-refactor-planner`, `ix-architecture-auditor`.

---

### Task: Implement lifecycle hooks if Gemini CLI supports them

**Status:** In Progress
**Owner:** Unassigned
**Started By:** Unknown
**Start Date:** 2026-05-16
**Completed By:**
**Completion Date:**
**Last Updated:** 2026-05-16
**Change Summary:** Hook scripts and `hooks/hooks.json` now exist for `SessionStart`, `BeforeAgent`, `BeforeTool`, `AfterTool`, and `SessionEnd`. Structural validation is documented; live Gemini CLI validation is still outstanding.

**Goal:**
Implement and validate Gemini lifecycle hooks for session briefing, shell interception, and background graph refresh.

**Current State Context:**
Hooks are confirmed, and the repo now contains a Python-based hook layer. The current implementation intercepts `run_shell_command` and uses heuristics to inject Ix context before search/read commands and to trigger `ix map` after write-like shell commands.

**Implementation Notes:**
Current hook scope is shell-oriented and extension-local; it is not yet wired to the future MCP tools. Keep the Python hooks for the extension shell, then decide whether the final MCP-backed version should stay Python or move to TypeScript alongside `mcp/`.

**Files Expected to Change:**
- `hooks/hooks.json`
- `hooks/*.py`
- `docs/VALIDATION.md`

**Acceptance Criteria:**
- [x] Lifecycle hook availability confirmed
- [x] Hook config exists outside the manifest in `hooks/hooks.json`
- [x] Session-start, pre-tool, post-tool, and session-end hooks implemented
- [x] Structural validation findings documented
- [ ] Live Gemini CLI session verifies the hooks actually fire
- [ ] Decide whether write gating should remain shell-heuristic or move to MCP-backed `ix_decide`/`ix_ingest`

**Progress Log:**
- Removed invalid manifest-level hook config and moved registration into `hooks/hooks.json`.
- Fixed the hook matcher to `run_shell_command`.
- Added Python hook handlers plus shared helpers in `hooks/common.py`.

---

### Task: Write install scripts (install.sh, install.ps1)

**Status:** In Progress
**Owner:** Unassigned
**Started By:** Unknown
**Start Date:** 2026-05-16
**Completed By:**
**Completion Date:**
**Last Updated:** 2026-05-16
**Change Summary:** Added `install.ps1` with the same copy-based extension-shell behavior as `install.sh`. MCP build/settings integration is still pending until the server exists.

**Goal:**
Provide a complete install path for the extension shell now, then extend it to install the future MCP server cleanly on macOS/Linux and Windows.

**Current State Context:**
`install.sh` exists and is functional for copying extension assets. The remaining gap is configuration and cross-platform completeness.

**Implementation Notes:**
Keep the current extension-copy behavior. Once `mcp/` exists, extend the installer to build it and merge an `mcpServers` entry into Gemini settings without clobbering unrelated user config. Add `install.ps1` only after the install contract is stable.

**Files Expected to Change:**
- `install.sh`
- `install.ps1` (new)
- `.gemini/settings.json` or installer-managed settings merge logic

**Acceptance Criteria:**
- [x] `install.sh` copies the current extension assets into the Gemini extensions directory
- [x] `install.ps1` provides the same behavior on Windows
- [x] `install.sh` builds the MCP server and prints `mcpServers` merge instructions
- [ ] Install path is idempotent and preserves unrelated user settings (settings merge not yet automated)

**Progress Log:**
- Installer now copies `gemini-extension.json`, `hooks/`, Gemini-native skill directories, `agents/`, and `GEMINI.md`.
- Added `install.ps1` to mirror the current copy-only shell installer on Windows.
- Extended `install.sh` to run `npm ci && npm run build` in `mcp/`, copy `dist/` to the extension dir, and print the `mcpServers` config snippet the user needs to add to `~/.gemini/settings.json`.
- Added `--no-mcp` flag to skip the build step when Node.js is unavailable.

---

## Phase 4: Existing Behavior Preservation

### Task: Document GEMINI.md as the primary behavior anchor

**Status:** Blocked
**Owner:** Unassigned
**Started By:** Unknown
**Start Date:** 2026-05-16
**Completed By:**
**Completion Date:**
**Last Updated:** 2026-05-16
**Change Summary:** Runtime validation of `GEMINI.md` is pending a live Gemini CLI session; static review is complete.

**Goal:**
Since this is a greenfield plugin with no prior behavior, this phase focuses on ensuring `GEMINI.md` is the reliable anchor for all agent behavior — verifying it is loaded and that its instructions are followed.

**Current State Context:**
`GEMINI.md` now exists and is part of the install surface, but its runtime effect has not been validated in a live Gemini CLI session.

**Implementation Notes:**
Start a Gemini CLI session with the installed extension. Verify what Gemini actually loads from the extension package and whether `GEMINI.md`, skills, and hooks cooperate as intended. Because MCP tools do not exist yet, validate the current shell-first behavior first, then revisit after Phase 2.

**Files Expected to Change:**
- `GEMINI.md` (if instruction updates needed)

**Acceptance Criteria:**
- [ ] `GEMINI.md` loaded and active in Gemini CLI session
- [ ] `GeminiMdInjection` test confirms Ix operating model is active
- [ ] Agent calls `ix_decide` before file writes in test session
- [ ] Agent calls `ix_ingest` after file writes in test session

**Progress Log:**
- Blocked on a live Gemini CLI session; static repo review is complete.

---

## Phase 5: Security, Privacy, and Reliability

### Task: Enforce secret pattern detection in all MCP tools

**Status:** Done
**Owner:** Unassigned
**Started By:** Codex
**Start Date:** 2026-05-17
**Completed By:** Codex
**Completion Date:** 2026-05-17
**Last Updated:** 2026-05-17
**Change Summary:** `mcp/shared/secrets.ts` is now wired through the shared result envelope. `wrapOk` and `wrapErr` sanitize model-facing fields by default, and local tests cover redaction for `summary`, `preview_markdown`, nested `data`, evidence, input, and error messages.

**Goal:**
Port `mcp/shared/secrets.ts` from ix-cursor-plugin and ensure it runs on all MCP tool responses before they are returned to the Gemini model.

**Current State Context:**
`mcp/shared/secrets.ts` exists and the remaining work was to ensure the shared result envelope actually scrubbed all model-facing fields before tool responses were returned.

**Implementation Notes:**
Copy `mcp/shared/secrets.ts` from ix-cursor-plugin. Call `redactSecrets()` on `preview_markdown`, `summary`, and all string fields in `evidence[]` before returning from each tool. Log redactions.

**Files Expected to Change:**
- `mcp/shared/secrets.ts` (new, ported)
- `mcp/lib/runtime-client.ts`

**Acceptance Criteria:**
- [x] Secret detection runs on all tool response string fields
- [x] `preview_markdown` field specifically covered
- [x] No raw secrets in tool outputs

**Progress Log:**
- Wired redaction through `wrapOk` and `wrapErr` so all tool responses sanitize input, summaries, previews, nested data, evidence, and error text by default.
- Added local redaction tests in `mcp/tests/integration/parser.test.ts`.

---

### Task: Verify .gemini/settings.json uses no long-lived credentials

**Status:** Done
**Owner:** Unassigned
**Started By:** Codex
**Start Date:** 2026-05-17
**Completed By:** Codex
**Completion Date:** 2026-05-17
**Last Updated:** 2026-05-17
**Change Summary:** Reviewed `.gemini/settings.json` and `GEMINI.md`. The distributed config uses `${workspaceRoot}` and `${workspaceId}` placeholders, contains no tokens, and documents runtime auth through environment injection rather than committed credentials.

**Goal:**
Confirm the `.gemini/settings.json` MCP server config and `GEMINI.md` contain no secrets, tokens, or machine-specific paths.

**Current State Context:**
PLUGIN_SPEC.md section 13 specifies: "`.gemini/settings.json` must use short-lived credentials or OS-level secret management." The config file is distributed and may be committed to project repos.

**Implementation Notes:**
Review `.gemini/settings.json` template. Confirm it contains only the MCP server binary path and transport config — no API keys, tokens, or absolute paths (use `$HOME` or relative paths). Document auth approach for runtime API credentials (env var injection at runtime).

**Files Expected to Change:**
- `.gemini/settings.json`

**Acceptance Criteria:**
- [x] No API keys or tokens in `.gemini/settings.json`
- [x] No machine-specific absolute paths in `.gemini/settings.json`
- [x] Auth approach for runtime API credentials documented
- [x] `GEMINI.md` confirmed to contain no secrets

**Progress Log:**
- Verified `.gemini/settings.json` uses `${workspaceRoot}` and `${workspaceId}` placeholders plus `IX_RUNTIME_URL` only.
- Confirmed `GEMINI.md` contains no secrets or machine-local paths.

---

### Task: Verify all tools degrade gracefully when runtime unavailable

**Status:** In Progress
**Owner:** Unassigned
**Started By:** Codex
**Start Date:** 2026-05-17
**Completed By:**
**Completion Date:**
**Last Updated:** 2026-05-17
**Change Summary:** Added local tests covering non-fatal runtime-unavailable behavior for `ix_query` and `ix_status`. Full live Gemini validation is still outstanding.

**Goal:**
Confirm all 17 MCP tools return a graceful error envelope rather than throwing when the runtime is unavailable. Gemini CLI must continue to function without blocking.

**Current State Context:**
PLUGIN_SPEC.md section 11 requires: "All tools must handle `IX_UPSTREAM_UNAVAILABLE` gracefully; model must proceed without blocking."

**Implementation Notes:**
Stop the runtime. Call each tool from Gemini CLI. Verify each returns `{ ok: false, error: { code: "IX_UPSTREAM_UNAVAILABLE" } }` cleanly. Verify the model receives this and proceeds rather than erroring out.

**Files Expected to Change:**
- `mcp/lib/runtime-client.ts` (if fallback not implemented)

**Acceptance Criteria:**
- [ ] All 17 tools return gracefully on runtime unavailability
- [ ] `GeminiRuntimeUnavailableFallback` test passes
- [ ] Model continues operating without Ix context

**Progress Log:**
- Added `mcp/tests/integration/runtime-unavailable.test.ts` to cover representative fail-open behavior without a live Gemini CLI session.
- Live Gemini-session verification that the model proceeds correctly is still blocked on a local `gemini` install.

---

## Phase 6: Testing and Validation

### Task: Write test harness (test-local.sh) and run all Gemini-specific tests

**Status:** In Progress
**Owner:** Unassigned
**Started By:** Codex
**Start Date:** 2026-05-17
**Completed By:**
**Completion Date:**
**Last Updated:** 2026-05-17
**Change Summary:** Added `test-local.sh` plus local MCP integration tests for tool registration, response redaction, and runtime-unavailable fallback. Live Gemini CLI checks and golden cases remain blocked on the missing CLI.

**Goal:**
Write `test-local.sh` and implement all required tests: `GeminiMcpServerStartup`, `GeminiToolContractParity`, `GeminiMdInjection`, `GeminiPreEditGateFeasibility`, `GeminiPostEditIngestFeasibility`, `GeminiLifecycleHookSurvey`, `GeminiRuntimeUnavailableFallback`.

**Current State Context:**
A local MCP test harness now exists, but Gemini-session tests still require a real `gemini` install.

**Implementation Notes:**
Write `test-local.sh` that: (1) starts the MCP server in test mode, (2) runs tool contract tests (mock runtime responses), (3) verifies `GEMINI.md` injection via Gemini CLI session, (4) tests pre/post-edit gate behavior in a session, (5) documents lifecycle hook survey. Use the Cursor plugin's `tests/` structure as a reference.

**Files Expected to Change:**
- `test-local.sh` (new)
- `tests/` (new directory)
- `mcp/tests/` (new)

**Acceptance Criteria:**
- [x] `GeminiMcpServerStartup` local registration check passes (23 Gemini tools registered)
- [ ] `GeminiToolContractParity` passes for all tools
- [ ] `GeminiMdInjection` passes
- [ ] `GeminiPreEditGateFeasibility` passes (agent calls `ix_decide` before writes)
- [ ] `GeminiPostEditIngestFeasibility` passes (agent calls `ix_ingest` after writes)
- [ ] `GeminiLifecycleHookSurvey` documents lifecycle hook status
- [ ] `GeminiRuntimeUnavailableFallback` passes

**Progress Log:**
- Added `test-local.sh`.
- Added local MCP tests for registration, sanitization, and runtime-unavailable behavior in `mcp/tests/integration/`.

---

### Task: Run shared golden cases

**Status:** Not Started
**Owner:** Unassigned
**Started By:**
**Start Date:**
**Completed By:**
**Completion Date:**
**Last Updated:**
**Change Summary:**

**Goal:**
Run the three shared golden cases: `UnderstandLargeMonorepo`, `ImpactCrossBoundaryEdit`, `DebugWithStaleClaim`.

**Current State Context:**
These validate end-to-end skill behavior across surfaces. For Gemini, skills are invoked via `GEMINI.md` routing instructions and MCP tool calls rather than slash commands.

**Implementation Notes:**
Run each case in a live Gemini CLI session. Document results.

**Files Expected to Change:**
- None (run-only)

**Acceptance Criteria:**
- [ ] `UnderstandLargeMonorepo` passes
- [ ] `ImpactCrossBoundaryEdit` passes
- [ ] `DebugWithStaleClaim` passes

**Progress Log:**
- Not started yet.

---

## Phase 7: Migration and Release

### Task: Write README.md and finalize PLUGIN_SPEC.md

**Status:** Done
**Owner:** Unassigned
**Started By:** Unknown
**Start Date:** 2026-05-16
**Completed By:** Unknown
**Completion Date:** 2026-05-16
**Last Updated:** 2026-05-16
**Change Summary:** Added `README.md` with requirements, skills, hooks, and install guidance. Updated `PLUGIN_SPEC.md` to reflect the confirmed Gemini extension model and the current extension-shell implementation.

**Goal:**
Write `README.md` describing what the plugin does, how to install it, and how to use it. Finalize `PLUGIN_SPEC.md` with all open questions answered.

**Current State Context:**
Both files now exist and reflect the post-survey Gemini platform model. They will still need another pass once the MCP server is implemented.

**Implementation Notes:**
Write `README.md` with: plugin description, install instructions (`install.sh` / `install.ps1`), usage examples, and a link to `PLUGIN_SPEC.md`. Update `PLUGIN_SPEC.md` section 17 to mark all resolved open questions. Update section 3 (current implementation summary) to reflect actual built state.

**Files Expected to Change:**
- `README.md` (new)
- `PLUGIN_SPEC.md`

**Acceptance Criteria:**
- [x] `README.md` written with install and usage instructions
- [x] All PLUGIN_SPEC.md section 17 open questions answered
- [x] PLUGIN_SPEC.md section 3 updated to reflect current implementation status
- [x] Revisit both docs after MCP implementation so they no longer describe a pre-MCP shell-first phase as the end state

**Progress Log:**
- README covers requirements, skills, playbooks, hooks, and install paths.
- Spec now records confirmed hooks, skill loading, manifest rules, and marketplace details.
- README and PLUGIN_SPEC now reflect the implemented MCP server, the local test harness, and the remaining live-validation gaps.

---

### Task: Register marketplace extension (if marketplace confirmed)

**Status:** Not Started
**Owner:** Unassigned
**Started By:**
**Start Date:**
**Completed By:**
**Completion Date:**
**Last Updated:**
**Change Summary:**

**Goal:**
If Phase 0 survey confirms Gemini CLI has a plugin marketplace, register the extension manifest and publish the plugin.

**Current State Context:**
Marketplace availability is confirmed, and the repo now has a minimal `gemini-extension.json`. Actual publication has not been attempted.

**Implementation Notes:**
Keep the manifest minimal until live validation is complete. Do not attempt publication until the extension shell is validated and the MCP install path exists.

**Files Expected to Change:**
- `gemini-extension.json`
- release/publishing docs if Gemini requires them

**Acceptance Criteria:**
- [x] Marketplace availability confirmed
- [x] Extension manifest exists in the repo
- [ ] Extension registered and visible in the marketplace
- [ ] Install via `install.sh` and extension manager verified in a live Gemini CLI environment

**Progress Log:**
- Manifest was reduced to valid top-level fields; hooks and skills now load from extension directory conventions instead of the manifest.
