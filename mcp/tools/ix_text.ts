import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { graphQueryRuntime } from "../lib/runtime-client.js";
import { wrapErr, wrapOk, type ToolResult } from "../lib/parser.js";
import { registerIxTool, type ToolInput } from "./base.js";

const TOOL_NAME = "ix_text";
const DEFAULT_LIMIT = 20;

const inputSchema = {
  pattern: z.string().min(1, "pattern is required"),
  limit: z.number().int().positive().max(100).optional(),
  path: z.string().min(1).optional(),
  language: z.string().min(1).optional(),
};

type TextInput = ToolInput<typeof inputSchema>;

interface TextHit {
  path?: string;
  line_start?: number;
  line_end?: number;
  snippet?: string;
  engine?: string;
  score?: number;
  language?: string;
}

interface TextResponse {
  canonical_revision?: number;
  preview_markdown?: string;
  hits?: TextHit[];
  total?: number;
}

export function register(server: McpServer): void {
  registerIxTool(server, {
    name: TOOL_NAME,
    description: "Search text across the indexed repository and return ranked hits",
    schema: inputSchema,
    handler: runText,
  });
}

async function runText(input: TextInput): Promise<ToolResult> {
  const limit = input.limit ?? DEFAULT_LIMIT;
  const body: Record<string, unknown> = {
    operation: "text_search",
    pattern: input.pattern,
    limit,
  };
  if (input.path) body["path"] = input.path;
  if (input.language) body["language"] = input.language;

  const response = await graphQueryRuntime<TextResponse>(body);

  if (!response.ok) {
    return wrapErr(TOOL_NAME, input as unknown as Record<string, unknown>, {
      code: response.code,
      message: response.message,
    });
  }

  const raw = response.data;
  const canonical_revision = response.canonical_revision ?? raw.canonical_revision ?? null;

  const rawHits = Array.isArray(raw.hits) ? raw.hits : [];
  const hits = rawHits.map((h) => ({
    path: h.path ?? null,
    line_start: h.line_start ?? null,
    line_end: h.line_end ?? null,
    snippet: h.snippet ?? null,
    engine: h.engine ?? null,
    score: h.score ?? null,
    language: h.language ?? null,
  }));

  const total = raw.total ?? hits.length;
  const summary = total === 0
    ? `No text hits found for ${input.pattern}`
    : `Found ${total} text hits for ${input.pattern}`;

  const preview_markdown = raw.preview_markdown ?? buildTextPreview(input.pattern, hits, total);

  return wrapOk(
    TOOL_NAME,
    { ...input, limit } as unknown as Record<string, unknown>,
    { hits, total },
    summary,
    preview_markdown,
    canonical_revision,
    undefined,
    response.duration_ms,
  );
}

function buildTextPreview(pattern: string, hits: Array<{ path: string | null; line_start: number | null; snippet: string | null }>, total: number): string {
  if (total === 0) {
    return `## ix_text: ${pattern}\n\nNo matches found.`;
  }
  const lines = [`## ix_text: ${pattern}`, "", `**${total} hit${total === 1 ? "" : "s"}**`, ""];
  for (const h of hits.slice(0, 10)) {
    const loc = h.path ? `\`${h.path}\`` : "(unknown)";
    const lineInfo = h.line_start != null ? `:${h.line_start}` : "";
    const snip = h.snippet ? ` — ${h.snippet.slice(0, 80)}` : "";
    lines.push(`- ${loc}${lineInfo}${snip}`);
  }
  if (total > 10) lines.push(`\n_...and ${total - 10} more_`);
  return lines.join("\n");
}
