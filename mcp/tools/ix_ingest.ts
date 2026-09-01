import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { TIMEOUT_INGEST_MS, TIMEOUT_MAP_MS } from "../lib/config.js";
import { runIx } from "../lib/cli.js";
import { parseIxJson } from "../lib/parser.js";
import { ingestRuntime } from "../lib/runtime-client.js";
import { wrapErr, wrapOk, type ToolResult } from "../lib/parser.js";
import { registerIxTool, type ToolInput } from "./base.js";

const TOOL_NAME = "ix_ingest";

const inputSchema = {
  paths: z.array(z.string().min(1)).min(1).describe(
    "File paths to ingest into the graph after a write or edit. Pass all paths touched in the current edit.",
  ),
  async_mode: z.boolean().optional().describe(
    "If true, start the ingest job and return immediately without waiting for completion. " +
    "Default: false (wait for completion).",
  ),
  full_workspace: z.boolean().optional().describe(
    "If true, run a full workspace reindex instead of a targeted file ingest. " +
    "Use at session end; slower than targeted ingest.",
  ),
};

type IngestInput = ToolInput<typeof inputSchema>;

interface IngestResponse {
  canonical_revision?: number;
  preview_markdown?: string;
  job_id?: string;
  status?: string;
  files_indexed?: number;
  errors?: string[];
}

interface MapCliResponse {
  map_rev?: number;
  outcome?: string;
  file_count?: number;
  region_count?: number;
}

interface StatusCliResponse {
  currentRev?: number;
  lastIngestAt?: string;
  staleFiles?: number;
}

interface IngestCliResponse {
  filesProcessed?: number;
  patchesApplied?: number;
  commitErrors?: number;
  skipReasons?: { parseError?: number };
}

interface ScopedIngestResult {
  ok: boolean;
  filesIndexed: number;
  errors: string[];
  durationMs: number;
}

/**
 * Ingest exactly the paths that changed.
 *
 * The previous fallback ran a bare `ix map` — a full workspace reindex — no
 * matter how many paths were requested, under the 60s ingest budget. On any
 * checkout with dependencies installed that always timed out, so the fallback
 * could never fire and every edit reported "runtime unavailable" instead (#25).
 *
 * `ix ingest` takes one path per invocation, so walk them. A post-edit hook
 * normally passes one.
 */
async function runScopedIngest(paths: string[]): Promise<ScopedIngestResult> {
  let filesIndexed = 0;
  let durationMs = 0;
  const errors: string[] = [];

  for (const path of paths) {
    const result = await runIx(["ingest", path], { timeout: TIMEOUT_INGEST_MS });
    durationMs += result.durationMs;

    if (!result.ok) {
      errors.push(`${path}: ${result.stderr.trim() || "ix ingest failed"}`);
      continue;
    }

    const raw = parseIxJson(result.stdout) as IngestCliResponse;
    filesIndexed += raw.filesProcessed ?? 0;
    const parseErrors = raw.skipReasons?.parseError ?? 0;
    const commitErrors = raw.commitErrors ?? 0;
    if (parseErrors > 0) errors.push(`${path}: ${parseErrors} file(s) failed to parse`);
    if (commitErrors > 0) errors.push(`${path}: ${commitErrors} patch(es) failed to commit`);
  }

  // A path that failed outright means the graph does not have that edit. Parse
  // and commit errors are reported but do not fail the ingest as a whole.
  return { ok: errors.length === 0 || filesIndexed > 0, filesIndexed, errors, durationMs };
}

export function register(server: McpServer): void {
  registerIxTool(server, {
    name: TOOL_NAME,
    description:
      "Post-edit graph ingest. Call this after writing or editing any file to keep the Ix graph current. " +
      "Pass all file paths touched in the current operation. " +
      "Use full_workspace=true at session end for a complete graph refresh. " +
      "If the runtime is unavailable, returns a non-fatal warning (failClosed: false).",
    schema: inputSchema,
    handler: runIngest,
  });
}

