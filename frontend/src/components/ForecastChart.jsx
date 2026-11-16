import { Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { MODELS, monthLabel, num } from '../format.js';

export default function ForecastChart({ forecast, model = 'sarima', from, to, height = 300, interval = 2 }) {
  const rows = forecast.filter((r) => r.model_name === model && (!from || r.month >= from) && (!to || r.month <= to));
  const data = rows.map((r) => ({
    name: monthLabel(r.month),
    type: r.series_type,
    actual: r.actual_units,
    fc: r.forecast_units,
    lower: r.lower_80,
    upper: r.upper_80,
    band: r.forecast_units == null || r.lower_80 == null ? null : [r.lower_80, r.upper_80],
  }));
  const span = (t) => {
    const xs = data.filter((d) => d.type === t);
    return xs.length ? [xs[0].name, xs[xs.length - 1].name] : null;
  };
  const bt = span('Backtest');
  const fc = span('Dự báo');
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        {bt && <ReferenceArea x1={bt[0]} x2={bt[1]} fill="var(--muted)" fillOpacity={0.12} label={{ value: 'Backtest', position: 'insideTopLeft', fontSize: 11 }} />}
        {fc && <ReferenceArea x1={fc[0]} x2={fc[1]} fill="var(--muted)" fillOpacity={0.25} label={{ value: 'Dự báo', position: 'insideTopLeft', fontSize: 11 }} />}
        <XAxis dataKey="name" interval={interval} />
        <YAxis tickFormatter={num} width={56} />
        <Tooltip
          formatter={(v, n) => {
            if (n === 'Khoảng 80%') return [`${num(v[0])} – ${num(v[1])}`, n];
            return [`${num(v)} xe`, n];
          }}
        />
        <Legend />
        <Area type="linear" legendType="none" dataKey="band" name="Khoảng 80%" stroke="none" fill="var(--accent)" fillOpacity={0.18} isAnimationActive={false} connectNulls />
        <Line type="linear" dataKey="actual" name="Thực tế" stroke="var(--muted)" strokeWidth={2} dot={false} connectNulls />
        <Line type="linear" dataKey="fc" name={MODELS[model]} stroke="var(--accent)" strokeWidth={2} strokeDasharray="6 4" dot={{ r: 3, fill: 'var(--accent)', stroke: 'none' }} activeDot={{ r: 5 }} isAnimationActive={false} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
