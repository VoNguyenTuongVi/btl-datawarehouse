import { BIAS_MAX, MODELS, monthLabel, num, pct, spct, WAPE_MAX } from '../format.js';

function Tile({ label, value, sub, tone }) {
  return (
    <div className="tile">
      <span className="k">{label}</span>
      <b className={`v ${tone || ''}`}>{value}</b>
      <span className="d">{sub}</span>
    </div>
  );
}

export default function Kpis({ annual, pooled, dq, parameters, mainModel, forecast }) {
  const y = annual.reduce((latest, row) => row.year > (latest?.year ?? -Infinity) ? row : latest, null);
  const tot = pooled.find((r) => r.level === 'total' && r.model === mainModel);
  const vsTarget = y?.target_units > 0 ? y.units / y.target_units - 1 : null;
  const wapeMax = parameters?.wape_threshold ?? WAPE_MAX;
  const biasMax = parameters?.bias_threshold ?? BIAS_MAX;
  const modelName = MODELS[mainModel] || mainModel;
  const backtest = forecast.filter((row) => row.model_name === mainModel && row.series_type === 'Backtest');
  const period = backtest.length ? `${monthLabel(backtest[0].month)} – ${monthLabel(backtest.at(-1).month)}` : 'Chưa có backtest';
  const dqOk = dq.filter((r) => r.passed).length;
  return (
    <div className="tiles">
      <Tile label={`Sản lượng ${y?.year ?? ''}`} value={num(y?.units)} sub={`${spct(y?.units_yoy_pct)} so với năm trước`} tone="good" />
      <Tile label={`Doanh thu ${y?.year ?? ''}`} value={num(y?.revenue)} sub={`${spct(y?.revenue_yoy_pct)} so với năm trước`} tone="good" />
      <Tile label={`So với mục tiêu ${spct(parameters?.target_growth)}`} value={spct(vsTarget)} sub={y?.units_target_status} tone={vsTarget == null ? '' : vsTarget >= 0 ? 'good' : 'bad'} />
      <Tile label={`WAPE ${modelName}, cấp tổng`} value={pct(tot?.wape)} sub={`${period}, ngưỡng WAPE ≤ ${pct(wapeMax)}`} tone={tot?.wape == null ? '' : tot.wape <= wapeMax ? 'good' : 'bad'} />
      <Tile label={`Bias ${modelName}, cấp tổng`} value={spct(tot?.bias)} sub={`${period}, ngưỡng |Bias| ≤ ${pct(biasMax)}`} tone={tot?.bias == null ? '' : Math.abs(tot.bias) <= biasMax ? 'good' : 'bad'} />
      <Tile label="Kiểm tra chất lượng DW" value={`${dqOk}/${dq.length}`} sub="Đạt/tổng" tone={dqOk === dq.length ? 'good' : 'bad'} />
    </div>
  );
}
