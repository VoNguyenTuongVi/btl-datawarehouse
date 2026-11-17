import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { prepareDss, normalizeWeights, rankCompanies, orderCompanies, forecastComparison, reportCaseResults } from './dss.js';

const snapshot = JSON.parse(fs.readFileSync(new URL('../../test-fixtures/data.json', import.meta.url), 'utf8'));
const model = prepareDss(snapshot.dss);
const base = { month: 202401, modelName: 'sarima', weights: [25, 25, 25, 25], demandChange: 0, safetyFactor: 1 };
const near = (actual, expected, tolerance = 1e-6) => assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} != ${expected}`);
const s6 = (company, extra = {}) => orderCompanies(model, { ...base, ...extra }).find((r) => r.company === company);
const status = (id, extra = {}) => reportCaseResults(model, { ...base, ...extra }).find((r) => r.id === id).status;

test('TC-S5-01: Mercedes-B Growth 117.1% from 56.44 forecast and 26 PY', () => {
  const r = rankCompanies(model, base).rows.find((r) => r.company === 'Mercedes-B');
  assert.equal(r.forecast, 56.44); assert.equal(r.py, 26);
  assert.equal(Math.round(r.raw.growth * 1000) / 10, 117.1);
  assert.equal(status('TC-S5-01'), 'PASS');
});

test('TC-S5-02: all eligible normalized scores are bounded', () => {
  const result = rankCompanies(model, base);
  assert.equal(result.eligibleCount, 30);
  for (const r of result.rows) for (const value of Object.values(r.normalized)) assert.ok(value >= 0 && value <= 1);
  const c = result.rows.find((r) => r.company === 'Chevrolet');
  near(c.normalized.growth, 0.402, 0.001); near(c.normalized.share, 1);
  near(c.normalized.stability, 0.729, 0.001); near(c.normalized.accuracy, 0.990, 0.001);
  assert.equal(status('TC-S5-02'), 'PASS');
});

test('TC-S5-03: 50/25/25/25 gives 40/20/20/20 and report ranking', () => {
  const result = rankCompanies(model, { ...base, weights: [50, 25, 25, 25] });
  assert.deepEqual(result.weights.normalized, [0.4, 0.2, 0.2, 0.2]);
  assert.deepEqual(result.rows.slice(0, 3).map((r) => r.company), ['Mercedes-B', 'Plymouth', 'Chevrolet']);
  near(result.rows[0].score, 0.733, 0.001);
  assert.equal(status('TC-S5-03', { weights: [50, 25, 25, 25] }), 'PASS');
});

test('TC-S5-04: four zero weights recover the equal-weight results', () => {
  const before = rankCompanies(model, base);
  const after = rankCompanies(model, { ...base, weights: [0, 0, 0, 0] });
  assert.equal(after.weights.fallback, true);
  assert.deepEqual(after.rows.map((r) => [r.company, r.score, r.rank]), before.rows.map((r) => [r.company, r.score, r.rank]));
  assert.equal(status('TC-S5-04', { weights: [0, 0, 0, 0] }), 'PASS');
});

test('TC-S6-01: Chevrolet and Mercedes-B baseline figures from report', () => {
  const c = s6('Chevrolet'); const m = s6('Mercedes-B');
  assert.equal(c.orderBaseline, 114); assert.equal(c.orderScenario, 114);
  assert.equal(c.orderDelta, 0); near(c.revenueDelta, 0); near(c.revenueBaseline, 2007861, 1);
  assert.equal(m.orderBaseline, 82); near(m.revenueBaseline, 1520767, 1);
  assert.equal(status('TC-S6-01'), 'PASS');
});

test('TC-S6-02: demand +20% gives Chevrolet 137 units and revenue 2409433', () => {
  const c = s6('Chevrolet', { demandChange: 0.2 });
  assert.equal(c.orderScenario, 137); assert.equal(c.orderDelta, 23); near(c.revenueScenario, 2409433, 1);
  assert.equal(status('TC-S6-02', { demandChange: 0.2 }), 'PASS');
});

test('TC-S6-03: demand -20% gives Plymouth 26 units and revenue 502708', () => {
  const p = s6('Plymouth', { demandChange: -0.2 });
  assert.equal(p.orderBaseline, 33); assert.equal(p.orderScenario, 26); near(p.revenueScenario, 502708, 1);
  assert.equal(status('TC-S6-03', { demandChange: -0.2 }), 'PASS');
});

test('TC-S6-04: safety factor affects ordering and preserves revenue', () => {
  const p = s6('Plymouth', { safetyFactor: 2 }); const c = s6('Chevrolet', { safetyFactor: 2 });
  assert.equal(p.orderScenario, 44); assert.equal(c.orderScenario, 152);
  near(p.revenueScenario, p.revenueBaseline); near(c.revenueScenario, c.revenueBaseline);
  assert.equal(status('TC-S6-04', { safetyFactor: 2 }), 'PASS');
});

test('TC-S6-05: all four Chevrolet month/model forecasts match report and source', () => {
  const expected = new Map([['202401|sarima', 76.64], ['202402|sarima', 70.59], ['202401|holt_winters', 53.60], ['202402|holt_winters', 53.31]]);
  for (const r of forecastComparison(model)) {
    near(r.actual, expected.get(`${r.month}|${r.modelName}`)); near(r.actual, r.expected);
    near(s6('Chevrolet', { month: r.month, modelName: r.modelName }).forecast, r.actual);
  }
  assert.equal(status('TC-S6-05'), 'PASS');
});

test('future month selection does not filter historical backtest accuracy', () => {
  const one = rankCompanies(model, base).rows;
  const two = rankCompanies(model, { ...base, month: 202402 }).rows;
  for (const a of one) near(a.raw.accuracy, two.find((b) => b.company === a.company).raw.accuracy);
});

test('missing forecasts and empty company selection never become a zero-valued plan', () => {
  for (const r of rankCompanies(model, { ...base, month: 209901 }).rows) { assert.equal(r.eligible, false); assert.equal(r.rank, null); }
  for (const r of orderCompanies(model, { ...base, month: 209901 })) { assert.equal(r.eligible, false); assert.equal(r.orderScenario, null); }
  assert.deepEqual(rankCompanies(model, { ...base, selectedCompanies: [] }).rows, []);
  assert.equal(status('TC-S6-05', { month: 209901 }), 'NO DATA');
});

test('total and region series cannot pollute company forecasts', () => {
  const payload = structuredClone(snapshot.dss);
  payload.forecasts.push({ level: 'total', member: 'Chevrolet', month_id: 202401, model_name: 'sarima', is_backtest: false, forecast_units: 999999 });
  payload.forecasts.push({ level: 'region', member: 'Chevrolet', month_id: 202401, model_name: 'sarima', is_backtest: false, forecast_units: 999999 });
  const m = prepareDss(payload);
  near(orderCompanies(m, base).find((r) => r.company === 'Chevrolet').forecast, 76.64);
});

test('single eligible company gets neutral min-max scores and rank one', () => {
  const result = rankCompanies(model, { ...base, selectedCompanies: ['Chevrolet'] });
  assert.equal(result.rows[0].rank, 1); near(result.rows[0].score, 0.5);
  assert.deepEqual(Object.values(result.rows[0].normalized), [0.5, 0.5, 0.5, 0.5]);
});

test('duplicate company forecasts are rejected instead of double counted', () => {
  const payload = structuredClone(snapshot.dss);
  payload.forecasts.push({ ...payload.forecasts[0] });
  assert.throws(() => prepareDss(payload), /trùng/);
});

test('inapplicable testcase is N/A rather than PASS', () => {
  assert.equal(status('TC-S5-03'), 'N/A'); assert.equal(status('TC-S6-02'), 'N/A');
  near(normalizeWeights([100, 0, 0, 0]).normalized[0], 1);
});
