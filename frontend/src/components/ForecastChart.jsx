import { CartesianGrid, ComposedChart, ErrorBar, Legend, Line, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { monthLabel, num } from '../format.js';

export default function ForecastChart({ forecast }) {
  const rows = forecast.filter((r) => r.model_name === 'sarima');
  const data = rows.map((r) => ({
    name: monthLabel(r.month),
    type: r.series_type,
    actual: r.actual_units,
    fc: r.forecast_units,
    lower: r.lower_80,
    upper: r.upper_80,
    err: r.forecast_units == null ? null : [r.forecast_units - r.lower_80, r.upper_80 - r.forecast_units],
  }));
  const span = (t) => {
    const xs = data.filter((d) => d.type === t);
    return xs.length ? [xs[0].name, xs[xs.length - 1].name] : null;
  };
  const bt = span('Backtest');
  const fc = span('Dự báo');
  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        {bt && <ReferenceArea x1={bt[0]} x2={bt[1]} fill="var(--muted)" fillOpacity={0.12} label={{ value: 'Backtest', position: 'insideTopLeft', fontSize: 11 }} />}
        {fc && <ReferenceArea x1={fc[0]} x2={fc[1]} fill="var(--muted)" fillOpacity={0.25} label={{ value: 'Dự báo', position: 'insideTopLeft', fontSize: 11 }} />}
        <XAxis dataKey="name" interval={2} />
        <YAxis tickFormatter={num} width={56} />
        <Tooltip
          formatter={(v, n, p) => {
            if (n === 'SARIMA' && p.payload.lower != null) return [`${num(v)} (${num(p.payload.lower)}–${num(p.payload.upper)})`, n];
            return [`${num(v)} xe`, n];
          }}
        />
        <Legend />
        <Line type="linear" dataKey="actual" name="Thực tế" stroke="var(--muted)" strokeWidth={2} dot={false} connectNulls />
        <Line type="linear" dataKey="fc" name="SARIMA" stroke="none" dot={{ r: 4, fill: 'var(--accent)', stroke: 'none' }} activeDot={{ r: 5 }} isAnimationActive={false}>
          <ErrorBar dataKey="err" width={4} stroke="var(--accent)" strokeOpacity={0.5} strokeWidth={2} />
        </Line>
      </ComposedChart>
    </ResponsiveContainer>
  );
}
