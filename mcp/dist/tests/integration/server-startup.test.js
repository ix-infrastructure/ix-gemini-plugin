import assert from "node:assert/strict";
import test from "node:test";
import { registerAllTools } from "../../server.js";
class FakeServer {
    callbacks = new Map();
    tool(name, _description, _paramsSchema, cb) {
        this.callbacks.set(name, cb);
    }
}
test("registerAllTools exposes the full Gemini MCP tool surface", () => {
    const server = new FakeServer();
    registerAllTools(server);
    const expectedTools = [
        "ix_query",
        "ix_decide",
        "ix_ingest",
        "ix_status",
        "ix_briefing",
        "ix_locate",
        "ix_text",
        "ix_explain",
        "ix_rank",
        "ix_stats",
        "ix_subsystems",
        "ix_inventory",
        "ix_callers",
        "ix_imported_by",
        "ix_callees",
        "ix_imports",
        "ix_depends",
        "ix_trace",
        "ix_impact",
        "ix_health",
        "ix_map",
        "ix_overview",
        "ix_smells",
    ];
    assert.deepEqual([...server.callbacks.keys()].sort(), [...expectedTools].sort());
});
//# sourceMappingURL=server-startup.test.js.map