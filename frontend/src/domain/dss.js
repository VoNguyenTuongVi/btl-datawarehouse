export const DEFAULT_WEIGHTS = [25, 25, 25, 25];
export const CRITERIA = [
  { key: 'growth', label: 'Tăng trưởng', short: 'Growth' },
  { key: 'share', label: 'Thị phần', short: 'Share' },
  { key: 'stability', label: 'Ổn định', short: 'Stability' },
  { key: 'accuracy', label: 'Độ chính xác', short: 'Accuracy' },
];
const finite = (v) => typeof v === 'number' && Number.isFinite(v);
const sum = (rows, get) => rows.reduce((total, r) => total + get(r), 0);
const key = (...parts) => JSON.stringify(parts);
const close = (a, b, tolerance = 1e-6) => finite(a) && finite(b) && Math.abs(a - b) <= tolerance;

export function normalizeWeights(values = DEFAULT_WEIGHTS) {
  const raw = DEFAULT_WEIGHTS.map((fallback, i) => Math.max(0, Math.min(100, finite(values[i]) ? values[i] : fallback)));
  const total = sum(raw, (v) => v);
  return { raw, total, normalized: total ? raw.map((v) => v / total) : [0.25, 0.25, 0.25, 0.25], fallback: total === 0 };
}

export function prepareDss(payload) {
  if (payload?.schema_version !== 1 || !Array.isArray(payload.history) || !Array.isArray(payload.forecasts)) {
    throw new Error('Chưa có dữ liệu DSS hợp lệ. Hãy xuất lại dữ liệu frontend.');
  }
  const profiles = new Map();
  for (const r of payload.history) {
    if (!r.company || !finite(r.units) || !finite(r.revenue) || !Number.isInteger(r.month_id)) continue;
    if (!profiles.has(r.company)) profiles.set(r.company, { company: r.company, months: new Map(), units: 0, revenue: 0 });
    const p = profiles.get(r.company);
    if (p.months.has(r.month_id)) throw new Error(`Lịch sử bị trùng hãng/tháng: ${r.company}.`);
    p.months.set(r.month_id, r.units);
    p.units += r.units;
    p.revenue += r.revenue;
  }
  for (const p of profiles.values()) {
    const months = [...p.months.values()].filter((v) => v > 0);
    const mean = months.length ? sum(months, (v) => v) / months.length : 0;
    p.cv = months.length >= 2 && mean > 0 ? Math.sqrt(sum(months, (v) => (v - mean) ** 2) / months.length) / mean : null;
    p.asp = p.units > 0 ? p.revenue / p.units : null;
  }
  const future = new Map();
  const backtests = new Map();
  const companies = new Set(profiles.keys());
  const months = new Set();
  const models = new Set();
  const seen = new Set();
  for (const r of payload.forecasts) {
    if (r.level !== 'company') continue;
    const signature = key(r.member, r.model_name, r.month_id, r.is_backtest);
    if (seen.has(signature)) throw new Error(`Dự báo bị trùng hãng/model/tháng: ${r.member}.`);
    seen.add(signature);
    companies.add(r.member);
    if (r.is_backtest === true) {
      if (!finite(r.actual_units) || !finite(r.forecast_units)) continue;
      const k = key(r.member, r.model_name);
      if (!backtests.has(k)) backtests.set(k, { actual: 0, absError: 0 });
      const b = backtests.get(k);
      b.actual += r.actual_units;
      b.absError += Math.abs(r.forecast_units - r.actual_units);
    } else if (r.is_backtest === false) {
      future.set(key(r.member, r.month_id, r.model_name), r);
      months.add(r.month_id);
      models.add(r.model_name);
    }
  }
  return { profiles, future, backtests, companies: [...companies].sort(), months: [...months].sort(), models: [...models].sort(), metadata: payload };
}

function members(model, selection) {
  if (selection == null) return model.companies;
  const chosen = new Set(selection);
  return model.companies.filter((c) => chosen.has(c));
}

