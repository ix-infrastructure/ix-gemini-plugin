import assert from "node:assert/strict";
import test from "node:test";
import { parseJson, wrapErr, wrapOk } from "../../lib/parser.js";
const SECRET = "Bearer AbCdEf1234567890AbCdEf1234567890";
test("wrapOk redacts secrets across all model-facing fields", () => {
    const result = wrapOk("ix_query", { query: SECRET, nested: { token: SECRET } }, { summary: SECRET, evidence: [{ detail: SECRET }] }, `summary ${SECRET}`, `preview ${SECRET}`, 42, [{ kind: "graph", id: "node-1", name: `name ${SECRET}`, confidence: "observed" }], 12);
    const raw = JSON.stringify(result);
    assert.equal(raw.includes(SECRET), false);
    if (!result.ok) {
        assert.fail("wrapOk should return a success result");
    }
    assert.match(result.summary, /\[REDACTED\]/);
    assert.match(result.preview_markdown, /\[REDACTED\]/);
    assert.match(JSON.stringify(result.input), /\[REDACTED\]/);
    assert.match(JSON.stringify(result.data), /\[REDACTED\]/);
    assert.match(JSON.stringify(result.evidence), /\[REDACTED\]/);
});
test("wrapErr redacts secrets in input and message", () => {
    const result = wrapErr("ix_query", { query: SECRET }, { code: "IX_UPSTREAM_UNAVAILABLE", message: `runtime rejected ${SECRET}` });
    const raw = JSON.stringify(result);
    assert.equal(raw.includes(SECRET), false);
    if (result.ok) {
        assert.fail("wrapErr should return an error result");
    }
    assert.match(result.error.message, /\[REDACTED\]/);
    assert.match(JSON.stringify(result.input), /\[REDACTED\]/);
});
test("parseJson sanitizes string fields recursively", () => {
    const parsed = parseJson(JSON.stringify({
        preview_markdown: `preview ${SECRET}`,
        nested: {
            message: SECRET,
            items: [SECRET],
        },
    }));
    const raw = JSON.stringify(parsed);
    assert.equal(raw.includes(SECRET), false);
    assert.match(raw, /\[REDACTED\]/);
});
//# sourceMappingURL=parser.test.js.map