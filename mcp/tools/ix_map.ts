import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { ingestRuntime, graphQueryRuntime } from "../lib/runtime-client.js";
import { wrapErr, wrapOk, type ToolResult } from "../lib/parser.js";
import { registerIxTool, type ToolInput } from "./base.js";

const MAP_TOOL = "ix_map";
const OVERVIEW_TOOL = "ix_overview";

const mapSchema = {
  file: z.string().min(1).optional(),
};

const overviewSchema = {
  target: z.string().min(1, "target is required"),
};

type MapInput = ToolInput<typeof mapSchema>;
type OverviewInput = ToolInput<typeof overviewSchema>;

interface IngestResponse {
  canonical_revision?: number;
  preview_markdown?: string;
  job_id?: string;
  status?: string;
  files_indexed?: number;
  errors?: string[];
}

interface OverviewResponse {
  canonical_revision?: number;
  preview_markdown?: string;
  resolvedTarget?: { id?: string; kind?: string; name?: string };
  resolutionMode?: string;
  path?: string;
  systemPath?: Array<{ name?: string; kind?: string }>;
  hasMapData?: boolean;
  childrenByKind?: Record<string, number>;
  keyItems?: Array<{ name?: string; kind?: string }>;
  containedIn?: { name?: string; kind?: string } | null;
  diagnostics?: string[];
}

export function register(server: McpServer): void {
  registerIxTool(server, {
    name: MAP_TOOL,
    description:
      "Ingest a file into the graph (ix_map file=<path>) or run a full workspace reindex (ix_map with no file). Used by the post-edit hook.",
    schema: mapSchema,
    handler: runMap,
  });

  registerIxTool(server, {
    name: OVERVIEW_TOOL,
    description: "Return a structural overview of a symbol or file — children, key items, and hierarchy position",
    schema: overviewSchema,
    handler: runOverview,
  });
}

async function runMap(input: MapInput): Promise<ToolResult> {
  const body: Record<string, unknown> = {
    paths: input.file ? [input.file] : [],
    options: { async: false, full_workspace: !input.file },
  };

  const response = await ingestRuntime<IngestResponse>(body);

  if (!response.ok) {
    return wrapOk(
      MAP_TOOL,
      input as unknown as Record<string, unknown>,
      { ingested: false, runtime_available: false },
      "Runtime unavailable — graph not updated",
      `## ix_map: Unavailable\n\n**Error:** ${response.message}`,
      null,
      undefined,
      response.duration_ms,
    );
  }

  const raw = response.data;
  const canonical_revision = response.canonical_revision ?? raw.canonical_revision ?? null;
  const filesIndexed = raw.files_indexed ?? (input.file ? 1 : 0);
  const summary = input.file
    ? `Ingested ${input.file} into graph`
    : "Full graph map completed";

  const preview_markdown = raw.preview_markdown ?? [
    `## ix_map${input.file ? `: ${input.file}` : ""}`,
    "",
    input.file ? `Ingested \`${input.file}\` into graph.` : "Full workspace reindex completed.",
    canonical_revision !== null ? `**Graph revision:** ${canonical_revision}` : "",
  ].filter(Boolean).join("\n");

  return wrapOk(
    MAP_TOOL,
    input as unknown as Record<string, unknown>,
    {
      ingested: true,
      files_indexed: filesIndexed,
      job_id: raw.job_id ?? null,
      status: raw.status ?? "complete",
      errors: Array.isArray(raw.errors) ? raw.errors : [],
    },
    summary,
    preview_markdown,
    canonical_revision,
    undefined,
    response.duration_ms,
  );
}

async function runOverview(input: OverviewInput): Promise<ToolResult> {
  const response = await graphQueryRuntime<OverviewResponse>({
    operation: "overview",
    selectors: [{ kind: "path", value: input.target }],
  });

  if (!response.ok) {
    return wrapErr(OVERVIEW_TOOL, input as unknown as Record<string, unknown>, {
      code: response.code,
      message: response.message,
    });
  }

  const raw = response.data;
  const canonical_revision = response.canonical_revision ?? raw.canonical_revision ?? null;
  const resolvedTarget = raw.resolvedTarget;
  const childrenByKind = raw.childrenByKind ?? {};
  const childCount = Object.values(childrenByKind).reduce((a, b) => a + b, 0);
  const name = resolvedTarget?.name ?? input.target;
  const kind = resolvedTarget?.kind ?? "entity";

  const summary = childCount > 0
    ? `Overview of ${kind} ${name} (${childCount} children)`
    : `Overview of ${kind} ${name}`;

  const preview_markdown = raw.preview_markdown ?? buildOverviewPreview(name, kind, raw.path, childrenByKind, raw.keyItems ?? []);

  return wrapOk(
    OVERVIEW_TOOL,
    input as unknown as Record<string, unknown>,
    {
      resolved_target: resolvedTarget
        ? { id: resolvedTarget.id ?? null, kind: resolvedTarget.kind ?? null, name: resolvedTarget.name ?? null }
        : null,
      path: raw.path ?? null,
      resolution_mode: raw.resolutionMode ?? null,
      system_path: Array.isArray(raw.systemPath) ? raw.systemPath : [],
      has_map_data: raw.hasMapData ?? false,
      children_by_kind: childrenByKind,
      key_items: Array.isArray(raw.keyItems) ? raw.keyItems : [],
      contained_in: raw.containedIn ?? null,
      diagnostics: Array.isArray(raw.diagnostics) ? raw.diagnostics : [],
    },
    summary,
    preview_markdown,
    canonical_revision,
    undefined,
    response.duration_ms,
  );
}

function buildOverviewPreview(
  name: string,
  kind: string,
  path: string | undefined,
  childrenByKind: Record<string, number>,
  keyItems: Array<{ name?: string; kind?: string }>,
): string {
  const lines = [
    `## ix_overview: ${name}`,
    "",
    `**Kind:** ${kind}${path ? ` | **Path:** \`${path}\`` : ""}`,
  ];
  const childEntries = Object.entries(childrenByKind).filter(([, n]) => n > 0);
  if (childEntries.length > 0) {
    lines.push(`**Children:** ${childEntries.map(([k, n]) => `${n} ${k}`).join(", ")}`);
  }
  if (keyItems.length > 0) {
    lines.push("", "**Key items:**");
    for (const item of keyItems.slice(0, 8)) {
      lines.push(`- \`${item.name ?? "?"}\` (${item.kind ?? "?"})`);
    }
  }
  return lines.join("\n");
}
