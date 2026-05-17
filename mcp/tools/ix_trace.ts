import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { graphQueryRuntime } from "../lib/runtime-client.js";
import { wrapErr, wrapOk, type ToolResult } from "../lib/parser.js";
import { registerIxTool, type ToolInput } from "./base.js";

const TOOL_NAME = "ix_trace";

const inputSchema = {
  symbol: z.string().min(1, "symbol is required"),
  to: z.string().min(1).optional(),
};

type TraceInput = ToolInput<typeof inputSchema>;

interface TraceNode {
  name?: string;
  kind?: string;
  path?: string;
  cycle?: boolean;
  children?: TraceNode[];
}

interface TraceSide {
  tree?: TraceNode[];
  summary?: { nodes_visited?: number; max_depth?: number };
}

interface TraceResponse {
  canonical_revision?: number;
  preview_markdown?: string;
  mode?: string;
  target?: { name?: string; kind?: string; path?: string };
  direction?: string;
  upstream?: TraceSide;
  downstream?: TraceSide;
}

export function register(server: McpServer): void {
  registerIxTool(server, {
    name: TOOL_NAME,
    description: "Trace execution paths through a symbol — upstream callers and downstream callees",
    schema: inputSchema,
    handler: runTrace,
  });
}

async function runTrace(input: TraceInput): Promise<ToolResult> {
  const body: Record<string, unknown> = {
    operation: "trace",
    selectors: [{ kind: "symbol", value: input.symbol }],
  };
  if (input.to) body["to"] = input.to;

  const response = await graphQueryRuntime<TraceResponse>(body);

  if (!response.ok) {
    return wrapErr(TOOL_NAME, input as unknown as Record<string, unknown>, {
      code: response.code,
      message: response.message,
    });
  }

  const raw = response.data;
  const canonical_revision = response.canonical_revision ?? raw.canonical_revision ?? null;
  const upstream = raw.upstream ?? {};
  const downstream = raw.downstream ?? {};
  const upNodes = upstream.summary?.nodes_visited ?? 0;
  const downNodes = downstream.summary?.nodes_visited ?? 0;

  const name = raw.target?.name ?? input.symbol;
  const summary = upNodes === 0 && downNodes === 0
    ? `No trace paths found for ${name}`
    : `Traced ${name}: ${upNodes} upstream nodes, ${downNodes} downstream nodes`;

  const preview_markdown = raw.preview_markdown ?? [
    `## ix_trace: ${name}`,
    "",
    `**Upstream:** ${upNodes} nodes | **Downstream:** ${downNodes} nodes`,
  ].join("\n");

  return wrapOk(
    TOOL_NAME,
    input as unknown as Record<string, unknown>,
    {
      mode: raw.mode ?? null,
      target: raw.target
        ? { name: raw.target.name ?? null, kind: raw.target.kind ?? null, path: raw.target.path ?? null }
        : null,
      direction: raw.direction ?? null,
      upstream: {
        tree: upstream.tree ?? [],
        summary: { nodes_visited: upNodes, max_depth: upstream.summary?.max_depth ?? 0 },
      },
      downstream: {
        tree: downstream.tree ?? [],
        summary: { nodes_visited: downNodes, max_depth: downstream.summary?.max_depth ?? 0 },
      },
    },
    summary,
    preview_markdown,
    canonical_revision,
    undefined,
    response.duration_ms,
  );
}
