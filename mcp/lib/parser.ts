import { containsSecret, redactSecrets } from "../shared/secrets.js";

export interface Evidence {
  kind: "graph" | "symbol" | "file";
  id?: string;
  name?: string;
  confidence?: "observed" | "inferred";
}

export interface ToolResultOk {
  ok: true;
  tool: string;
  input: Record<string, unknown>;
  summary: string;
  canonical_revision: number | null;
  preview_markdown: string;
  data: unknown;
  evidence?: Evidence[];
  timing_ms?: number;
}

export interface ToolResultErr {
  ok: false;
  tool: string;
  input: Record<string, unknown>;
  error: {
    code: string;
    message: string;
  };
}

export type ToolResult = ToolResultOk | ToolResultErr;

export class ParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ParseError";
  }
}

// ── Sanitization ──────────────────────────────────────────────────────────────

function sanitizeParsedValue(value: unknown): unknown {
  if (typeof value === "string") {
    return containsSecret(value) ? redactSecrets(value) : value;
  }
  if (Array.isArray(value)) {
    return value.map((entry) => sanitizeParsedValue(entry));
  }
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value).map(([key, entry]) => [key, sanitizeParsedValue(entry)]);
    return Object.fromEntries(entries);
  }
  return value;
}

export function sanitize(value: unknown): unknown {
  return sanitizeParsedValue(value);
}

// ── Envelope builders ─────────────────────────────────────────────────────────

export function wrapOk(
  tool: string,
  input: Record<string, unknown>,
  data: unknown,
  summary: string,
  previewMarkdown: string,
  canonicalRevision: number | null,
  evidence?: Evidence[],
  durationMs?: number,
): ToolResult {
  const sanitizedInput = sanitizeParsedValue(input) as Record<string, unknown>;
  const sanitizedSummary = sanitizeParsedValue(summary) as string;
  const sanitizedPreviewMarkdown = sanitizeParsedValue(previewMarkdown) as string;
  const sanitizedData = sanitizeParsedValue(data);
  const sanitizedEvidence = evidence === undefined
    ? undefined
    : sanitizeParsedValue(evidence) as Evidence[];

  const result: ToolResultOk = {
    ok: true,
    tool,
    input: sanitizedInput,
    summary: sanitizedSummary,
    canonical_revision: canonicalRevision,
    preview_markdown: sanitizedPreviewMarkdown,
    data: sanitizedData,
  };
  if (sanitizedEvidence !== undefined) result.evidence = sanitizedEvidence;
  if (durationMs !== undefined) result.timing_ms = durationMs;
  return result;
}

export function wrapErr(
  tool: string,
  input: Record<string, unknown>,
  err: { code: string; message: string },
): ToolResult {
  return {
    ok: false,
    tool,
    input: sanitizeParsedValue(input) as Record<string, unknown>,
    error: {
      code: err.code,
      message: sanitizeParsedValue(err.message) as string,
    },
  };
}

// ── JSON parser ───────────────────────────────────────────────────────────────

export function parseJson(raw: string): unknown {
  const cleaned = raw.trim();
  if (!cleaned) {
    throw new ParseError("runtime produced no JSON output");
  }
  try {
    const parsed = JSON.parse(cleaned) as unknown;
    return sanitizeParsedValue(parsed);
  } catch (cause) {
    throw new ParseError(
      `runtime output is not valid JSON: ${cleaned.slice(0, 120)}`,
    );
  }
}

export function parseIxJson(raw: string): unknown {
  return parseJson(raw);
}
