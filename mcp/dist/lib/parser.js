import { containsSecret, redactSecrets } from "../shared/secrets.js";
export class ParseError extends Error {
    constructor(message) {
        super(message);
        this.name = "ParseError";
    }
}
// ── Sanitization ──────────────────────────────────────────────────────────────
function sanitizeParsedValue(value) {
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
export function sanitize(value) {
    return sanitizeParsedValue(value);
}
// ── Envelope builders ─────────────────────────────────────────────────────────
export function wrapOk(tool, input, data, summary, previewMarkdown, canonicalRevision, evidence, durationMs) {
    const sanitizedInput = sanitizeParsedValue(input);
    const sanitizedSummary = sanitizeParsedValue(summary);
    const sanitizedPreviewMarkdown = sanitizeParsedValue(previewMarkdown);
    const sanitizedData = sanitizeParsedValue(data);
    const sanitizedEvidence = evidence === undefined
        ? undefined
        : sanitizeParsedValue(evidence);
    const result = {
        ok: true,
        tool,
        input: sanitizedInput,
        summary: sanitizedSummary,
        canonical_revision: canonicalRevision,
        preview_markdown: sanitizedPreviewMarkdown,
        data: sanitizedData,
    };
    if (sanitizedEvidence !== undefined)
        result.evidence = sanitizedEvidence;
    if (durationMs !== undefined)
        result.timing_ms = durationMs;
    return result;
}
export function wrapErr(tool, input, err) {
    return {
        ok: false,
        tool,
        input: sanitizeParsedValue(input),
        error: {
            code: err.code,
            message: sanitizeParsedValue(err.message),
        },
    };
}
// ── JSON parser ───────────────────────────────────────────────────────────────
export function parseJson(raw) {
    const cleaned = raw.trim();
    if (!cleaned) {
        throw new ParseError("runtime produced no JSON output");
    }
    try {
        const parsed = JSON.parse(cleaned);
        return sanitizeParsedValue(parsed);
    }
    catch (cause) {
        throw new ParseError(`runtime output is not valid JSON: ${cleaned.slice(0, 120)}`);
    }
}
export function parseIxJson(raw) {
    return parseJson(raw);
}
//# sourceMappingURL=parser.js.map