async function runIngest(input: IngestInput): Promise<ToolResult> {
  const body: Record<string, unknown> = {
    paths: input.full_workspace ? [] : input.paths,
    options: {
      async: input.async_mode ?? false,
      full_workspace: input.full_workspace ?? false,
    },
  };

  const response = await ingestRuntime<IngestResponse>(body);

  if (!response.ok) {
    // A full-workspace request is genuinely a remap; a targeted one must only
    // ingest the paths it was given. Sending every edit through `ix map` is what
    // made this fallback unreachable (#25).
    const scoped = input.full_workspace ? null : await runScopedIngest(input.paths);
    const cliResult = scoped
      ? { ok: scoped.ok, stdout: "", stderr: "", durationMs: scoped.durationMs }
      : await runIx(["map"], { timeout: TIMEOUT_MAP_MS });

    if (cliResult.ok) {
      const raw = scoped ? {} as MapCliResponse : parseIxJson(cliResult.stdout) as MapCliResponse;
      const statusResult = await runIx(["status"]);
      const status = statusResult.ok
        ? parseIxJson(statusResult.stdout) as StatusCliResponse
        : null;
      const canonical_revision = raw.map_rev ?? status?.currentRev ?? null;
      const filesIndexed = input.full_workspace
        ? raw.file_count ?? input.paths.length
        : scoped?.filesIndexed ?? input.paths.length;
      const stale = (status?.staleFiles ?? 0) > 0;
      const summary = input.full_workspace
        ? `Full workspace reindex completed at revision ${canonical_revision ?? "unknown"}`
        : `CLI reindex completed after ${filesIndexed} file${filesIndexed === 1 ? "" : "s"} changed`;
      const preview_markdown = [
        input.full_workspace
          ? "## ix_ingest: Full workspace reindex"
          : `## ix_ingest: CLI reindex after ${filesIndexed} file${filesIndexed === 1 ? "" : "s"} changed`,
        "",
        `**Mode:** CLI fallback (\`${input.full_workspace ? "ix map" : "ix ingest"}\`)`,
        raw.outcome ? `**Outcome:** ${raw.outcome}` : "",
        canonical_revision !== null ? `**Graph revision:** ${canonical_revision}` : "",
        status?.lastIngestAt ? `**Last ingest:** ${status.lastIngestAt}` : "",
        stale ? "**Warning:** Index still reports stale files after fallback." : "",
        !input.full_workspace ? "**Files:**" : "",
        ...(!input.full_workspace ? input.paths.map((path) => `- \`${path}\``) : []),
      ]
        .filter(Boolean)
        .join("\n");

      return wrapOk(
        TOOL_NAME,
        input as unknown as Record<string, unknown>,
        {
          ingested: true,
          files_indexed: filesIndexed,
          job_id: null,
          status: "complete",
          errors: scoped?.errors ?? [],
          runtime_available: true,
          fallback: "cli",
          map_outcome: raw.outcome ?? null,
          region_count: raw.region_count ?? null,
          stale,
        },
        summary,
        preview_markdown,
        canonical_revision,
        undefined,
        cliResult.durationMs + (statusResult.ok ? statusResult.durationMs : 0),
      );
    }

    // failClosed: false — runtime unavailability is non-fatal
    const preview_markdown =
      `**ix_ingest**: Runtime unavailable — graph not updated.\n\n` +
      `The Ix graph could not be updated after this edit. Graph context may be stale.\n\n` +
      `Error: ${response.message}`;
    return wrapOk(
      TOOL_NAME,
      input as unknown as Record<string, unknown>,
      { ingested: false, reason: `Runtime unavailable: ${response.message}`, runtime_available: false },
      "Runtime unavailable — graph not updated",
      preview_markdown,
      null,
      undefined,
      response.duration_ms,
    );
  }

  const raw = response.data;
  const canonical_revision = response.canonical_revision ?? raw.canonical_revision ?? null;
  const filesIndexed = raw.files_indexed ?? input.paths.length;
  const errors = Array.isArray(raw.errors) && raw.errors.length > 0 ? raw.errors : null;

  const preview_markdown =
    raw.preview_markdown ??
    buildIngestPreview(input, filesIndexed, canonical_revision, errors);

  const summary = input.full_workspace
    ? `Full workspace reindex completed at revision ${canonical_revision ?? "unknown"}`
    : `Ingested ${filesIndexed} file${filesIndexed === 1 ? "" : "s"} at revision ${canonical_revision ?? "unknown"}`;

  return wrapOk(
    TOOL_NAME,
    input as unknown as Record<string, unknown>,
    {
      ingested: true,
      files_indexed: filesIndexed,
      job_id: raw.job_id ?? null,
      status: raw.status ?? "complete",
      errors: errors ?? [],
      runtime_available: true,
    },
    summary,
    preview_markdown,
    canonical_revision,
    undefined,
    response.duration_ms,
  );
}

function buildIngestPreview(
  input: IngestInput,
  filesIndexed: number,
  revision: number | null,
  errors: string[] | null,
): string {
  const lines: string[] = [];

  if (input.full_workspace) {
    lines.push("## ix_ingest: Full workspace reindex");
  } else {
    lines.push(`## ix_ingest: ${filesIndexed} file${filesIndexed === 1 ? "" : "s"} ingested`);
    lines.push("");
    lines.push("**Files:**");
    for (const p of input.paths) {
      lines.push(`- \`${p}\``);
    }
  }

  if (revision !== null) {
    lines.push("");
    lines.push(`**Graph revision:** ${revision}`);
  }

  if (errors && errors.length > 0) {
    lines.push("");
    lines.push("**Errors:**");
    for (const e of errors) {
      lines.push(`- ${e}`);
    }
  }

  return lines.join("\n");
}
