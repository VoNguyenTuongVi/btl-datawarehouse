import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { num } from '../format.js';

export default function TrendChart({ monthly }) {
  const years = [...new Set(monthly.map((r) => Number(r.month.slice(0, 4))))].sort((a, b) => a - b);
  const colors = ['#7c3aed', '#0891b2', '#d97706', '#db2777'];
  const data = Array.from({ length: 12 }, (_, i) => {
    const m = String(i + 1).padStart(2, '0');
    return { name: `T${i + 1}`, ...Object.fromEntries(years.map((year) => [`y${year}`, monthly.find((r) => r.month === `${year}-${m}`)?.units])) };
  });
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="name" />
        <YAxis tickFormatter={num} width={56} />
        <Tooltip formatter={(v, n) => [`${num(v)} xe`, n]} />
        <Legend />
        {years.map((year, index) => <Line key={year} type="linear" dataKey={`y${year}`} name={String(year)} stroke={index === years.length - 1 ? 'var(--accent)' : colors[index % colors.length]} strokeWidth={2} dot={false} />)}
      </LineChart>
    </ResponsiveContainer>
  );
}
