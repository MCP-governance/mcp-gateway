"""정적 자원은 재검증(304)으로 재방문 전송을 줄이고, 페이지·API 응답은 no-store를 유지한다."""
from pathlib import Path
import sys
import unittest

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "gateway"))
from app import agent_service


class StaticCacheTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(agent_service.app)

    def test_static_files_revalidate_and_answer_304(self):
        for path in ("/static/fonts/NotoSansKR-variable.woff2", "/static/vendor/echarts.min.js", "/static/login.js"):
            first = self.client.get(path)
            self.assertEqual(first.status_code, 200, path)
            self.assertEqual(first.headers["Cache-Control"], "no-cache", path)
            again = self.client.get(path, headers={"If-None-Match": first.headers["ETag"]})
            self.assertEqual((again.status_code, again.content), (304, b""), path)

    def test_pages_and_api_stay_no_store(self):
        for path in ("/login", "/workspace", "/auth/me", "/api/accounts"):
            self.assertEqual(self.client.get(path).headers["Cache-Control"], "no-store", path)


if __name__ == "__main__":
    unittest.main()
