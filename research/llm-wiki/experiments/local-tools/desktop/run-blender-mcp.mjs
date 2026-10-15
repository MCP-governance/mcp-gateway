import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../../../../..");
const task = path.join(repo, ".task-local-20261014/desktop");
const sdk = path.join(task, "app/playwright/node_modules/@modelcontextprotocol/sdk/dist/esm/client");
const [{ Client }, { StdioClientTransport }] = await Promise.all([
  import(pathToFileURL(path.join(sdk, "index.js"))),
  import(pathToFileURL(path.join(sdk, "stdio.js"))),
]);
const out = path.join(task, "log/blender-protocol.json");
const venv = path.join(task, "venv/blender/Scripts");
const exe = path.join(venv, "mcp-for-blender.exe");
const environment = Object.fromEntries(Object.entries(process.env).filter(([name]) =>
  !/(TOKEN|SECRET|PASSWORD|CREDENTIAL|API_?KEY|PRIVATE_KEY|SSH_AUTH|OPENAI|ANTHROPIC|AWS_|AZURE_|GOOGLE_)/i.test(name)));
const transport = new StdioClientTransport({
  command: exe,
  args: [],
  env: {
    ...environment,
    BLENDER_HOST: "127.0.0.1",
    BLENDER_PORT: "9876",
    BLENDER_MCP_DISABLE_TELEMETRY: "1",
    DISABLE_TELEMETRY: "1",
    BLENDER_MCP_SAFE_MODE: "1",
    APPDATA: path.join(task, "app/blender-profile/roaming"),
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
  for (const required of ["get_addon_status", "get_scene_info", "execute_blender_code"])
    if (!names.has(required)) throw new Error(`Required tool missing: ${required}`);
  const status = names.has("get_addon_status")
    ? await client.callTool({ name: "get_addon_status", arguments: {} })
    : { error: "get_addon_status not listed" };
  const before = names.has("get_scene_info")
    ? await client.callTool({ name: "get_scene_info", arguments: {} })
    : { error: "get_scene_info not listed" };
  const write = names.has("execute_blender_code")
    ? await client.callTool({ name: "execute_blender_code", arguments: {
        code: [
          "import bpy",
          "bpy.ops.mesh.primitive_uv_sphere_add(radius=0.25, location=(2, 0, 0))",
          "bpy.context.object.name = 'MCP Synthetic Sphere'",
          "print(bpy.context.object.name)",
        ].join("\n"),
      } })
    : { error: "execute_blender_code not listed" };
  const after = names.has("get_scene_info")
    ? await client.callTool({ name: "get_scene_info", arguments: { query: "MCP Synthetic Sphere" } })
    : { error: "get_scene_info not listed" };
  if ([status, before, write, after].some(result => result.isError) || !JSON.stringify(after).includes("MCP Synthetic Sphere"))
    throw new Error("Synthetic Blender read/write verification failed");
  const record = {
    captured_at_utc: new Date().toISOString(),
    server: "mcp-for-blender==2.1.9",
    blender: "5.2.2 LTS",
    telemetry_environment: { BLENDER_MCP_DISABLE_TELEMETRY: "1", DISABLE_TELEMETRY: "1" },
    safe_mode: true,
    server_version: client.getServerVersion(),
    initialize_result: initializeResult,
    protocol_version: initializeResult?.protocolVersion ?? null,
    tools: listed.tools,
    calls: { get_addon_status: status, get_scene_info_before: before, execute_blender_code_synthetic_write: write, get_scene_info_after: after },
    stderr,
  };
  await fs.writeFile(out, JSON.stringify(record, null, 2));
  console.log(JSON.stringify({ toolCount: listed.tools.length, names: listed.tools.map(tool => tool.name), status, before, write, after, serverVersion: record.server_version, output: out }, null, 2));
} finally {
  await client.close();
}
