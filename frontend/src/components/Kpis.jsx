import { num, pct, spct, WAPE_MAX } from '../format.js';

function Tile({ label, value, sub, tone }) {
  return (
    <div className="tile">
      <span className="k">{label}</span>
      <b className={`v ${tone || ''}`}>{value}</b>
      <span className="d">{sub}</span>
    </div>
  );
}

export default function Kpis({ annual, pooled, dq }) {
  const y = annual.find((r) => r.year === 2023);
  const tot = pooled.find((r) => r.level === 'total' && r.model === 'sarima');
  const vsTarget = y.units / y.target_units - 1;
  const dqOk = dq.filter((r) => r.passed).length;
  return (
    <div className="tiles">
      <Tile label="Sản lượng 2023 (xe)" value={num(y.units)} sub={`${spct(y.units_yoy_pct)} so với 2022`} tone="good" />
      <Tile label="Doanh thu 2023 (USD)" value={num(y.revenue)} sub={`${spct(y.revenue_yoy_pct)} so với 2022`} tone="good" />
      <Tile label="So với mục tiêu +5%" value={spct(vsTarget)} sub={`Mục tiêu ${num(y.target_units)} xe · ${y.units_target_status}`} tone={vsTarget >= 0 ? 'good' : 'bad'} />
      <Tile label="WAPE SARIMA, cấp tổng" value={pct(tot.wape)} sub={`Bias ${spct(tot.bias)} · ngưỡng ${pct(WAPE_MAX)}`} tone={tot.wape <= WAPE_MAX ? 'good' : 'bad'} />
      <Tile label="Kiểm tra chất lượng DW" value={`${dqOk}/${dq.length}`} sub="Q1–Q6, đạt / tổng" tone={dqOk === dq.length ? 'good' : 'bad'} />
    </div>
  );
}
