import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import ingest_dataset, get_connection
from analytics import get_summary, get_top_products, get_top_customers, get_broken_flows


class AnalyticsSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure database is built
        ingest_dataset()

    def test_summary_shape(self):
        summary = get_summary()
        self.assertIn("totals", summary)
        self.assertIn("top_products", summary)
        self.assertIn("top_customers", summary)
        self.assertIn("broken_flows", summary)
        self.assertIsInstance(summary["totals"], dict)

    def test_top_products(self):
        conn = get_connection()
        data = get_top_products(conn, 3)
        conn.close()
        self.assertIn("rows", data)
        self.assertIsInstance(data["rows"], list)

    def test_top_customers(self):
        conn = get_connection()
        data = get_top_customers(conn, 3)
        conn.close()
        self.assertIn("rows", data)
        self.assertIsInstance(data["rows"], list)

    def test_broken_flows(self):
        conn = get_connection()
        data = get_broken_flows(conn)
        conn.close()
        self.assertIn("delivered_not_billed", data)
        self.assertIn("billed_no_delivery", data)
        self.assertIn("billed_no_journal", data)
        self.assertIn("unpaid", data)


if __name__ == "__main__":
    unittest.main()
