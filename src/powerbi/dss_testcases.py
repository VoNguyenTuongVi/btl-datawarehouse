"""Testcase theo mục 5.6.2, hình 12-22 của Nhóm6_L01_Report.pdf.

PASS/FAIL kiểm tra measure thật trong ngữ cảnh visual. N/A: chưa chọn đúng
kịch bản; NO DATA: không có một hãng hoặc thiếu dữ liệu cần đối chiếu.
"""
from textwrap import dedent

FOLDER = "9. Testcase theo báo cáo"
REPORT_CASE_STATUS_MEASURES = {
    "TC-S5-01": "TC S5 01 Status",
    "TC-S5-02": "TC S5 02 Status",
    "TC-S5-03": "TC S5 03 Status",
    "TC-S5-04": "TC S5 04 Status",
    "TC-S6-01": "TC S6 01 Status",
    "TC-S6-02": "TC S6 02 Status",
    "TC-S6-03": "TC S6 03 Status",
    "TC-S6-04": "TC S6 04 Status",
    "TC-S6-05": "TC S6 05 Status",
}


def _case(name, expression, description, fmt=None):
    return (name, dedent(expression).strip(), fmt, FOLDER, description)


def _weight_status(raw, expected):
    tables = ("Growth", "Share", "Stability", "Accuracy")
    setup = " || ".join(f"SELECTEDVALUE(Param_{t}[Value], 25) <> {v}"
                        for t, v in zip(tables, raw))
    passed = " && ".join(f"NOT ISBLANK([Priority Weight {t}]) && "
                         f"ABS([Priority Weight {t}] - {v}) <= 0.000001"
                         for t, v in zip(tables, expected))
    return f'IF({setup}, "N/A", IF({passed}, "PASS", "FAIL"))'


def _s6_status(demand, safety, condition):
    return f"""
        VAR d = [Demand Change Value]
        VAR k = [Safety Factor Value]
        VAR ob = [DSS Order Baseline]
        VAR os = [DSS Order Scenario]
        VAR rb = [DSS Revenue Baseline]
        VAR rs = [DSS Revenue Scenario]
        VAR deltaO = [DSS Order Delta]
        VAR deltaR = [DSS Revenue Delta]
        RETURN SWITCH(
            TRUE(),
            NOT HASONEVALUE(fact_demand_forecast[member]) || [DSS S6 Eligible] <> 1, "NO DATA",
            ABS(d - ({demand})) > 0.000001 || ABS(k - {safety}) > 0.000001, "N/A",
            ISBLANK(ob) || ISBLANK(os) || ISBLANK(rb) || ISBLANK(rs)
                || ISBLANK(deltaO) || ISBLANK(deltaR), "FAIL",
            ABS(deltaO - (os - ob)) > 0.000001 || ABS(deltaR - (rs - rb)) > 1, "FAIL",
            {condition}, "PASS",
            "FAIL"
        )
    """


