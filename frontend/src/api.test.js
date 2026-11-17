import test from 'node:test';
import assert from 'node:assert/strict';
import { loadDashboard } from './api.js';

const payload = () => ({ monthly: [], forecast: [], accuracy: [], company: [], region: [], annual: [], dq: [], model: [], dealer: [], dss: { history: [], forecasts: [] } });

test('every load calls the DB API with no-store; a second response replaces the first', async () => {
  let version = 0;
  const fetcher = async (url, options) => {
    assert.equal(url, '/api/dashboard'); assert.equal(options.cache, 'no-store');
    return { ok: true, json: async () => ({ ...payload(), version: ++version }) };
  };
  assert.equal((await loadDashboard({ fetcher })).version, 1);
  assert.equal((await loadDashboard({ fetcher })).version, 2);
});

test('database errors stay errors rather than returning a sample snapshot', async () => {
  const fetcher = async () => ({ ok: false, status: 503, json: async () => ({ message: 'DB chưa chạy' }) });
  await assert.rejects(loadDashboard({ fetcher }), /DB chưa chạy/);
});

test('unreachable API and HTML proxy error have actionable messages', async () => {
  await assert.rejects(loadDashboard({ fetcher: async () => { throw new TypeError('fetch failed'); } }), /py -3 src\/api.py/);
  await assert.rejects(loadDashboard({ fetcher: async () => ({ json: async () => { throw new SyntaxError('HTML'); } }) }), /API chưa sẵn sàng/);
});

test('incompatible backend payload is rejected', async () => {
  await assert.rejects(loadDashboard({ fetcher: async () => ({ ok: true, json: async () => ({}) }) }), /không đúng định dạng/);
});
