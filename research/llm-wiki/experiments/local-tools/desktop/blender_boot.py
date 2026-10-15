import bpy
import os
import traceback
from pathlib import Path

LOG = Path(os.environ["BLENDERMCP_TEST_LOG"])
def log(message):
    with LOG.open("a", encoding="utf-8") as stream:
        stream.write(str(message) + "\n")

def start_server():
    try:
        import blender_mcp
        bpy.context.scene.blendermcp_auto_start_server = False
        bpy.context.scene.blendermcp_port = 9876
        prefs = bpy.context.preferences.addons.get("blender_mcp")
        if prefs:
            prefs.preferences.telemetry_consent = False
        server = blender_mcp.BlenderMCPServer(host="localhost", port=9876)
        bpy.types.blendermcp_server = server
        server.start()
        log(f"bridge_started host={server.host} port={server.port} running={server.running} telemetry_consent={getattr(prefs.preferences, 'telemetry_consent', None) if prefs else None}")
    except Exception:
        log(traceback.format_exc())
    return None

try:
    bpy.ops.preferences.addon_enable(module="blender_mcp")
    prefs = bpy.context.preferences.addons.get("blender_mcp")
    if prefs:
        prefs.preferences.telemetry_consent = False
    bpy.context.scene.blendermcp_auto_start_server = False
    bpy.context.scene.blendermcp_port = 9876
    bpy.app.timers.register(start_server, first_interval=3.0)
    log(f"addon_enabled blender={bpy.app.version_string} telemetry_consent={getattr(prefs.preferences, 'telemetry_consent', None) if prefs else None}")
except Exception:
    log(traceback.format_exc())
