
from textwrap import dedent as _dedent

DSS_MEASURES = [
    (
        'DSS Selected Forecast Month',
        _dedent("""
            VAR ym = SELECTEDVALUE(Calendar[YearMonth])
            RETURN IF(
                ISFILTERED(Calendar[YearMonth]) && NOT HASONEVALUE(Calendar[YearMonth]),
                BLANK(), COALESCE(ym, 202401)
            )
        """).strip(),
        '0',
        '4. Hỗ trợ quyết định',
        'S5/S6 – mặc định 202401; chọn đúng một tháng nếu dùng slicer',
    ),
    (
        'DSS Selected Forecast Model',
        _dedent("""
            IF(
                ISFILTERED(fact_demand_forecast[model_name])
                    && NOT HASONEVALUE(fact_demand_forecast[model_name]),
                BLANK(),
                SELECTEDVALUE(fact_demand_forecast[model_name], "sarima")
            )
        """).strip(),
        None,
        '4. Hỗ trợ quyết định',
        'S5/S6 – mặc định sarima; chỉ chọn một mô hình',
    ),
    (
        'DSS Forecast Units Company',
        _dedent("""
            VAR ym = [DSS Selected Forecast Month]
            VAR mdl = [DSS Selected Forecast Model]
            VAR co = SELECTEDVALUE(dim_car[company])
            RETURN IF(
                ISBLANK(co) || ISBLANK(ym) || ISBLANK(mdl), BLANK(),
                CALCULATE(
                    SUM(fact_demand_forecast[forecast_units]),
                    REMOVEFILTERS(Calendar),
                    Calendar[YearMonth] = ym,
                    REMOVEFILTERS(fact_demand_forecast[member]),
                    fact_demand_forecast[level] = "company",
                    fact_demand_forecast[is_backtest] = FALSE(),
                    fact_demand_forecast[model_name] = mdl,
                    TREATAS({ co }, fact_demand_forecast[member])
                )
            )
        """).strip(),
        '#,0.00',
        '4. Hỗ trợ quyết định',
        'S5 – dự báo một tháng theo đúng hãng, mô hình và kỳ',
    ),
    (
        'Priority Growth Raw',
        _dedent("""
            VAR ym = [DSS Selected Forecast Month]
            VAR predicted = [DSS Forecast Units Company]
            VAR lastYear =
                CALCULATE(
                    [Units Sold],
                    REMOVEFILTERS(Calendar),
                    Calendar[YearMonth] = ym - 100
                )
            RETURN IF(
                NOT HASONEVALUE(dim_car[company]) || ISBLANK(predicted)
                    || ISBLANK(ym) || lastYear <= 0,
                BLANK(),
                DIVIDE(predicted - lastYear, lastYear)
            )
        """).strip(),
        '0.0%',
        '4. Hỗ trợ quyết định',
        'S5 – forecast tháng t / actual cùng hãng tháng t-12 trừ 1',
    ),
    (
        'Priority Share Raw',
        _dedent("""
            VAR units = CALCULATE([Units Sold], REMOVEFILTERS(Calendar))
            VAR totalUnits = CALCULATE(
                [Units Sold],
                REMOVEFILTERS(Calendar),
                ALLSELECTED(dim_car[company])
            )
            RETURN IF(
                NOT HASONEVALUE(dim_car[company]) || ISBLANK(units) || totalUnits <= 0,
                BLANK(), DIVIDE(units, totalUnits)
            )
        """).strip(),
        '0.0%',
        '4. Hỗ trợ quyết định',
        'S5 – thị phần sản lượng lịch sử của hãng trên tập hãng được chọn',
    ),
    (
        'Priority Stability Raw',
        _dedent("""
            VAR cv = [Demand CV Hist]
            RETURN IF(NOT HASONEVALUE(dim_car[company]) || ISBLANK(cv), BLANK(), 1 - cv)
        """).strip(),
        '0.000',
        '4. Hỗ trợ quyết định',
        'S5 – 1−CV; không coi CV thiếu bằng 0',
    ),
    (
        'Priority Accuracy Raw',
        _dedent("""
            VAR co = SELECTEDVALUE(dim_car[company])
            VAR mdl = [DSS Selected Forecast Model]
            VAR bt =
                CALCULATETABLE(
                    fact_demand_forecast,
                    REMOVEFILTERS(Calendar),
                    REMOVEFILTERS(fact_demand_forecast[month_start]),
                    REMOVEFILTERS(fact_demand_forecast[member]),
                    fact_demand_forecast[is_backtest] = TRUE(),
                    fact_demand_forecast[level] = "company",
                    fact_demand_forecast[model_name] = mdl,
                    TREATAS({ co }, fact_demand_forecast[member])
                )
            VAR actual = SUMX(bt, fact_demand_forecast[actual_units])
            VAR absErr = SUMX(
                bt,
                ABS(fact_demand_forecast[actual_units] - fact_demand_forecast[forecast_units])
            )
            RETURN IF(
                ISBLANK(co) || ISBLANK(mdl) || actual <= 0,
                BLANK(), 1 - DIVIDE(absErr, actual)
            )
        """).strip(),
        '0.0%',
        '4. Hỗ trợ quyết định',
        'S5 – 1−WAPE cấp hãng, cùng mô hình, toàn bộ backtest lịch sử',
    ),
    (
        'Priority Eligible',
        _dedent("""
            IF(
                HASONEVALUE(dim_car[company])
                    && NOT ISBLANK([DSS Selected Forecast Month])
                    && NOT ISBLANK([DSS Selected Forecast Model])
                    && NOT ISBLANK([Priority Growth Raw])
                    && NOT ISBLANK([Priority Share Raw])
                    && NOT ISBLANK([Priority Stability Raw])
                    && NOT ISBLANK([Priority Accuracy Raw]),
                1, 0
            )
        """).strip(),
        '0',
        '4. Hỗ trợ quyết định',
        'S5 – chỉ hãng có đủ 4 tiêu chí mới được xếp hạng',
    ),
    (
        'Priority Weight Total',
        _dedent("""
            SELECTEDVALUE(Param_Growth[Value], 25)
                + SELECTEDVALUE(Param_Share[Value], 25)
                + SELECTEDVALUE(Param_Stability[Value], 25)
                + SELECTEDVALUE(Param_Accuracy[Value], 25)
        """).strip(),
        '0',
        '5. Mục tiêu & ngưỡng',
        'S5 – tổng 4 mức ưu tiên trên slicer, không bắt buộc bằng 100',
    ),
    (
        'Priority Weight Growth',
        _dedent("""
            VAR t = [Priority Weight Total]
            RETURN IF(t = 0, 0.25, DIVIDE(SELECTEDVALUE(Param_Growth[Value], 25), t))
        """).strip(),
        '0.00%',
        '5. Mục tiêu & ngưỡng',
        'S5 – trọng số Growth đã chuẩn hóa, 4 trọng số cộng bằng 1',
    ),
    (
        'Priority Weight Share',
        _dedent("""
            VAR t = [Priority Weight Total]
            RETURN IF(t = 0, 0.25, DIVIDE(SELECTEDVALUE(Param_Share[Value], 25), t))
        """).strip(),
        '0.00%',
        '5. Mục tiêu & ngưỡng',
        'S5 – trọng số Share đã chuẩn hóa, 4 trọng số cộng bằng 1',
    ),
    (
        'Priority Weight Stability',
        _dedent("""
            VAR t = [Priority Weight Total]
            RETURN IF(t = 0, 0.25, DIVIDE(SELECTEDVALUE(Param_Stability[Value], 25), t))
        """).strip(),
        '0.00%',
        '5. Mục tiêu & ngưỡng',
        'S5 – trọng số Stability đã chuẩn hóa, 4 trọng số cộng bằng 1',
    ),
    (
        'Priority Weight Accuracy',
        _dedent("""
            VAR t = [Priority Weight Total]
            RETURN IF(t = 0, 0.25, DIVIDE(SELECTEDVALUE(Param_Accuracy[Value], 25), t))
        """).strip(),
        '0.00%',
        '5. Mục tiêu & ngưỡng',
        'S5 – trọng số Accuracy đã chuẩn hóa, 4 trọng số cộng bằng 1',
    ),
    (
        'Priority Growth Score',
        _dedent("""
            VAR v = [Priority Growth Raw]
            VAR eligibleCompanies =
                FILTER(
                    ALLSELECTED(dim_car[company]),
                    CALCULATE([Priority Eligible]) = 1
                )
            VAR lo = MINX(eligibleCompanies, CALCULATE([Priority Growth Raw]))
            VAR hi = MAXX(eligibleCompanies, CALCULATE([Priority Growth Raw]))
            RETURN IF(
                [Priority Eligible] <> 1 || ISEMPTY(eligibleCompanies), BLANK(),
                IF(hi = lo, 0.5, DIVIDE(v - lo, hi - lo))
            )
        """).strip(),
        '0.000',
        '4. Hỗ trợ quyết định',
        'S5 – min-max cùng tập hãng hợp lệ; bằng nhau dùng điểm 0.5',
    ),
    (
        'Priority Share Score',
        _dedent("""
            VAR v = [Priority Share Raw]
            VAR eligibleCompanies =
                FILTER(
                    ALLSELECTED(dim_car[company]),
                    CALCULATE([Priority Eligible]) = 1
                )
            VAR lo = MINX(eligibleCompanies, CALCULATE([Priority Share Raw]))
            VAR hi = MAXX(eligibleCompanies, CALCULATE([Priority Share Raw]))
            RETURN IF(
                [Priority Eligible] <> 1 || ISEMPTY(eligibleCompanies), BLANK(),
                IF(hi = lo, 0.5, DIVIDE(v - lo, hi - lo))
            )
        """).strip(),
        '0.000',
        '4. Hỗ trợ quyết định',
        'S5 – min-max cùng tập hãng hợp lệ; bằng nhau dùng điểm 0.5',
    ),
    (
        'Priority Stability Score',
        _dedent("""
            VAR v = [Priority Stability Raw]
            VAR eligibleCompanies =
                FILTER(
                    ALLSELECTED(dim_car[company]),
                    CALCULATE([Priority Eligible]) = 1
                )
            VAR lo = MINX(eligibleCompanies, CALCULATE([Priority Stability Raw]))
            VAR hi = MAXX(eligibleCompanies, CALCULATE([Priority Stability Raw]))
            RETURN IF(
                [Priority Eligible] <> 1 || ISEMPTY(eligibleCompanies), BLANK(),
                IF(hi = lo, 0.5, DIVIDE(v - lo, hi - lo))
            )
        """).strip(),
        '0.000',
        '4. Hỗ trợ quyết định',
        'S5 – min-max cùng tập hãng hợp lệ; bằng nhau dùng điểm 0.5',
    ),
    (
        'Priority Accuracy Score',
        _dedent("""
            VAR v = [Priority Accuracy Raw]
            VAR eligibleCompanies =
                FILTER(
                    ALLSELECTED(dim_car[company]),
                    CALCULATE([Priority Eligible]) = 1
                )
            VAR lo = MINX(eligibleCompanies, CALCULATE([Priority Accuracy Raw]))
            VAR hi = MAXX(eligibleCompanies, CALCULATE([Priority Accuracy Raw]))
            RETURN IF(
                [Priority Eligible] <> 1 || ISEMPTY(eligibleCompanies), BLANK(),
                IF(hi = lo, 0.5, DIVIDE(v - lo, hi - lo))
            )
        """).strip(),
        '0.000',
        '4. Hỗ trợ quyết định',
        'S5 – min-max cùng tập hãng hợp lệ; bằng nhau dùng điểm 0.5',
    ),
    (
        'Priority Score',
        _dedent("""
            VAR g = [Priority Growth Score]
            VAR s = [Priority Share Score]
            VAR st = [Priority Stability Score]
            VAR a = [Priority Accuracy Score]
            RETURN IF(
                [Priority Eligible] <> 1 || ISBLANK(g) || ISBLANK(s)
                    || ISBLANK(st) || ISBLANK(a),
                BLANK(),
                [Priority Weight Growth] * g
                    + [Priority Weight Share] * s
                    + [Priority Weight Stability] * st
                    + [Priority Weight Accuracy] * a
            )
        """).strip(),
        '0.000',
        '4. Hỗ trợ quyết định',
        'S5 – weighted scoring, thang 0..1; không tính thiếu KPI',
    ),
    (
        'Priority Score 100',
        _dedent("""
            IF(ISBLANK([Priority Score]), BLANK(), ROUND(100 * [Priority Score], 4))
        """).strip(),
        '0.00',
        '4. Hỗ trợ quyết định',
        'S5 – điểm hiển thị 0..100, không làm đổi thứ hạng',
    ),
    (
        'Priority Rank',
        _dedent("""
            VAR candidates =
                FILTER(
                    ALLSELECTED(dim_car[company]),
                    CALCULATE([Priority Eligible]) = 1
                )
            RETURN IF(
                [Priority Eligible] <> 1, BLANK(),
                RANKX(candidates, CALCULATE([Priority Score]), , DESC, DENSE)
            )
        """).strip(),
        '0',
        '4. Hỗ trợ quyết định',
        'S5 – xếp hạng giảm dần theo điểm trên cùng tập hãng hợp lệ',
    ),
    (
        'DSS S6 Forecast Units',
        _dedent("""
            VAR ym = [DSS Selected Forecast Month]
            VAR mdl = [DSS Selected Forecast Model]
            VAR memberName = SELECTEDVALUE(fact_demand_forecast[member])
            RETURN IF(
                ISBLANK(ym) || ISBLANK(mdl) || ISBLANK(memberName), BLANK(),
                CALCULATE(
                    SUM(fact_demand_forecast[forecast_units]),
                    REMOVEFILTERS(Calendar),
                    Calendar[YearMonth] = ym,
                    fact_demand_forecast[level] = "company",
                    fact_demand_forecast[is_backtest] = FALSE(),
                    fact_demand_forecast[model_name] = mdl
                )
            )
        """).strip(),
        '#,0.00',
        '4. Hỗ trợ quyết định',
        'S6 – dự báo tháng/mô hình được chọn theo member của cấp company',
    ),
    (
        'DSS S6 Eligible',
        _dedent("""
            VAR f = [DSS S6 Forecast Units]
            VAR cv = CALCULATE([Demand CV for Member], fact_demand_forecast[level] = "company")
            VAR asp = CALCULATE([ASP for Member], fact_demand_forecast[level] = "company")
            RETURN IF(
                HASONEVALUE(fact_demand_forecast[member])
                    && NOT ISBLANK(f) && f >= 0
                    && NOT ISBLANK(cv) && cv >= 0
                    && NOT ISBLANK(asp) && asp > 0,
                1, 0
            )
        """).strip(),
        '0',
        '4. Hỗ trợ quyết định',
        'S6 – chỉ member cấp company có forecast/CV/ASP hợp lệ',
    ),
    (
        'DSS Order Baseline',
        _dedent("""
            VAR f = [DSS S6 Forecast Units]
            VAR cv = CALCULATE([Demand CV for Member], fact_demand_forecast[level] = "company")
            RETURN IF([DSS S6 Eligible] <> 1, BLANK(), MAX(0, ROUNDUP(f * (1 + cv), 0)))
        """).strip(),
        '#,0',
        '4. Hỗ trợ quyết định',
        'S6 – số xe nhập cơ sở: Demand Change 0%, Safety Factor 1',
    ),
    (
        'DSS Order Scenario',
        _dedent("""
            VAR f = [DSS S6 Forecast Units]
            VAR cv = CALCULATE([Demand CV for Member], fact_demand_forecast[level] = "company")
            VAR d = [Demand Change Value]
            VAR k = [Safety Factor Value]
            RETURN IF([DSS S6 Eligible] <> 1, BLANK(), MAX(0, ROUNDUP(f * (1 + d) * (1 + k * cv), 0)))
        """).strip(),
        '#,0',
        '4. Hỗ trợ quyết định',
        'S6 – số xe nhập theo thay đổi nhu cầu và hệ số dự phòng',
    ),
    (
        'DSS Order Delta',
        _dedent("""
            IF([DSS S6 Eligible] <> 1, BLANK(), [DSS Order Scenario] - [DSS Order Baseline])
        """).strip(),
        '+#,0;-#,0;0',
        '4. Hỗ trợ quyết định',
        'S6 – chênh lệch số xe nhập Scenario – Baseline',
    ),
    (
        'DSS Revenue Baseline',
        _dedent("""
            VAR f = [DSS S6 Forecast Units]
            VAR asp = CALCULATE([ASP for Member], fact_demand_forecast[level] = "company")
            RETURN IF([DSS S6 Eligible] <> 1, BLANK(), f * asp)
        """).strip(),
        '$#,0',
        '4. Hỗ trợ quyết định',
        'S6 – doanh thu dự kiến cơ sở: sản lượng dự báo × ASP lịch sử',
    ),
    (
        'DSS Revenue Scenario',
        _dedent("""
            VAR f = [DSS S6 Forecast Units]
            VAR asp = CALCULATE([ASP for Member], fact_demand_forecast[level] = "company")
            RETURN IF([DSS S6 Eligible] <> 1, BLANK(), f * (1 + [Demand Change Value]) * asp)
        """).strip(),
        '$#,0',
        '4. Hỗ trợ quyết định',
        'S6 – doanh thu kịch bản theo Demand Change; không nhân Safety Factor',
    ),
    (
        'DSS Revenue Delta',
        _dedent("""
            IF([DSS S6 Eligible] <> 1, BLANK(), [DSS Revenue Scenario] - [DSS Revenue Baseline])
        """).strip(),
        '+$#,0;-$#,0;$0',
        '4. Hỗ trợ quyết định',
        'S6 – chênh lệch doanh thu Scenario – Baseline',
    ),
]
