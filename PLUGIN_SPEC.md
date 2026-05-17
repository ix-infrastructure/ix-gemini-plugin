# ix-gemini-plugin — Plugin Specification

Version: 2.0.0-draft  
Root spec: [IX_PLUGIN_OVERHAUL_SPEC.md](../IX_PLUGIN_OVERHAUL_SPEC.md)  
Status: **In progress.** MCP server, skills, hooks, installers, and agent docs exist. Remaining work is live Gemini validation, installer settings merge automation, and release hardening.

---

## 1. Plugin name

`ix-memory` (Gemini CLI plugin/extension ID — Unknown / needs verification)  
Repository: `ix-gemini-plugin`

---

## 2. Target AI platform

**Google Gemini CLI** — Google's open-source terminal AI agent powered by Gemini models.  
GitHub: https://github.com/google-gemini/gemini-cli  
Distribution: Per-project `.gemini/` config + MCP server registration in `~/.gemini/settings.json`. Marketplace confirmed: https://geminicli.com/extensions/browse/ — extensions installed via `gemini extensions install <github-url>`, manifest is `gemini-extension.json`.

---

## 3. Current implementation summary

**Extension shell and MCP server both exist.** The repo now contains `GEMINI.md`, Gemini-native `skills/<name>/SKILL.md` directories, five agent playbooks, Python hook scripts in `hooks/`, a minimal `gemini-extension.json`, macOS/Linux and Windows installers, and a TypeScript `mcp/` server exposing the Gemini Ix tool surface.

**What is confirmed about the Gemini CLI platform (Phase 0 survey complete):**
- Uses `GEMINI.md` as the primary system prompt injection mechanism (equivalent to `CLAUDE.md`)
- Supports **MCP servers** configured in `~/.gemini/settings.json` or `.gemini/settings.json` under `mcpServers` — key is identical to Codex; schema: `{ command, args, cwd, env }`
- Supports stdio, SSE, and Streamable HTTP MCP transports
- Runs as a local terminal agent with full shell access via tool calls
- Function calling is the model's tool invocation mechanism
- **Lifecycle hooks confirmed** — full hook system: `SessionStart`, `SessionEnd`, `BeforeTool`, `AfterTool`, `BeforeAgent`, `AfterAgent`, `BeforeModel`, `AfterModel`, `BeforeToolSelection`, `Notification`, `PreCompress`. Hooks defined in `settings.json` under `hooks`. MCP tool matcher pattern: `mcp_<server_name>_<tool_name>`. `BeforeTool`/`AfterTool` can block, modify args, or replace responses.
- **Skill files confirmed** — skills live in `.gemini/skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`). Discovered automatically; activated by the built-in `activate_skill` tool. Discovery tiers: built-in → extension → user (`~/.gemini/skills/`) → workspace (`.gemini/skills/`).
- **Custom commands confirmed** — `.gemini/commands/<name>.toml` for slash commands.
- **Extension marketplace confirmed** — https://geminicli.com/extensions/browse/. Install via `gemini extensions install <github-url>`. Manifest: `gemini-extension.json` with `name`, `version`, `mcpServers`, optional `contextFileName`, skills, hooks, themes.
- **ACP mode confirmed** — JSON-RPC over stdio for IDE integration. ACP clients can expose their own MCP server to Gemini.

**What remains unconfirmed:**
- Maximum MCP tool response size (not documented; treat as unknown)
- Subagent delegation (extensions mention sub-agents but first-class delegation API unconfirmed)
- Cloud agent MCP support

---

## 4. Existing files and behavior to preserve

Preserve the current MCP-first Gemini integration:
- TypeScript MCP server in `mcp/`
- `GEMINI.md` operating model and skill routing
- Gemini-native `skills/<name>/SKILL.md` directories
- Python hook layer in `hooks/`
- Installers in `install.sh` and `install.ps1`

---

## 5. Known gaps and stale areas

