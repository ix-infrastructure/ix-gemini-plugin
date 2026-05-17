import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { runIx } from "../lib/cli.js";
import { parseIxJson } from "../lib/parser.js";
import { graphQueryRuntime } from "../lib/runtime-client.js";
import { wrapErr, wrapOk, type ToolResult } from "../lib/parser.js";
import { registerIxTool, type ToolInput } from "./base.js";

const CALLERS_TOOL = "ix_callers";
const IMPORTED_BY_TOOL = "ix_imported_by";

const symbolSchema = {
  symbol: z.string().min(1, "symbol is required"),
};

type SymbolInput = ToolInput<typeof symbolSchema>;

interface RelationResult {
  name?: string;
  kind?: string;
  id?: string;
  path?: string;
}

interface RelationResponse {
  canonical_revision?: number;
  preview_markdown?: string;
  results?: RelationResult[];
  resultSource?: string;
  resolvedTarget?: { id?: string; kind?: string; name?: string; path?: string; resolutionMode?: string };
  summary?: { total?: number; resolved?: number; unresolved?: number };
  diagnostics?: Array<{ code?: string; message?: string }>;
}

export function register(server: McpServer): void {
  registerIxTool(server, {
    name: CALLERS_TOOL,
    description: "List entities that call a symbol (incoming call edges)",
    schema: symbolSchema,
    handler: (input) => runRelation(CALLERS_TOOL, "callers", input),
  });

  registerIxTool(server, {
    name: IMPORTED_BY_TOOL,
    description: "List files or symbols that import a given symbol (incoming import edges)",
    schema: symbolSchema,
    handler: (input) => runRelation(IMPORTED_BY_TOOL, "imported_by", input),
  });
}

async function runRelation(toolName: string, operation: string, input: SymbolInput): Promise<ToolResult> {
  const response = await graphQueryRuntime<RelationResponse>({
    operation,
    selectors: [{ kind: "symbol", value: input.symbol }],
  });

  if (!response.ok) {
    const cliArgs = operation === "imported_by" ? ["imported-by", input.symbol] : ["callers", input.symbol];
    const cliResult = await runIx(cliArgs);
    if (cliResult.ok) {
      const raw = parseIxJson(cliResult.stdout) as RelationResponse;
      return buildRelationResult(toolName, input, raw, cliResult.durationMs);
    }

    return wrapErr(toolName, input as unknown as Record<string, unknown>, {
      code: response.code,
      message: response.message,
    });
  }

  const raw = response.data;
  return buildRelationResult(
    toolName,
    input,
    raw,
    response.duration_ms,
    response.canonical_revision ?? raw.canonical_revision ?? null,
  );
}

function buildRelationResult(
  toolName: string,
  input: SymbolInput,
  raw: RelationResponse,
  durationMs: number,
  canonicalRevision: number | null = raw.canonical_revision ?? null,
): ToolResult {
  const results = Array.isArray(raw.results) ? raw.results : [];
  const normalized = results.map((r) => ({
    name: r.name ?? null,
    kind: r.kind ?? null,
    id: r.id ?? null,
    path: r.path ?? null,
  }));

  const resolvedTarget = raw.resolvedTarget;
  const total = raw.summary?.total ?? normalized.length;
  const verb = toolName === IMPORTED_BY_TOOL ? "importers" : "callers";

  const summary = total === 0 ? `No ${verb} found for ${input.symbol}` : `Found ${total} ${verb} for ${input.symbol}`;
  const preview_markdown = raw.preview_markdown ?? buildRelationPreview(toolName, input.symbol, normalized, total);

  return wrapOk(
    toolName,
    input as unknown as Record<string, unknown>,
    {
      results: normalized,
      total,
      resolved_target: resolvedTarget
        ? {
            id: resolvedTarget.id ?? null,
            kind: resolvedTarget.kind ?? null,
            name: resolvedTarget.name ?? null,
            path: resolvedTarget.path ?? null,
            resolution_mode: resolvedTarget.resolutionMode ?? null,
          }
        : null,
      result_source: raw.resultSource ?? null,
      diagnostics: Array.isArray(raw.diagnostics)
        ? raw.diagnostics.map((d) => ({ code: d.code ?? null, message: d.message ?? null }))
        : [],
    },
    summary,
    preview_markdown,
    canonicalRevision,
    undefined,
    durationMs,
  );
}

function buildRelationPreview(
  toolName: string,
  symbol: string,
  results: Array<{ name: string | null; kind: string | null; path: string | null }>,
  total: number,
): string {
  const verb = toolName === IMPORTED_BY_TOOL ? "importers" : "callers";
  if (total === 0) return `## ${toolName}: ${symbol}\n\nNo ${verb} found.`;
  const lines = [`## ${toolName}: ${symbol}`, "", `**${total} ${verb}**`, ""];
  for (const r of results.slice(0, 15)) {
    const kind = r.kind ? ` (${r.kind})` : "";
    const path = r.path ? ` — \`${r.path}\`` : "";
    lines.push(`- \`${r.name ?? "?"}\`${kind}${path}`);
  }
  if (total > 15) lines.push(`\n_...and ${total - 15} more_`);
  return lines.join("\n");
}
