import math

import pytest

from mcp_gateway.config import Settings, Upstream, load_config


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/mcp", "http:///mcp", "https://user:secret@example.com/mcp", "http://example.com/mcp#fragment", "http://example.com:secret/mcp"])
def test_invalid_upstream(url):
    with pytest.raises((ValueError, TypeError)) as failure:
        Upstream(url)
    assert "secret" not in str(failure.value)


@pytest.mark.parametrize("headers", [
    {"Host": "other"}, {"Content-Length": "0"}, {"Connection": "close"},
    {"Bad Header": "value"}, {"X-Token": "secret\r\nInjected: yes"}, {"X-Token": 42}, {"Authorization": "one", "authorization": "two"},
])
def test_invalid_header(headers):
    with pytest.raises((ValueError, TypeError)):
        Upstream("https://example.com/mcp", headers)


@pytest.mark.parametrize("name,value", [
    ("connect_timeout_seconds", 0), ("connect_timeout_seconds", True),
    ("read_timeout_seconds", -1), ("read_timeout_seconds", math.nan),
    ("write_timeout_seconds", math.inf), ("write_timeout_seconds", "10"),
    ("shutdown_timeout_seconds", -1), ("shutdown_timeout_seconds", math.inf),
    ("max_connections_per_server", 0), ("max_connections_per_server", True),
    ("max_connections_per_server", 1.5), ("max_connections_per_server", "10"),
])
def test_invalid_proxy_option(name, value):
    with pytest.raises(ValueError):
        Settings({"demo": Upstream("http://localhost/mcp")}, **{name: value})


def test_proxy_options_loaded(tmp_path):
    config = tmp_path / "proxy.toml"
    config.write_text('[proxy]\nshutdown_timeout_seconds=0\nmax_connections_per_server=2\n'
                      '[servers.demo]\nurl="http://localhost/mcp"\n')
    settings = load_config(config)
    assert settings.shutdown_timeout_seconds == 0
    assert settings.max_connections_per_server == 2


@pytest.mark.parametrize("servers", [{}, {"../other": Upstream("http://localhost/mcp")}, {"with space": Upstream("http://localhost/mcp")}])
def test_invalid_routes(servers):
    with pytest.raises(ValueError):
        Settings(servers)


def test_credentials_loaded_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MCP_AUTH", "Bearer upstream-secret")
    config = tmp_path / "proxy.toml"
    config.write_text('[servers.demo]\nurl="https://example.com/mcp"\n[servers.demo.headers]\nAuthorization={env="DEMO_MCP_AUTH"}\n')
    settings = load_config(config)
    assert settings.servers["demo"].headers == {"Authorization": "Bearer upstream-secret"}
    assert "upstream-secret" not in repr(settings)
    monkeypatch.delenv("DEMO_MCP_AUTH")
    with pytest.raises(ValueError, match="missing upstream credential"):
        load_config(config)


@pytest.mark.parametrize("document", [
    'servers=[]\n',
    'proxy=[]\n',
    '[servers]\ndemo=[]\n',
    '[servers.demo]\nurl="http://localhost/mcp"\nheaders=[]\n',
    '[unknown]\nvalue=1\n',
    '[servers.demo]\nurl="http://localhost/mcp"\ntypo=true\n',
    '[proxy]\ntypo=1\n[servers.demo]\nurl="http://localhost/mcp"\n',
])
def test_unknown_settings_rejected(tmp_path, document):
    config = tmp_path / "proxy.toml"
    config.write_text(document)
    with pytest.raises((ValueError, TypeError)):
        load_config(config)