| Gap | Impact |
|---|---|
| Live Gemini CLI validation is still blocked in this environment | Hook firing, `GEMINI.md` injection, and golden cases remain unverified end to end |
| Installer does not merge settings.json automatically | Install remains manual at the `mcpServers` merge step |
| MCP tests cover only local registration / fallback / redaction paths so far | Gemini-facing behavior still needs live-session validation |
| Max MCP tool response size unknown | Cannot finalize output budgeting; treat as uncapped until confirmed |
| Subagent delegation unconfirmed | Agent playbooks work as documentation; first-class delegation not yet planned |
| Cloud agent MCP support unconfirmed | Cannot plan cloud bootstrap path |

**Resolved gaps (Phase 0):**
| Gap | Resolution |
|---|---|
| Lifecycle hooks | Confirmed — `BeforeTool`/`AfterTool` enable automatic pre/post-edit gate |
| Extension manifest | Confirmed — `gemini-extension.json` |
| Skill file loading | Confirmed — `.gemini/skills/<name>/SKILL.md` with YAML frontmatter |
| Marketplace | Confirmed — geminicli.com/extensions/browse/ |

---

## 6. Desired refactor outcome

This is not a refactor — it is a greenfield implementation. The goal is to bring the full seven-skill, five-agent Ix capability set to Gemini CLI users via:
1. MCP server exposing Ix Core Runtime tools
2. `GEMINI.md` system prompt providing Ix operating guidance and skill routing
3. Agent-driven pre-edit gate and post-edit ingest (via `ix_decide` and `ix_ingest` MCP tools)
4. Skill markdown files for each of the seven skills

Priority order:
1. MCP server + `GEMINI.md` (core capability)
2. All seven skill workflows reachable via tool calls
3. Pre-edit gate — automatic via `BeforeTool` hook + `ix_decide`
4. Post-edit ingest — automatic via `AfterTool` hook + `ix_ingest`
5. Session-start briefing — automatic via `SessionStart` hook
6. Extension manifest (`gemini-extension.json`) and marketplace registration

---

## 7. Platform-specific integration model

### What Gemini CLI provides

| Mechanism | Description | Equivalent |
|---|---|---|
| `GEMINI.md` | System prompt injected from project root; advisory context | `CLAUDE.md` (Claude), `AGENTS.md` (Codex/OpenCode) |
| MCP server (`~/.gemini/settings.json`) | Registers external MCP servers; tools callable by the model | `mcp.json` (Cursor), MCP config (Codex/OpenCode) |
| Stdio MCP transport | Local process communication | Same as Claude/Cursor |
| HTTP MCP transport | Remote server communication | Same as Claude/Cursor |
| Function calling | Model invokes registered tools | Same as all other surfaces |

### What Gemini CLI provides (updated after Phase 0 survey)

| Mechanism | Description | Confirmed |
|---|---|---|
| `GEMINI.md` | System prompt injected from project root | Yes |
| `mcpServers` in `settings.json` | Registers external MCP servers | Yes |
| Stdio / SSE / HTTP MCP transport | Three transport options | Yes |
| `BeforeTool` / `AfterTool` hooks | Pre/post tool interception with matcher regex | Yes |
| `SessionStart` / `SessionEnd` hooks | Session lifecycle events | Yes |
| `BeforeAgent` / `AfterAgent` hooks | Per-turn prompt/response interception | Yes |
| `BeforeModel` / `AfterModel` hooks | LLM request/response interception | Yes |
| Skill files | `.gemini/skills/<name>/SKILL.md` with YAML frontmatter | Yes |
| Custom commands | `.gemini/commands/<name>.toml` slash commands | Yes |
| Extension manifest | `gemini-extension.json` | Yes |
| Extension marketplace | geminicli.com/extensions/browse/ | Yes |
| Subagent delegation | First-class API unconfirmed | Partial |
| Cloud agent MCP | Unknown | No |

### Integration strategy

The primary integration model (updated now that hooks are confirmed):
1. **MCP as the tool surface** — all Ix capabilities exposed as MCP tools
2. **`GEMINI.md` as the instruction surface** — Ix operating model, routing table
3. **Automatic hooks** — `BeforeTool` intercepts write/edit tool calls → `ix_decide`; `AfterTool` intercepts write/edit completions → `ix_ingest`; `SessionStart` injects briefing
4. **Skill files** — each of the seven skills as `.gemini/skills/<name>/SKILL.md`, activated on demand by the model

