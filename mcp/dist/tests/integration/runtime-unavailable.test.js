import assert from "node:assert/strict";
import test from "node:test";
import { registerAllTools } from "../../server.js";
class FakeServer {
    callbacks = new Map();
    tool(name, _description, _paramsSchema, cb) {
        this.callbacks.set(name, cb);
    }
}
function parseToolResponse(payload) {
    const text = payload.content[0]?.text ?? "";
    return JSON.parse(text);
}
test("ix_query status remains usable when runtime HTTP is unavailable", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => {
        throw new Error("connect ECONNREFUSED");
    };
    try {
        const server = new FakeServer();
        registerAllTools(server);
        const callback = server.callbacks.get("ix_query");
        assert.ok(callback, "ix_query should be registered");
        const response = parseToolResponse(await callback({ mode: "status" }, {}));
        assert.equal(response["ok"], true);
        const data = response["data"];
        assert.equal(data["fallback"], "cli");
        assert.equal(typeof data["current_rev"], "number");
    }
    finally {
        globalThis.fetch = originalFetch;
    }
});
test("ix_status falls back to CLI when runtime HTTP is unavailable", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => {
        throw new Error("connect ECONNREFUSED");
    };
    try {
        const server = new FakeServer();
        registerAllTools(server);
        const callback = server.callbacks.get("ix_status");
        assert.ok(callback, "ix_status should be registered");
        const response = parseToolResponse(await callback({}, {}));
        assert.equal(response["ok"], true);
        const data = response["data"];
        assert.equal(data["fallback"], "cli");
        assert.equal(data["runtime_available"], true);
        assert.equal(typeof data["canonical_revision"], "number");
    }
    finally {
        globalThis.fetch = originalFetch;
    }
});
test("ix_decide falls back to local CLI health when runtime HTTP is unavailable", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => {
        throw new Error("connect ECONNREFUSED");
    };
    try {
        const server = new FakeServer();
        registerAllTools(server);
        const callback = server.callbacks.get("ix_decide");
        assert.ok(callback, "ix_decide should be registered");
        const response = parseToolResponse(await callback({
            paths: ["package.json"],
            operation: "edit",
        }, {}));
        assert.equal(response["ok"], true);
        const data = response["data"];
        assert.equal(data["fallback"], "cli");
        assert.equal(data["runtime_available"], true);
        assert.match(String(data["verdict"]), /^(allow|warn)$/);
    }
    finally {
        globalThis.fetch = originalFetch;
    }
});
test("ix_ingest falls back to ix map when runtime HTTP is unavailable", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => {
        throw new Error("connect ECONNREFUSED");
    };
    try {
        const server = new FakeServer();
        registerAllTools(server);
        const callback = server.callbacks.get("ix_ingest");
        assert.ok(callback, "ix_ingest should be registered");
        const response = parseToolResponse(await callback({
            paths: ["package.json"],
        }, {}));
        assert.equal(response["ok"], true);
        const data = response["data"];
        assert.equal(data["fallback"], "cli");
        assert.equal(data["runtime_available"], true);
        assert.equal(data["ingested"], true);
        assert.equal(typeof response["canonical_revision"], "number");
    }
    finally {
        globalThis.fetch = originalFetch;
    }
});
//# sourceMappingURL=runtime-unavailable.test.js.map