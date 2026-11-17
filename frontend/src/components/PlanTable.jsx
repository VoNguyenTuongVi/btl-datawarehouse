import { num } from '../format.js';

export default function PlanTable({ forecast, model }) {
  const rows = forecast.filter((r) => r.model_name === model && r.series_type === 'Dự báo');
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr><th>Tháng</th><th>Dự báo (xe)</th><th>Cận dưới 80%</th><th>Cận trên 80%</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.month}>
              <td>{r.month.slice(5)}/{r.month.slice(0, 4)}</td>
              <td>{num(r.forecast_units)}</td>
              <td>{num(r.lower_80)}</td>
              <td>{num(r.upper_80)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
