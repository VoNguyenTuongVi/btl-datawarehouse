import Card from './Card.jsx';
import ForecastChart from './ForecastChart.jsx';
import ModelsTable from './ModelsTable.jsx';
import { BIAS_MAX, MODELS, WAPE_MAX, num, pct, spct } from '../format.js';

// SARIMA đứng đầu, sau đó đến các mô hình còn lại
const ORDER = ['sarima', 'holt_winters', 'seasonal_naive'];

function Tile({ label, value, sub, tone }) {
  return (
    <div className="tile">
      <span className="k">{label}</span>
      <b className={`v ${tone || ''}`}>{value}</b>
      <span className="d">{sub}</span>
    </div>
  );
}

const hasBand = (r) => r.lower_80 != null && r.upper_80 != null;

function ModelSection({ model, forecast, pooled }) {
  const rows = forecast.filter((r) => r.model_name === model && r.series_type === 'Backtest');
  const tot = pooled.find((r) => r.level === 'total' && r.model === model);
  const inside = rows.filter((r) => hasBand(r) && r.actual_units >= r.lower_80 && r.actual_units <= r.upper_80).length;
  const name = MODELS[model];
  return (
    <section className="model-section">
      <h2 className="section-title">{name}</h2>
      <div className="tiles">
        <Tile label="WAPE" value={pct(tot.wape)} sub={`Ngưỡng ≤ ${pct(WAPE_MAX)}`} tone={tot.wape <= WAPE_MAX ? 'good' : 'bad'} />
        <Tile label="Bias" value={spct(tot.bias)} sub={`Ngưỡng |Bias| ≤ ${pct(BIAS_MAX)}`} tone={Math.abs(tot.bias) <= BIAS_MAX ? 'good' : 'bad'} />
        <Tile label="Độ phủ 80%" value={`${inside}/${rows.length} tháng`} sub="Số thực tế nằm trong khoảng dự báo" />
      </div>

      <div className="grid">
        <Card title={`${name} so với thực tế, 07–12/2023`}>
          <ForecastChart forecast={forecast} model={model} from="2023-07" to="2023-12" height={300} interval={0} />
        </Card>
        <Card title={`Bảng backtest ${name}, cấp tổng`}>
          <div className="scroll">
            <table>
              <thead>
                <tr><th>Tháng</th><th>Thực tế</th><th>{name}</th><th>Sai lệch</th><th>Sai lệch %</th><th>Cận dưới</th><th>Cận trên</th><th>Trong khoảng</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const diff = r.forecast_units - r.actual_units;
                  const ok = hasBand(r) && r.actual_units >= r.lower_80 && r.actual_units <= r.upper_80;
                  return (
                    <tr key={r.month}>
                      <td>{r.month.slice(5)}/{r.month.slice(0, 4)}</td>
                      <td>{num(r.actual_units)}</td>
                      <td>{num(r.forecast_units)}</td>
                      <td>{diff > 0 ? '+' : ''}{num(diff)}</td>
                      <td>{spct(diff / r.actual_units)}</td>
                      <td>{num(r.lower_80)}</td>
                      <td>{num(r.upper_80)}</td>
                      <td className={hasBand(r) ? (ok ? 'good' : 'bad') : ''}>{hasBand(r) ? (ok ? 'Có' : 'Không') : '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </section>
  );
}

export default function ModelCompareTab({ forecast, pooled }) {
  return (
    <>
      <Card title="Mô hình nào đáng tin? So sánh trên backtest 07–12/2023 (cấp tổng)">
        <ModelsTable pooled={pooled.filter((r) => r.level === 'total')} />
      </Card>
      {ORDER.map((m) => <ModelSection key={m} model={m} forecast={forecast} pooled={pooled} />)}
    </>
  );
}
