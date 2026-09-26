import json
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]

def test_services_match_selected_drawing():
    topology=json.loads((ROOT/"docs/topology.json").read_text())
    compose=yaml.safe_load((ROOT/"compose.yaml").read_text())
    expected={name for names in topology["boundaries"].values() for name in names}
    assert set(compose["services"])==expected
    assert topology["telemetry_sources"]==["agent-service","mcp-gateway","mcp-server"]
    for name in topology["telemetry_sources"]:
        assert compose["services"][name]["environment"]["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"]=="http://otel-collector:4318/v1/traces"
    assert "DATABASE_URL" not in compose["services"]["mcp-gateway"]["environment"]
    assert "research" in [p.name for p in ROOT.iterdir()]

def test_runtime_processor_is_collector_target():
    config=yaml.safe_load((ROOT/"deploy/collector.yaml").read_text())
    assert config["exporters"]["otlphttp/evidence"]["encoding"]=="json"
    assert config["exporters"]["otlphttp/evidence"]["traces_endpoint"]=="http://evidence-processor:8000/v1/traces"