export function rankCompanies(model, options) {
  const companies = members(model, options.selectedCompanies);
  const weights = normalizeWeights(options.weights);
  const denominator = sum(companies, (c) => model.profiles.get(c)?.units || 0);
  const rows = companies.map((company) => {
    const p = model.profiles.get(company);
    const f = model.future.get(key(company, options.month, options.modelName))?.forecast_units;
    const py = p?.months.get(options.month - 100);
    const backtest = model.backtests.get(key(company, options.modelName));
    const raw = {
      growth: finite(f) && py > 0 ? (f - py) / py : null,
      share: p && denominator > 0 ? p.units / denominator : null,
      stability: finite(p?.cv) ? 1 - p.cv : null,
      accuracy: backtest?.actual > 0 ? 1 - backtest.absError / backtest.actual : null,
    };
    const missing = [];
    if (!finite(f)) missing.push('thiếu forecast');
    if (!(py > 0)) missing.push('thiếu cùng kỳ năm trước');
    if (!finite(p?.cv)) missing.push('thiếu CV lịch sử');
    if (!(backtest?.actual > 0)) missing.push('thiếu backtest');
    return { company, forecast: finite(f) ? f : null, py: finite(py) ? py : null, raw,
      cv: p?.cv ?? null, asp: p?.asp ?? null,
      eligible: CRITERIA.every((c) => finite(raw[c.key])), missing,
      normalized: {}, score: null, rank: null };
  });
  const eligible = rows.filter((r) => r.eligible);
  for (const { key: criterion } of CRITERIA) {
    const values = eligible.map((r) => r.raw[criterion]);
    const low = Math.min(...values);
    const high = Math.max(...values);
    for (const row of rows) row.normalized[criterion] = row.eligible ? (high === low ? 0.5 : (row.raw[criterion] - low) / (high - low)) : null;
  }
  for (const r of eligible) r.score = sum(CRITERIA, (c) => r.normalized[c.key] * weights.normalized[CRITERIA.indexOf(c)]);
  rows.sort((a, b) => Number(b.eligible) - Number(a.eligible) || (b.score ?? 0) - (a.score ?? 0) || a.company.localeCompare(b.company));
  let last = null;
  let rank = 0;
  for (const r of rows) {
    if (!r.eligible) continue;
    if (last === null || r.score !== last) rank += 1;
    r.rank = rank;
    last = r.score;
  }
  return { rows, weights, eligibleCount: eligible.length };
}

export function orderCompanies(model, options) {
  const demand = Math.max(-0.3, Math.min(0.3, finite(options.demandChange) ? options.demandChange : 0));
  const safety = Math.max(0, Math.min(2, finite(options.safetyFactor) ? options.safetyFactor : 1));
  return members(model, options.selectedCompanies).map((company) => {
    const p = model.profiles.get(company);
    const forecast = model.future.get(key(company, options.month, options.modelName))?.forecast_units;
    const cv = p?.cv;
    const asp = p?.asp;
    const eligible = finite(forecast) && forecast >= 0 && finite(cv) && cv >= 0 && finite(asp) && asp > 0;
    const orderBaseline = eligible ? Math.max(0, Math.ceil(forecast * (1 + cv))) : null;
    const orderScenario = eligible ? Math.max(0, Math.ceil(forecast * (1 + demand) * (1 + safety * cv))) : null;
    const revenueBaseline = eligible ? forecast * asp : null;
    const revenueScenario = eligible ? forecast * (1 + demand) * asp : null;
    return { company, forecast: finite(forecast) ? forecast : null, cv: finite(cv) ? cv : null, asp: finite(asp) ? asp : null, eligible,
      orderBaseline, orderScenario, orderDelta: eligible ? orderScenario - orderBaseline : null,
      revenueBaseline, revenueScenario, revenueDelta: eligible ? revenueScenario - revenueBaseline : null };
  }).sort((a, b) => Number(b.eligible) - Number(a.eligible) || (b.orderScenario ?? 0) - (a.orderScenario ?? 0) || a.company.localeCompare(b.company));
}

