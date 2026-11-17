import { BIAS_MAX, LEVELS, MODELS, WAPE_MAX, pct, spct } from '../format.js';

export default function ModelsTable({ pooled }) {
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr><th>Cấp</th><th>Mô hình</th><th>WAPE</th><th>Bias</th><th>Độ phủ 80%</th><th>Chuỗi đạt</th></tr>
        </thead>
        <tbody>
          {pooled.map((r) => (
            <tr key={`${r.level}-${r.model}`} className={r.model === r.mainModel ? 'main' : ''}>
              <td>{LEVELS[r.level]} ({r.series} chuỗi)</td>
              <td>{MODELS[r.model] || r.model}</td>
              <td className={r.wape == null ? '' : r.wape <= (r.wapeMax ?? WAPE_MAX) ? 'good' : 'bad'}>{pct(r.wape)}</td>
              <td className={r.bias == null ? '' : Math.abs(r.bias) <= (r.biasMax ?? BIAS_MAX) ? 'good' : 'bad'}>{spct(r.bias)}</td>
              <td>{pct(r.coverage)}</td>
              <td>{r.pass}/{r.series}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
