import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { graphQueryRuntime } from "../lib/runtime-client.js";
import { wrapErr, wrapOk, type ToolResult } from "../lib/parser.js";
import { registerIxTool, type ToolInput } from "./base.js";

const TOOL_NAME = "ix_inventory";

const inputSchema = {
  kind: z.string().min(1).default("file"),
  path: z.string().min(1, "path is required"),
};

type InventoryInput = ToolInput<typeof inputSchema>;

interface InventoryResponse {
  canonical_revision?: number;
  preview_markdown?: string;
  kind?: string;
  scope?: string;
  total?: number;
  byFile?: Array<{ path?: string; items?: string[] }>;
}

export function register(server: McpServer): void {
  registerIxTool(server, {
    name: TOOL_NAME,
    description: "List files or symbols within a repository path scope",
    schema: inputSchema,
    handler: runInventory,
  });
}

async function runInventory(input: InventoryInput): Promise<ToolResult> {
  const response = await graphQueryRuntime<InventoryResponse>({
    operation: "inventory",
    selectors: [{ kind: "path", value: input.path }],
    entity_kind: input.kind,
  });

  if (!response.ok) {
    return wrapErr(TOOL_NAME, input as unknown as Record<string, unknown>, {
      code: response.code,
      message: response.message,
    });
  }

  const raw = response.data;
  const canonical_revision = response.canonical_revision ?? raw.canonical_revision ?? null;
  const entries = Array.isArray(raw.byFile) ? raw.byFile : [];
  const total = raw.total ?? entries.length;

  const items = entries.map((e) => ({
    path: e.path ?? null,
    items: Array.isArray(e.items) ? e.items : [],
  }));

  const summary = `Found ${total} ${input.kind} entries in ${input.path}`;
  const preview_markdown = raw.preview_markdown ?? buildInventoryPreview(input.path, input.kind, items, total);

  return wrapOk(
    TOOL_NAME,
    input as unknown as Record<string, unknown>,
    {
      kind: raw.kind ?? input.kind,
      scope: raw.scope ?? input.path,
      total,
      items,
    },
    summary,
    preview_markdown,
    canonical_revision,
    undefined,
    response.duration_ms,
  );
}

function buildInventoryPreview(path: string, kind: string, items: Array<{ path: string | null; items: string[] }>, total: number): string {
  const lines = [`## ix_inventory: \`${path}\` (${kind})`, "", `**${total} entries**`, ""];
  for (const e of items.slice(0, 20)) {
    const itemList = e.items.length > 0 ? `: ${e.items.slice(0, 3).join(", ")}${e.items.length > 3 ? "…" : ""}` : "";
    lines.push(`- \`${e.path ?? "?"}\`${itemList}`);
  }
  if (total > 20) lines.push(`\n_...and ${total - 20} more_`);
  return lines.join("\n");
}
