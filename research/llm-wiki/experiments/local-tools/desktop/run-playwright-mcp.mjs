import fs from "node:fs/promises";
import path from "node:path";
import { createServer } from "node:http";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../../../../..");
const app = path.join(repo, ".task-local-20261014/desktop/app/playwright");
const browserPath = path.join(repo, ".task-local-20261014/desktop/app/browsers");
const cli = path.join(app, "node_modules/@playwright/mcp/cli.js");
const sdk = path.join(app, "node_modules/@modelcontextprotocol/sdk/dist/esm/client");
const [{ Client }, { StdioClientTransport }] = await Promise.all([
  import(pathToFileURL(path.join(sdk, "index.js"))),
  import(pathToFileURL(path.join(sdk, "stdio.js"))),
]);
const userData = path.join(repo, ".task-local-20261014/desktop/app/playwright-profile");
const output = path.join(repo, ".task-local-20261014/desktop/log/playwright-protocol.json");
const fixture = path.join(here, "fixtures/local-read.html");
const html = await fs.readFile(fixture, "utf8");
const localServer = createServer((request, response) => {
  if (request.url === "/favicon.ico") {
    response.writeHead(204).end();
    return;
  }
  if (request.url !== "/") {
    response.writeHead(404).end();
    return;
  }
  response.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
  response.end(html);
});
await new Promise(resolve => localServer.listen(0, "127.0.0.1", resolve));
const localUrl = `http://127.0.0.1:${localServer.address().port}/`;
const transport = new StdioClientTransport({
  command: process.execPath,
  args: [cli, "--headless", "--browser", "chromium", "--user-data-dir", userData, "--allowed-origins", new URL(localUrl).origin],
  env: {
    ...process.env,
    PLAYWRIGHT_BROWSERS_PATH: browserPath,
    PLAYWRIGHT_MCP_OUTPUT_DIR: path.join(repo, ".task-local-20261014/desktop/log"),
  },
  stderr: "pipe",
});
const client = new Client({ name: "desktop-mcp-validation", version: "1.0.0" });
let stderr = "";
let initializeResult = null;
const originalRequest = client.request.bind(client);
client.request = async (request, schema, options) => {
  const result = await originalRequest(request, schema, options);
  if (request.method === "initialize") initializeResult = result;
  return result;
};
transport.stderr?.on("data", chunk => { stderr += chunk.toString(); });
try {
  await client.connect(transport);
  const listed = await client.listTools();
  const names = new Set(listed.tools.map(tool => tool.name));
  const nav = names.has("browser_navigate")
    ? await client.callTool({ name: "browser_navigate", arguments: { url: localUrl } })
    : { error: "browser_navigate not found" };
  const snapshot = names.has("browser_snapshot")
    ? await client.callTool({ name: "browser_snapshot", arguments: {} })
    : { error: "browser_snapshot not found" };
  await fs.writeFile(output, JSON.stringify({
    captured_at_utc: new Date().toISOString(),
    server: "@playwright/mcp@0.0.83",
    local_fixture_url: localUrl,
    initialize_result: initializeResult,
    initialize_server_info: client.getServerVersion(),
    protocol_version: initializeResult?.protocolVersion ?? null,
    tools: listed.tools,
    calls: { browser_navigate: nav, browser_snapshot: snapshot },
    stderr,
  }, null, 2));
  console.log(JSON.stringify({ toolCount: listed.tools.length, names: listed.tools.map(tool => tool.name), nav, snapshot, output }, null, 2));
} finally {
  await client.close();
  await new Promise(resolve => localServer.close(resolve));
}
