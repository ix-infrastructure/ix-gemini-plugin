import { pathToFileURL } from "node:url";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { register as registerIxQuery } from "./tools/ix_query.js";
import { register as registerIxDecide } from "./tools/ix_decide.js";
import { register as registerIxIngest } from "./tools/ix_ingest.js";
import { register as registerIxStatus } from "./tools/ix_status.js";
import { register as registerIxBriefing } from "./tools/ix_briefing.js";
import { register as registerIxLocate } from "./tools/ix_locate.js";
import { register as registerIxText } from "./tools/ix_text.js";
import { register as registerIxExplain } from "./tools/ix_explain.js";
import { register as registerIxRank } from "./tools/ix_rank.js";
import { register as registerIxStats } from "./tools/ix_stats.js";
import { register as registerIxSubsystems } from "./tools/ix_subsystems.js";
import { register as registerIxInventory } from "./tools/ix_inventory.js";
import { register as registerIxCallers } from "./tools/ix_callers.js";
import { register as registerIxCallees } from "./tools/ix_callees.js";
import { register as registerIxDepends } from "./tools/ix_depends.js";
import { register as registerIxTrace } from "./tools/ix_trace.js";
import { register as registerIxImpact } from "./tools/ix_impact.js";
import { register as registerIxHealth } from "./tools/ix_health.js";
import { register as registerIxMap } from "./tools/ix_map.js";
import { register as registerIxSmells } from "./tools/ix_smells.js";
export function registerAllTools(server) {
    // Core runtime tools
    registerIxQuery(server);
    registerIxDecide(server);
    registerIxIngest(server);
    registerIxStatus(server);
    // Query and search
    registerIxBriefing(server);
    registerIxLocate(server);
    registerIxText(server);
    registerIxExplain(server);
    // Graph analysis
    registerIxRank(server);
    registerIxStats(server);
    registerIxSubsystems(server);
    registerIxInventory(server);
    registerIxCallers(server); // registers ix_callers + ix_imported_by
    registerIxCallees(server); // registers ix_callees + ix_imports
    registerIxDepends(server);
    registerIxTrace(server);
    registerIxImpact(server);
    // Health, ingestion, and insights
    registerIxHealth(server);
    registerIxMap(server); // registers ix_map + ix_overview
    registerIxSmells(server);
}
export function createServer() {
    const server = new McpServer({
        name: "ix-memory",
        version: "0.1.0",
    });
    registerAllTools(server);
    return server;
}
async function main() {
    const server = createServer();
    const transport = new StdioServerTransport();
    process.on("SIGINT", () => process.exit(0));
    process.on("SIGTERM", () => process.exit(0));
    await server.connect(transport);
}
const entryUrl = process.argv[1] ? pathToFileURL(process.argv[1]).href : null;
if (entryUrl === import.meta.url) {
    await main();
}
//# sourceMappingURL=server.js.map