DSS_TESTCASE_MEASURES = [
    _case("TC S5 01 PY Units", """
        VAR ym = [DSS Selected Forecast Month]
        RETURN IF(
            NOT HASONEVALUE(dim_car[company]) || ISBLANK(ym), BLANK(),
            CALCULATE(
                SUM(fact_car_sales[quantity]),
                REMOVEFILTERS(dim_month), REMOVEFILTERS(dim_year),
                REMOVEFILTERS(dim_calendar), REMOVEFILTERS(dim_date),
                dim_date[year] = INT((ym - 100) / 100),
                dim_date[month] = MOD(ym, 100)
            )
        )
    """, "TC-S5-01: sản lượng thực bán cùng hãng, cùng tháng năm trước", "#,0"),
    _case("TC S5 01 Expected Growth", """
        VAR f = [DSS Forecast Units Company]
        VAR py = [TC S5 01 PY Units]
        RETURN IF(ISBLANK(f) || ISBLANK(py) || py <= 0, BLANK(), DIVIDE(f - py, py))
    """, "TC-S5-01: Growth đối chiếu = (Forecast - PY) / PY", "0.0%"),
    _case("TC S5 01 Status", """
        VAR actual = [Priority Growth Raw]
        VAR expected = [TC S5 01 Expected Growth]
        RETURN IF(
            NOT HASONEVALUE(dim_car[company]) || ISBLANK(expected), "NO DATA",
            IF(NOT ISBLANK(actual) && ABS(actual - expected) <= 0.000001, "PASS", "FAIL")
        )
    """, "TC-S5-01: đối chiếu Growth; ví dụ Mercedes-B tại hình 12"),
    _case("TC S5 02 Status", """
        VAR g = [Priority Growth Score]
        VAR s = [Priority Share Score]
        VAR st = [Priority Stability Score]
        VAR a = [Priority Accuracy Score]
        RETURN IF(
            NOT HASONEVALUE(dim_car[company]) || [Priority Eligible] <> 1, "NO DATA",
            IF(NOT ISBLANK(g) && NOT ISBLANK(s) && NOT ISBLANK(st) && NOT ISBLANK(a)
                && g >= 0 && g <= 1 && s >= 0 && s <= 1
                && st >= 0 && st <= 1 && a >= 0 && a <= 1, "PASS", "FAIL")
        )
    """, "TC-S5-02: bốn điểm của hãng hợp lệ nằm trong [0,1], hình 13"),
    _case("TC S5 03 Status", _weight_status((50, 25, 25, 25), (0.4, 0.2, 0.2, 0.2)),
          "TC-S5-03: chọn 50/25/25/25 để kiểm tra 40/20/20/20%, hình 14"),
    _case("TC S5 04 Status", _weight_status((0, 0, 0, 0), (0.25, 0.25, 0.25, 0.25)),
          "TC-S5-04: bốn trọng số 0 tự trở về 25% mỗi tiêu chí, hình 15"),
    _case("TC S6 05 Expected Forecast", """
        VAR ym = [DSS Selected Forecast Month]
        VAR mdl = [DSS Selected Forecast Model]
        VAR memberName = SELECTEDVALUE(fact_demand_forecast[member])
        RETURN IF(
            ISBLANK(ym) || ISBLANK(mdl) || ISBLANK(memberName), BLANK(),
            CALCULATE(
                SUM(fact_demand_forecast[forecast_units]),
                REMOVEFILTERS(dim_month), REMOVEFILTERS(dim_year),
                REMOVEFILTERS(dim_calendar), REMOVEFILTERS(dim_date),
                REMOVEFILTERS(fact_demand_forecast),
                fact_demand_forecast[month_id] = ym,
                fact_demand_forecast[model_name] = mdl,
                fact_demand_forecast[level] = "company",
                fact_demand_forecast[is_backtest] = FALSE(),
                TREATAS({memberName}, fact_demand_forecast[member])
            )
        )
    """, "TC-S6-05: đối soát trực tiếp fact theo member/tháng/model, company, không backtest", "#,0.00"),
    _case("TC S6 01 Status", _s6_status(0, 1,
          "ABS(os - ob) <= 0.000001 && ABS(rs - rb) <= 1 && ABS(deltaO) <= 0.000001 && ABS(deltaR) <= 1"),
          "TC-S6-01: d=0, k=1; Baseline=Scenario, Delta=0, hình 16"),
    _case("TC S6 02 Status", _s6_status(0.2, 1,
          "os >= ob && ABS(rs - 1.2 * rb) <= 1"),
          "TC-S6-02: d=+20%, k=1; doanh thu x1.2, xe nhập không giảm, hình 17"),
    _case("TC S6 03 Status", _s6_status(-0.2, 1,
          "os <= ob && ABS(rs - 0.8 * rb) <= 1"),
          "TC-S6-03: d=-20%, k=1; doanh thu x0.8, xe nhập không tăng, hình 18"),
    _case("TC S6 04 Status", _s6_status(0, 2,
          "os >= ob && ABS(rs - rb) <= 1"),
          "TC-S6-04: d=0, k=2; xe nhập không giảm, doanh thu giữ nguyên, hình 19"),
    _case("TC S6 05 Status", """
        VAR actual = [DSS S6 Forecast Units]
        VAR expected = [TC S6 05 Expected Forecast]
        RETURN IF(
            NOT HASONEVALUE(fact_demand_forecast[member]) || ISBLANK(expected), "NO DATA",
            IF(NOT ISBLANK(actual) && ABS(actual - expected) <= 0.000001, "PASS", "FAIL")
        )
    """, "TC-S6-05: đúng một hãng/tháng/model khi đổi bộ lọc, hình 20-22"),
]


def testcase_dax_reference():
    parts = ["// Sinh từ src/powerbi/dss_testcases.py; không sửa trực tiếp file này."]
    for name, dax, _fmt, _folder, description in DSS_TESTCASE_MEASURES:
        parts.extend(["", f"// {description}", f"{name} =", dax])
    return "\n".join(parts) + "\n"
