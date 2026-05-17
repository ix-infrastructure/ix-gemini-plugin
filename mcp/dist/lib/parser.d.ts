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
export declare class ParseError extends Error {
    constructor(message: string);
}
export declare function sanitize(value: unknown): unknown;
export declare function wrapOk(tool: string, input: Record<string, unknown>, data: unknown, summary: string, previewMarkdown: string, canonicalRevision: number | null, evidence?: Evidence[], durationMs?: number): ToolResult;
export declare function wrapErr(tool: string, input: Record<string, unknown>, err: {
    code: string;
    message: string;
}): ToolResult;
export declare function parseJson(raw: string): unknown;
export declare function parseIxJson(raw: string): unknown;
//# sourceMappingURL=parser.d.ts.map