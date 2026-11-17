"""Kiểm tra tích hợp DSS và sinh lại PBIP, không cần PostgreSQL/Power BI.

Chạy: python tests/test_dss_static.py
Hoặc: python -m pytest -q src/test_forecast.py tests
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "powerbi"))
import build_pbip
from dss_measures import DSS_MEASURES, DSS_SUPPORT_MEASURES
from dss_testcases import DSS_TESTCASE_MEASURES, REPORT_CASE_STATUS_MEASURES, testcase_dax_reference as render_testcase_dax_reference

DEFINITION = ROOT / "powerbi/CarSalesDSS.SemanticModel/definition"
REPORT = ROOT / "powerbi/CarSalesDSS.Report"
PARAMETERS = {
    "Param_Growth", "Param_Share", "Param_Stability", "Param_Accuracy",
    "Demand Change", "Safety Factor",
}
QUALIFIED = re.compile(r"(?:'((?:[^']|'')+)'|([A-Za-z_]\w*))\s*\[([^\]]+)\]")


def schema(definition: Path) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    columns, measures = {}, {}
    for path in (definition / "tables").glob("*.tmdl"):
        text = path.read_text(encoding="utf-8")
        columns[path.stem] = set()
        measures[path.stem] = set()
        for kind, names in (("column", columns), ("measure", measures)):
            pattern = rf"^\t{kind} (?:'((?:[^']|'')+)'|([A-Za-z_]\w*))(?=\s|$)"
            found = [(a or b).replace("''", "'") for a, b in re.findall(pattern, text, re.M)]
            if len(found) != len(set(found)):
                raise AssertionError(f"Tên {kind} bị trùng trong {path}")
            names[path.stem].update(found)
    return columns, measures


def digests(path: Path) -> dict[str, str]:
    return {
        str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in path.rglob("*") if p.is_file()
    }


class DSSIntegrationTests(unittest.TestCase):
    def test_dss_dependencies_resolve(self):
        columns, measures = schema(DEFINITION)
        all_measures = set().union(*measures.values())
        definitions = DSS_SUPPORT_MEASURES + DSS_MEASURES + DSS_TESTCASE_MEASURES
        self.assertEqual(len(DSS_MEASURES), 28)
        self.assertEqual(len({m[0] for m in definitions}), len(definitions))
        for name, dax, _fmt, _folder, _desc in definitions:
            with self.subTest(measure=name):
                self.assertIn(name, measures["_Measures"])
                self.assertNotIn("Calendar[", dax)
                for match in QUALIFIED.finditer(dax):
                    table = (match[1] or match[2]).replace("''", "'")
                    self.assertIn(table, columns, f"{name}: thiếu bảng {table}")
                    self.assertIn(match[3], columns[table], f"{name}: thiếu cột {table}[{match[3]}]")
                bare = QUALIFIED.sub("", dax)
                for ref in re.findall(r"\[([^\]]+)\]", bare):
                    self.assertIn(ref, all_measures | {"__dss_units"}, f"{name}: thiếu measure [{ref}]")
                self.assertFalse(dax.lstrip().upper().startswith("RETURN "), f"{name}: RETURN thiếu VAR")
                self.assertEqual(dax.count("("), dax.count(")"))
                self.assertEqual(dax.count("{"), dax.count("}"))

    def test_parameters_are_disconnected(self):
        columns, measures = schema(DEFINITION)
        relationships = (DEFINITION / "relationships.tmdl").read_text(encoding="utf-8")
        for table in PARAMETERS:
            with self.subTest(table=table):
                self.assertEqual(columns[table], {"Value"})
                self.assertNotIn(table, relationships)
                text = (DEFINITION / "tables" / f"{table}.tmdl").read_text(encoding="utf-8")
                if table.startswith("Param_"):
                    self.assertIn("GENERATESERIES ( 0, 100, 5 )", text)
                    self.assertIn("dataType: int64", text)
                else:
                    self.assertIn(f"{table} Value", measures[table])

    def test_report_fields_and_defaults(self):
        columns, measures = schema(DEFINITION)

        def walk(value, aliases=None):
            if isinstance(value, dict):
                local = dict(aliases or {})
                local.update({item["Name"]: item["Entity"] for item in value.get("From", [])})
                for kind, allowed in (("Column", columns), ("Measure", measures)):
                    if kind in value:
                        field = value[kind]
                        source = field.get("Expression", {}).get("SourceRef", {})
                        table = source.get("Entity") or local.get(source.get("Source"))
                        if source:
                            self.assertIsNotNone(table, f"SourceRef không xác định: {source}")
                            self.assertIn(table, allowed)
                            self.assertIn(field["Property"], allowed[table])
                for item in value.values():
                    walk(item, local)
            elif isinstance(value, list):
                for item in value:
                    walk(item, aliases)

        pages = REPORT / "definition/pages"
        metadata = json.loads((pages / "pages.json").read_text(encoding="utf-8"))
        self.assertEqual(len(metadata["pageOrder"]), len(set(metadata["pageOrder"])))
        for page in ("ReportSection", "DSS_Priority", "DSS_WhatIf", "DSS_Test_S5", "DSS_Test_S6"):
            self.assertIn(page, metadata["pageOrder"])
        for page in ("DSS_Priority", "DSS_WhatIf", "DSS_Test_S5", "DSS_Test_S6"):
            files = list((pages / page / "visuals").glob("*/visual.json"))
            self.assertGreaterEqual(len(files), 5)
            for path in files:
                with self.subTest(visual=str(path.relative_to(pages))):
                    value = json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(value["name"], path.parent.name)
                    self.assertIn("visualType", value["visual"])
                    self.assertLessEqual(value["position"]["x"] + value["position"]["width"], 1280)
                    self.assertLessEqual(value["position"]["y"] + value["position"]["height"], 720)
                    walk(value)
                    defaults = {
                        "DSS_month": "202401L", "DSS_model": "'sarima'",
                        "DSS_growth": "25L", "DSS_share": "25L",
                        "DSS_stability": "25L", "DSS_accuracy": "25L", "DSS_demand": "0D",
                    }
                    if value["visual"]["visualType"] == "slicer" and value["name"] in defaults:
                        general = value["visual"]["objects"]["general"]
                        literals = [
                            item["properties"]["filter"]["filter"]["Where"][0]
                            ["Condition"]["In"]["Values"][0][0]["Literal"]["Value"]
                            for item in general
                        ]
                        self.assertEqual(literals, [defaults[value["name"]]])

    def test_main_model_is_retained(self):
        columns, measures = schema(DEFINITION)
        expected = set(build_pbip.MART_TABLES) | set(build_pbip.DW_TABLES) | PARAMETERS | {"_Measures"}
        self.assertEqual(set(columns), expected)
        self.assertIn("cars_sold", columns["dim_car"])
        self.assertNotIn("dealer_no", columns["dim_dealer"])
        self.assertIn("has_forecast_data", columns["dim_month"])
        main_names = {m[0] for m in build_pbip.build_measures()}
        self.assertTrue(main_names <= measures["_Measures"])
        self.assertEqual(len(main_names), 85)

    def test_s5_s6_testcase_query_matches_model_and_guide(self):
        """Dùng đúng chín case tại mục 5.6.2 của báo cáo được cung cấp."""
        query = (ROOT / "powerbi/tests/DSS_TestCases.dax").read_text(encoding="utf-8")
        catalogue = json.loads((ROOT / "tests/fixtures/dss_report_testcases.json").read_text(encoding="utf-8"))
        expected = set(REPORT_CASE_STATUS_MEASURES)
        self.assertEqual(len(expected), 9)
        self.assertEqual(catalogue["source_section"], "5.6.2")
        self.assertEqual({c["id"]: c["status_measure"] for c in catalogue["cases"]}, REPORT_CASE_STATUS_MEASURES)
        self.assertEqual(len(catalogue["cases"]), 9)
        cases = re.findall(r'"TestCase"\s*,\s*"(TC-S[56]-\d{2})"', query)
        self.assertEqual(len(cases), len(expected))
        self.assertEqual(set(cases), expected)

        columns, measures = schema(DEFINITION)
        all_measures = set().union(*measures.values())
        code = re.sub(r"//[^\n]*", "", query)
        reference_code = re.sub(r'"(?:[^"\n]|"")*"', '""', code)
        # Unquoted table names in this query touch '[' directly; do not parse
        # 'RETURN [measure]' as a table named RETURN.
        qualified = re.compile(r"(?:'((?:[^']|'')+)'\s*|([A-Za-z_]\w*))\[([^\]]+)\]")
        for match in qualified.finditer(reference_code):
            table = (match[1] or match[2]).replace("''", "'")
            self.assertIn(table, columns, f"Query thiếu bảng {table}")
            self.assertIn(match[3], columns[table], f"Query thiếu cột {table}[{match[3]}]")
        bare = qualified.sub("", reference_code)
        for ref in re.findall(r"\[([^\]]+)\]", bare):
            if not ref.startswith("__") and ref != "TestCase":
                self.assertIn(ref, all_measures, f"Query thiếu measure [{ref}]")
        literals_removed = re.sub(r'"(?:[^"\n]|"")*"', '""', code)
        self.assertEqual(literals_removed.count("("), literals_removed.count(")"))
        self.assertEqual(literals_removed.count("{"), literals_removed.count("}"))
        self.assertEqual(len(re.findall(r"(?m)^EVALUATE\s*$", code)), 2)
        self.assertIn('"SKIP"', code)

    def test_report_testcase_status_columns_are_visible(self):
        pages = REPORT / "definition/pages"
        for page, prefix in (("DSS_Test_S5", "TC S5"), ("DSS_Test_S6", "TC S6")):
            bound = set()
            for path in (pages / page / "visuals").glob("*/visual.json"):
                value = json.loads(path.read_text(encoding="utf-8"))
                projections = value["visual"].get("query", {}).get("queryState", {}).get("Values", {}).get("projections", [])
                bound.update(p["field"]["Measure"]["Property"] for p in projections if "Measure" in p.get("field", {}))
            self.assertTrue({m for m in REPORT_CASE_STATUS_MEASURES.values() if m.startswith(prefix)} <= bound)
        for name in ("TC_S6_values", "TC_S6_status"):
            path = pages / "DSS_Test_S6/visuals" / name / "visual.json"
            filters = json.loads(path.read_text(encoding="utf-8"))["filterConfig"]["filters"]
            self.assertEqual(filters[0]["filter"]["Where"][0]["Condition"]["Comparison"]["Right"]["Literal"]["Value"], "'company'")

    def test_regeneration_retains_dss_and_report(self):
        before = digests(REPORT)
        testcase_dir = ROOT / "powerbi/tests"
        testcase_before = digests(testcase_dir)
        with tempfile.TemporaryDirectory(prefix="dss-test-", dir=ROOT) as temporary:
            out = Path(temporary)
            shutil.copytree(REPORT, out / "CarSalesDSS.Report")
            shutil.copytree(testcase_dir, out / "tests")
            args = argparse.Namespace(
                out=str(out), name="CarSalesDSS", server="localhost:5432",
                database="car_sales_dw", schema="mart", dw_schema="public",
            )
            for _ in range(2):
                build_pbip.build(args)
                self.assertEqual(schema(out / "CarSalesDSS.SemanticModel/definition"), schema(DEFINITION))
                self.assertEqual(digests(out / "CarSalesDSS.Report"), before)
                self.assertEqual(digests(out / "tests"), testcase_before)
                self.assertEqual((out / "dss_measures.dax").read_text(encoding="utf-8"), build_pbip.dss_dax_reference())
                self.assertEqual((out / "testcase_measures.dax").read_text(encoding="utf-8"), render_testcase_dax_reference())


if __name__ == "__main__":
    unittest.main(verbosity=2)