This is now equivalent to the Claude model (event-driven hooks + skill files), not the degraded agent-driven-only model originally assumed.

---

## 8. Required Ix capabilities

| Capability | Mechanism | Priority |
|---|---|---|
| `POST /v2/ix_query` all modes | MCP tool `ix_query` | High |
| `POST /v2/ix_decide` | MCP tool `ix_decide` | High |
| `POST /v2/ingest/map` | MCP tool `ix_ingest` | High |
| `GET /v2/status` | MCP tool `ix_status` | High |
| `POST /v2/graph/query` | MCP tools `ix_locate`, `ix_explain`, etc. | Medium |
| `POST /v2/insights/derive` | MCP tools `ix_rank`, `ix_smells` | Medium |
| Session briefing | `GEMINI.md` instruction + `ix_status` tool | High |
| Pre-edit gate | `GEMINI.md` instruction + `ix_decide` tool + hook integration | High |
| Post-edit ingest | `GEMINI.md` instruction + `ix_ingest` tool + hook integration | High |

---

## 9. Required hooks, skills, agents, commands, and MCP integrations

### MCP tools (target: 17 matching Cursor)

Core tools (required immediately):
`ix_query`, `ix_decide`, `ix_ingest`, `ix_status`

Full tool set (matching Cursor plugin):
`ix_briefing`, `ix_locate`, `ix_text`, `ix_explain`, `ix_rank`, `ix_stats`, `ix_subsystems`, `ix_inventory`, `ix_callers`, `ix_callees`, `ix_depends`, `ix_trace`, `ix_impact`, `ix_decide`, `ix_health`, `ix_map`, `ix_smells`

### `GEMINI.md`

Must include:
- Condensed Ix operating model from `skills/shared.md`
- Graph-first reasoning guidance (prefer tools over raw reads)
- Skill routing table (which tool to call for each user query type)
- Pre-edit gate instruction: "Before writing to any file, call `ix_decide` with the file path"
- Post-edit ingest instruction: "After writing to any file, call `ix_ingest` with the file path"
- Stale-index warning handling

### Skills

Implement as `.gemini/skills/<name>/SKILL.md` files with YAML frontmatter (`name`, `description`). Gemini CLI discovers and activates these automatically via the built-in `activate_skill` tool. Do NOT use `skills/*.toml` (that is Claude Code format).

Skills: `ix-understand`, `ix-investigate`, `ix-impact`, `ix-plan`, `ix-debug`, `ix-architecture`, `ix-docs`, `ix-help`

### Agents

Implement as markdown files in `agents/` referenced from `GEMINI.md`:
`ix-explorer`, `ix-system-explorer`, `ix-bug-investigator`, `ix-safe-refactor-planner`, `ix-architecture-auditor`

First-class subagent delegation API is unconfirmed; agent files serve as documentation and behavior guidance.

### Lifecycle hooks

Hooks are confirmed. Current implementation uses extension-local shell hooks in `hooks/hooks.json`:
- `SessionStart` → call `ix_status`, inject Ix briefing into `additionalContext`
- `BeforeTool` with matcher `write_file|edit_file|replace_file` (or regex covering all write tools) → call `ix_decide`
- `AfterTool` with same matcher → call `ix_ingest`
- `SessionEnd` → call `ix_map` asynchronously

Hook commands are shell scripts in `hooks/`. MCP tool names follow pattern `mcp_<server_name>_<tool_name>` for matcher-based interception when live Gemini validation is available.

---

## 10. Required folder structure after implementation

