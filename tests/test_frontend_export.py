from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.export_frontend_data import build_dss_payload, write_snapshot

ROOT = Path(__file__).resolve().parents[1]


class FrontendExportTests(unittest.TestCase):
    def setUp(self):
        self.history = [{"company": "A", "month_id": 202301, "units": 10, "revenue": 250000}]
        self.forecasts = [{"level": "company", "member": "A", "month_id": 202401,
                           "model_name": "sarima", "is_backtest": False, "forecast_units": 12,
                           "actual_units": None}]

    def test_payload_filters_to_company_and_does_not_export_connection_fields(self):
        self.history[0]["password"] = "not-for-browser"
        rows = self.forecasts + [{"level": "total", "forecast_units": 99999}]
        result = build_dss_payload(self.history, rows, [])
        self.assertEqual(len(result["forecasts"]), 1)
        self.assertEqual(result["default_month"], 202401)
        self.assertNotIn("not-for-browser", json.dumps(result))

    def test_duplicate_forecasts_fail_export(self):
        with self.assertRaisesRegex(ValueError, "trùng"):
            build_dss_payload(self.history, self.forecasts * 2, [])

    def test_backtest_requires_actuals(self):
        self.forecasts[0]["is_backtest"] = True
        with self.assertRaisesRegex(ValueError, "actual_units"):
            build_dss_payload(self.history, self.forecasts, [])

    def test_empty_or_nonfinite_input_is_rejected(self):
        with self.assertRaises(ValueError):
            build_dss_payload([], self.forecasts, [])
        self.forecasts[0]["forecast_units"] = float("nan")
        with self.assertRaises(ValueError):
            build_dss_payload(self.history, self.forecasts, [])

    def test_failed_serialization_keeps_the_previous_snapshot(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            path = Path(temporary) / "data.json"
            write_snapshot(path, {"version": 1})
            with self.assertRaises(ValueError):
                write_snapshot(path, {"value": float("nan")})
            self.assertEqual(json.loads(path.read_text()), {"version": 1})


if __name__ == "__main__":
    unittest.main()
