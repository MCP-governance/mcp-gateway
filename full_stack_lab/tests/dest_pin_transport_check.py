"""Real HTTPX/HTTPX2 pools over an in-memory byte stream; no network or DB.

Run in the Gateway dependency environment. TLS here records the SSL context and
SNI passed by httpcore; certificate acceptance still requires a real TLS test.
"""
import asyncio
from pathlib import Path
import ssl
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

try:
    import httpx
except ModuleNotFoundError as exc:
    if exc.name != "httpx":
        raise
    httpx = None
try:
    import httpx2
except ModuleNotFoundError as exc:
    if exc.name != "httpx2":
        raise
    httpx2 = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app.destination import DestinationBlocked, pin_transport


class MemoryStream:
    def __init__(self):
        self.response = b"HTTP/1.1 302 Found\r\nLocation: http://127.0.0.1/\r\nContent-Length: 0\r\n\r\n"
        self.written = bytearray()
        self.tls = None

    async def read(self, max_bytes, timeout=None):
        data, self.response = self.response[:max_bytes], self.response[max_bytes:]
        return data

    async def write(self, buffer, timeout=None):
        self.written.extend(buffer)

    async def aclose(self):
        pass

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self.tls = (ssl_context, server_hostname)
        return self

    def get_extra_info(self, info):
        return None


@unittest.skipUnless(httpx is not None and httpx2 is not None, "requires Gateway httpx and httpx2 dependencies")
class TransportPin(unittest.IsolatedAsyncioTestCase):
    async def test_original_sni_verified_context_host_and_redirect_disabled(self):
        for library in [httpx, httpx2]:
            with self.subTest(library=library.__name__):
                transport = pin_transport(library.AsyncHTTPTransport(trust_env=False),
                                          target=("vendor.example", 443))
                stream = MemoryStream()
                connector = AsyncMock(return_value=stream)
                transport._pool._network_backend.backend = SimpleNamespace(connect_tcp=connector)
                resolver = AsyncMock(return_value=[(2, 1, 6, "", ("8.8.8.8", 443))])
                with patch.object(asyncio.get_running_loop(), "getaddrinfo", resolver):
                    async with library.AsyncClient(transport=transport, trust_env=False, follow_redirects=False) as client:
                        response = await client.get("https://vendor.example/mcp")
                self.assertEqual(response.status_code, 302)
                resolver.assert_awaited_once()
                self.assertEqual(connector.call_args.kwargs["host"], "8.8.8.8")
                self.assertEqual(stream.tls[1], "vendor.example")
                self.assertTrue(stream.tls[0].check_hostname)
                self.assertEqual(stream.tls[0].verify_mode, ssl.CERT_REQUIRED)
                self.assertIn(b"host: vendor.example\r\n", bytes(stream.written).lower())
                self.assertEqual(str(response.request.url), "https://vendor.example/mcp")

    async def test_internal_dns_answer_never_reaches_real_pool_connector(self):
        for library in [httpx, httpx2]:
            transport = pin_transport(library.AsyncHTTPTransport(trust_env=False))
            connector = AsyncMock()
            transport._pool._network_backend.backend = SimpleNamespace(connect_tcp=connector)
            resolver = AsyncMock(return_value=[(2, 1, 6, "", ("127.0.0.1", 443))])
            with patch.object(asyncio.get_running_loop(), "getaddrinfo", resolver):
                async with library.AsyncClient(transport=transport, trust_env=False) as client:
                    with self.assertRaises(DestinationBlocked):
                        await client.get("https://vendor.example/mcp")
            connector.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
