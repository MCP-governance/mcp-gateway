"""Configured internal/external API fixtures used by the example MCP tools."""
from fastapi import FastAPI
app = FastAPI()
@app.get("/data")
def data():
    return {"message": "public example data"}
@app.get("/health")
def health():
    return {"ok": True}
