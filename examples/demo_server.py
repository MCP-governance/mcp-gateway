"""Small upstream MCP server for local demos and SDK compatibility tests."""
import argparse

import uvicorn
from mcp import types
from mcp.server.lowlevel.server import Server
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import Response
from starlette.routing import Route


async def list_tools(ctx, params):
    return types.ListToolsResult(tools=[types.Tool(
        name="echo", description="Return the supplied text unchanged.",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    )])


async def call_tool(ctx, params):
    text = params.arguments["text"]
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        structured_content={"echo": text},
    )


async def list_resources(ctx, params):
    return types.ListResourcesResult(resources=[types.Resource(
        uri="demo://message", name="Demo message", mime_type="text/plain",
    )])


async def read_resource(ctx, params):
    return types.ReadResourceResult(contents=[types.TextResourceContents(
        uri=params.uri, mime_type="text/plain", text="hello from upstream",
    )])


async def list_prompts(ctx, params):
    return types.ListPromptsResult(prompts=[types.Prompt(name="greeting", description="A short greeting.")])


async def get_prompt(ctx, params):
    return types.GetPromptResult(messages=[types.PromptMessage(
        role="user", content=types.TextContent(type="text", text="Say hello."),
    )])


def create_demo_app(*, json_response=False):
    server = Server(
        "proxy-demo-upstream", version="1.0.0",
        on_list_tools=list_tools, on_call_tool=call_tool,
        on_list_resources=list_resources, on_read_resource=read_resource,
        on_list_prompts=list_prompts, on_get_prompt=get_prompt,
    )
    async def health(request):
        return Response("ok")

    return server.streamable_http_app(
        json_response=json_response, custom_starlette_routes=[Route("/health", health)],
        transport_security=TransportSecuritySettings(
            allowed_hosts=["127.0.0.1:*", "localhost:*", "demo:*"],
            allowed_origins=["http://127.0.0.1:*", "http://localhost:*"],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    arguments = parser.parse_args()
    uvicorn.run(create_demo_app(), host=arguments.host, port=arguments.port, access_log=False)
