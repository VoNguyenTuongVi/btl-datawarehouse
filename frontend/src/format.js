const nf = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 0 });
export const num = (v) => (v == null ? '—' : nf.format(v));
export const pct = (v) => (v == null ? '—' : (v * 100).toFixed(1).replace('.', ',') + '%');
export const spct = (v) =>
  v == null ? '—' : (v >= 0 ? '+' : '−') + (Math.abs(v) * 100).toFixed(1).replace('.', ',') + '%';
export const monthLabel = (m) => `${m.slice(5)}/${m.slice(2, 4)}`;

// Ngưỡng do nhóm đề xuất (khớp mart.kpi_parameters)
export const WAPE_MAX = 0.2;
export const BIAS_MAX = 0.05;

export const LEVELS = { total: 'Tổng', region: 'Vùng', company: 'Hãng' };
export const MODELS = { sarima: 'SARIMA', holt_winters: 'Holt-Winters', seasonal_naive: 'Seasonal naive' };

// Độ chính xác gộp từ tổng thành phần (không trung bình các phần trăm)
export function poolAccuracy(accuracy) {
  const groups = new Map();
  for (const r of accuracy) {
    const k = `${r.level}|${r.model_name}`;
    if (!groups.has(k)) groups.set(k, { level: r.level, model: r.model_name, actual: 0, abs: 0, err: 0, n: 0, inside: 0, series: 0, pass: 0 });
    const g = groups.get(k);
    g.actual += r.actual_total;
    g.abs += r.abs_error_total;
    g.err += r.error_total;
    g.n += r.n_points;
    g.inside += r.n_in_interval;
    g.series += 1;
    if (r.actual_total > 0 && r.abs_error_total / r.actual_total <= WAPE_MAX && Math.abs(r.error_total / r.actual_total) <= BIAS_MAX) g.pass += 1;
  }
  const lv = ['total', 'region', 'company'];
  const md = ['sarima', 'holt_winters', 'seasonal_naive'];
  return [...groups.values()]
    .map((g) => ({ level: g.level, model: g.model, wape: g.abs / g.actual, bias: g.err / g.actual, coverage: g.inside / g.n, pass: g.pass, series: g.series }))
    .sort((a, b) => lv.indexOf(a.level) - lv.indexOf(b.level) || md.indexOf(a.model) - md.indexOf(b.model));
}
