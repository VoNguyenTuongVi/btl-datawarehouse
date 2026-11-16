import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { num } from '../format.js';

export default function TrendChart({ monthly }) {
  const data = Array.from({ length: 12 }, (_, i) => {
    const m = String(i + 1).padStart(2, '0');
    const a = monthly.find((r) => r.month === `2022-${m}`);
    const b = monthly.find((r) => r.month === `2023-${m}`);
    return { name: `T${i + 1}`, y2022: a?.units, y2023: b?.units };
  });
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="name" />
        <YAxis tickFormatter={num} width={56} />
        <Tooltip formatter={(v, n) => [`${num(v)} xe`, n]} />
        <Legend />
        <Line type="linear" dataKey="y2022" name="2022" stroke="var(--muted)" strokeWidth={2} dot={false} />
        <Line type="linear" dataKey="y2023" name="2023" stroke="var(--accent)" strokeWidth={2.5} dot={{ r: 3 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
