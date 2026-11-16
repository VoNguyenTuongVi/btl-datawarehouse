import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { num, pct, spct } from '../format.js';

export default function BarsChart({ rows, labelWidth = 92, valueKey = 'units', yoyKey = 'units_yoy_pct', shareKey = 'units_share_pct', tip = 'xe' }) {
  const data = rows.map((r) => ({ ...r, label: `${num(r[valueKey])} · ${spct(r[yoyKey])}` }));
  return (
    <ResponsiveContainer width="100%" height={Math.max(180, data.length * 28 + 20)}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 110, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" hide />
        <YAxis type="category" dataKey="member" width={labelWidth} tickLine={false} />
        <Tooltip
          cursor={{ fill: 'var(--hover)' }}
          formatter={(v) => [`${num(v)} ${tip}`, valueKey === 'revenue' ? 'Doanh thu 2023' : 'Sản lượng 2023']}
          labelFormatter={(l, p) => {
            const r = p?.[0]?.payload;
            return r ? `${l} · thị phần ${pct(r[shareKey])} · ${spct(r[yoyKey])} so với 2022` : l;
          }}
        />
        <Bar dataKey={valueKey} fill="var(--accent)" radius={[0, 3, 3, 0]}>
          <LabelList dataKey="label" position="right" fontSize={11} fill="var(--fg-muted)" />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
