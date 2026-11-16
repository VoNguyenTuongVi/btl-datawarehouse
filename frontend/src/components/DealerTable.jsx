import { num, pct } from '../format.js';

export default function DealerTable({ rows }) {
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr><th>Hạng</th><th>Dealer</th><th>Vùng</th><th>Số xe bán</th><th>Doanh thu (USD)</th><th>Thị phần (doanh thu)</th></tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.member}>
              <td>{i + 1}</td>
              <td>{r.member}</td>
              <td>{r.region}</td>
              <td>{num(r.units)}</td>
              <td>{num(r.revenue)}</td>
              <td>{pct(r.revenue_share_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