```
ix-gemini-plugin/
├── .gemini/
│   └── settings.json            # MCP server config (per-project override of ~/.gemini/settings.json)
├── mcp/
│   ├── server.ts                # MCP server entry point (TypeScript, matches Cursor pattern)
│   ├── package.json
│   ├── tsconfig.json
│   └── tools/
│       ├── [17 tool implementations]
│       └── base.ts
├── skills/
│   ├── ix-help/
│   │   └── SKILL.md
│   ├── ix-understand/
│   │   └── SKILL.md
│   ├── ix-investigate/
│   │   └── SKILL.md
│   ├── ix-impact/
│   │   └── SKILL.md
│   ├── ix-plan/
│   │   └── SKILL.md
│   ├── ix-debug/
│   │   └── SKILL.md
│   ├── ix-architecture/
│   │   └── SKILL.md
│   └── ix-docs/
│       └── SKILL.md
├── agents/
│   ├── ix-explorer.md
│   ├── ix-system-explorer.md
│   ├── ix-bug-investigator.md
│   ├── ix-safe-refactor-planner.md
│   └── ix-architecture-auditor.md
├── GEMINI.md                    # System prompt — Ix operating model + routing + gate instructions
├── install.sh
├── install.ps1
├── PLUGIN_SPEC.md               # This file
└── README.md
```

---

## 11. Shared Ix Core Runtime requirements

See [IX_PLUGIN_OVERHAUL_SPEC.md](../IX_PLUGIN_OVERHAUL_SPEC.md). Plugin-specific notes:

- `caller.surface = "gemini-plugin"` in all API calls.
- MCP tool responses must include `canonical_revision` and `preview_markdown`.
- `preview_markdown` is the primary human-facing output; Gemini CLI renders markdown in the terminal.
- All tools must handle `IX_UPSTREAM_UNAVAILABLE` gracefully; model must proceed without blocking.
- MCP server should use stdio for local sessions; HTTP for remote/cloud.

---

## 12. API contracts used by this plugin

| API | MCP tool | Notes |
|---|---|---|
| `POST /v2/ix_query` | `ix_query`, all skill tools | `caller.surface = "gemini-plugin"` |
| `POST /v2/ix_decide` | `ix_decide` | Called by agent before file edits |
| `POST /v2/ingest/map` | `ix_ingest` | Called by agent after file edits; and at session end |
| `GET /v2/status` | `ix_status` | Used in `GEMINI.md` startup check |
| `POST /v2/graph/query` | `ix_locate`, `ix_explain`, traversal tools | |
| `POST /v2/insights/derive` | `ix_rank`, `ix_smells` | |

---

## 13. Security and privacy requirements

- `GEMINI.md` must not include secrets, tokens, or machine-specific paths.
- `.gemini/settings.json` must use short-lived credentials or OS-level secret management.
- MCP tool responses must not include raw source code unless explicitly requested.
- MCP server must run with the same user permissions as the Gemini CLI process; no privilege elevation.
- Secret pattern detection must run before any string is submitted to Ix via MCP tool calls.

---

## 14. Testing requirements

| Test | Coverage |
|---|---|
| `GeminiMcpServerStartup` | MCP server starts and registers all 17 tools |
| `GeminiToolContractParity` | All tool outputs match `ix_query` / `ix_decide` contract |
| `GeminiMdInjection` | `GEMINI.md` is loaded by Gemini CLI and Ix operating model is active |
| `GeminiPreEditGateFeasibility` | Agent reliably calls `ix_decide` before file writes |
| `GeminiPostEditIngestFeasibility` | Agent reliably calls `ix_ingest` after file writes |
| `GeminiLifecycleHookSurvey` | Documents which lifecycle hooks (if any) are available |
| `GeminiRuntimeUnavailableFallback` | All tools degrade gracefully when runtime is unavailable |
| Shared golden cases | `UnderstandLargeMonorepo`, `ImpactCrossBoundaryEdit`, `DebugWithStaleClaim` |

---

## 15. Migration plan

This is a greenfield implementation. No migration from a prior version. Build order:

| Step | Action | Risk |
|---|---|---|
| 1. Platform survey | Verify MCP transport, config format, lifecycle hooks, slash command support | High (unknowns) |
| 2. MCP server skeleton | Copy Cursor MCP server structure; adapt for Gemini CLI config format | Low |
| 3. Core tools | Implement `ix_query`, `ix_decide`, `ix_ingest`, `ix_status` | Low |
| 4. `GEMINI.md` | Write system prompt with Ix operating model, routing table, gate instructions | Low |
| 5. Full tool set | Implement remaining 13 tools matching Cursor plugin | Medium |
| 6. Skills and agents | Write skill markdown files and agent playbooks | Low |
| 7. Lifecycle hooks | Validate the current hook layer live and decide whether to move write gating from shell heuristics to MCP matchers | Medium |
| 8. Install scripts | Write `install.sh` and `install.ps1` | Low |
| 9. Test harness | Write `test-local.sh` using shared golden cases | Medium |
| 10. Marketplace registration | Register extension manifest if marketplace is available | Unknown |

