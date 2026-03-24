import unittest
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from main import app


class ApiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("status", body)
        self.assertIn("nodes", body)
        self.assertIn("edges", body)

    def test_analytics_summary(self):
        resp = self.client.get("/analytics/summary")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("totals", body)
        self.assertIn("top_products", body)
        self.assertIn("top_customers", body)
        self.assertIn("top_plants", body)
        self.assertIn("top_regions", body)
        self.assertIn("top_countries", body)
        self.assertIn("broken_flows", body)


if __name__ == "__main__":
    unittest.main()