export function forecastComparison(model, company = 'Chevrolet') {
  const paper = model.metadata.cases?.find((c) => c.id === 'TC-S6-05')?.reference?.forecasts || [];
  return [202401, 202402].flatMap((month) => ['sarima', 'holt_winters'].map((modelName) => ({
    company, month, modelName,
    actual: model.future.get(key(company, month, modelName))?.forecast_units ?? null,
    expected: expectedForecast(model, company, month, modelName),
    reference: company === 'Chevrolet' ? paper.find((p) => p.month === month && p.model === modelName)?.forecast ?? null : null,
  })));
}

export function expectedForecast(model, company, month, modelName) {
  const rows = model.metadata.forecasts.filter((r) => r.level === 'company' && r.is_backtest === false
    && r.member === company && r.month_id === month && r.model_name === modelName);
  return rows.length && rows.every((r) => finite(r.forecast_units)) ? sum(rows, (r) => r.forecast_units) : null;
}

export function reportCaseResults(model, options) {
  const ranking = rankCompanies(model, options);
  const ordering = orderCompanies(model, options);
  const eligibleS5 = ranking.rows.filter((r) => r.eligible);
  const eligibleS6 = ordering.filter((r) => r.eligible);
  const assess = (rows, check) => !rows.length ? 'NO DATA' : rows.every(check) ? 'PASS' : 'FAIL';
  const weightsAre = (wanted) => ranking.weights.raw.every((w, i) => w === wanted[i]);
  const weightCase = (raw, expected) => !weightsAre(raw) ? 'N/A' : ranking.weights.normalized.every((w, i) => close(w, expected[i])) ? 'PASS' : 'FAIL';
  const scenarioCase = (d, k, check) => !close(options.demandChange ?? 0, d) || !close(options.safetyFactor ?? 1, k) ? 'N/A' : assess(eligibleS6, check);
  const status = {
    'TC-S5-01': assess(ranking.rows.filter((r) => r.py > 0 && finite(r.forecast)), (r) => close(r.raw.growth, (r.forecast - r.py) / r.py)),
    'TC-S5-02': assess(eligibleS5, (r) => CRITERIA.every((c) => finite(r.normalized[c.key]) && r.normalized[c.key] >= 0 && r.normalized[c.key] <= 1)),
    'TC-S5-03': weightCase([50, 25, 25, 25], [0.4, 0.2, 0.2, 0.2]),
    'TC-S5-04': weightCase([0, 0, 0, 0], [0.25, 0.25, 0.25, 0.25]),
    'TC-S6-01': scenarioCase(0, 1, (r) => r.orderBaseline === r.orderScenario && close(r.revenueBaseline, r.revenueScenario, 1) && r.orderDelta === 0 && close(r.revenueDelta, 0, 1)),
    'TC-S6-02': scenarioCase(0.2, 1, (r) => r.orderScenario >= r.orderBaseline && close(r.revenueScenario, 1.2 * r.revenueBaseline, 1)),
    'TC-S6-03': scenarioCase(-0.2, 1, (r) => r.orderScenario <= r.orderBaseline && close(r.revenueScenario, 0.8 * r.revenueBaseline, 1)),
    'TC-S6-04': scenarioCase(0, 2, (r) => r.orderScenario >= r.orderBaseline && close(r.revenueScenario, r.revenueBaseline, 1)),
    'TC-S6-05': assess(ordering.filter((r) => finite(r.forecast)), (r) => close(r.forecast, expectedForecast(model, r.company, options.month, options.modelName))),
  };
  const setups = ['01/2024 · SARIMA', 'Hãng đủ 4 tiêu chí', '50 / 25 / 25 / 25', '0 / 0 / 0 / 0', 'd = 0% · k = 1', 'd = +20% · k = 1', 'd = −20% · k = 1', 'd = 0% · k = 2', 'Đổi tháng và model'];
  return (model.metadata.cases || []).map((c, i) => ({ ...c, status: status[c.id] ?? 'NO DATA', setupLabel: setups[i] }));
}