---

## 16. Acceptance criteria

- [ ] Gemini CLI loads the Ix MCP server from `.gemini/settings.json` or `~/.gemini/settings.json`.
- [ ] All 17 MCP tools are registered and callable by the Gemini model.
- [ ] `GEMINI.md` is loaded and Ix operating model is active.
- [ ] All seven skill workflows are reachable via MCP tool calls.
- [ ] Agent reliably calls `ix_decide` before file edits.
- [ ] Agent reliably calls `ix_ingest` after file edits.
- [ ] Lifecycle hooks (if any): documented with verified status.
- [ ] All tools degrade gracefully when runtime is unavailable.
- [ ] Shared golden cases pass.
- [x] No secrets or machine-specific paths in the distributed `.gemini/settings.json` template.

---

## 17. Open questions

**All questions resolved by Phase 0 survey (2026-05-16). Source: https://github.com/google-gemini/gemini-cli docs.**

1. **Does Gemini CLI support lifecycle hooks?**
   **CONFIRMED YES.** Full hook system: `SessionStart`, `SessionEnd`, `BeforeTool`, `AfterTool`, `BeforeAgent`, `AfterAgent`, `BeforeModel`, `AfterModel`, `BeforeToolSelection`, `Notification`, `PreCompress`. Configured in `settings.json` under `hooks`. `BeforeTool`/`AfterTool` support regex matchers and can block, modify args, or replace responses. MCP tools match as `mcp_<server_name>_<tool_name>`. Integration is now fully automatic — equivalent to Claude, not degraded agent-driven.

2. **What is the exact MCP config format in `~/.gemini/settings.json`?**
   **CONFIRMED.** Key is `mcpServers` (same as Codex). Schema: `{ "mcpServers": { "<name>": { "command": "...", "args": [...], "cwd": "...", "env": {...} } } }`. Works in `~/.gemini/settings.json` (user) and `.gemini/settings.json` (project). Transports: stdio, SSE, Streamable HTTP. Extension manifest uses same `mcpServers` schema.

3. **Does Gemini CLI support slash commands or skill-file loading?**
   **CONFIRMED YES.** Skills: `.gemini/skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`). Discovered at session start; activated on demand by the built-in `activate_skill` tool. Discovery tiers: built-in → extension → user (`~/.gemini/skills/`) → workspace (`.gemini/skills/`). Slash commands: `.gemini/commands/<name>.toml`.

4. **What is the maximum MCP tool response size?**
   **UNKNOWN.** Not documented. Treat as uncapped; apply output budgeting defensively.

5. **Does Gemini CLI support subagent delegation?**
   **PARTIALLY CONFIRMED.** Extensions can bundle sub-agents. ACP mode supports IDE↔agent bidirectional tool exposure. First-class delegation API (like Claude's `Agent` tool) not confirmed.

6. **Is there a Gemini CLI plugin marketplace?**
   **CONFIRMED YES.** Gallery: https://geminicli.com/extensions/browse/. Install: `gemini extensions install <github-url>`. Manifest: `gemini-extension.json` with `name`, `version`, `mcpServers`, optional `contextFileName`, skills, hooks, themes.

7. **Does Gemini CLI have a cloud agent mode with MCP support?**
   **UNCONFIRMED.** ACP mode enables IDE integration via JSON-RPC over stdio. Hosted cloud agent mode with MCP not found in docs.

8. **TypeScript or Python for MCP server?**
   **DECISION: TypeScript.** Extension template uses Node.js + `@modelcontextprotocol/sdk`. Cursor plugin provides a working TypeScript MCP server to port from. No Gemini-specific reason to use Python.


---

## Roadmap

See [`ROADMAP.md`](./ROADMAP.md) for phased implementation tasks and progress tracking.
