import { useEffect, useMemo, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import Card from './Card.jsx';
import { MODELS, num, pct, spct } from '../format.js';
import { CRITERIA, DEFAULT_WEIGHTS, forecastComparison, orderCompanies, prepareDss, rankCompanies, reportCaseResults } from '../domain/dss.js';
import '../dss.css';

const decimal = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });
const dec = (v) => v == null ? '—' : decimal.format(v);
const money = (v) => v == null ? '—' : `${num(v)} USD`;
const monthName = (v) => `${String(v).slice(4)}/${String(v).slice(0, 4)}`;
const signed = (v, formatter = num) => v == null ? '—' : `${v > 0 ? '+' : ''}${formatter(v)}`;
const setupEqual = (a, b) => Math.abs(a - b) < 1e-6;

function Badge({ value }) {
  const cls = { PASS: 'pass', FAIL: 'fail', 'N/A': 'na', 'NO DATA': 'empty' }[value] || 'empty';
  return <span className={`dss-status ${cls}`}>{value}</span>;
}

function Metric({ label, value, note, tone }) {
  return <div className="tile dss-metric"><span className="k">{label}</span><strong className={`v ${tone || ''}`}>{value}</strong><span className="d">{note}</span></div>;
}

function CompanyPicker({ companies, selected, onChange }) {
  const [search, setSearch] = useState('');
  const chosen = new Set((selected ?? companies).filter((c) => companies.includes(c)));
  const shown = companies.filter((c) => c.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  function toggle(company) {
    const next = new Set(chosen);
    if (next.has(company)) next.delete(company); else next.add(company);
    onChange([...next]);
  }
  return (
    <details className="dss-company-picker">
      <summary>Hãng xe <span>{chosen.size}/{companies.length} đang chọn</span></summary>
      <div className="dss-company-content">
        <div className="dss-company-actions">
          <input aria-label="Tìm hãng xe" type="search" placeholder="Tìm hãng xe…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <button type="button" onClick={() => onChange(null)}>Chọn tất cả</button>
          <button type="button" onClick={() => onChange([])}>Bỏ chọn</button>
        </div>
        <div className="dss-company-grid">
          {shown.map((c) => <label key={c}><input type="checkbox" checked={chosen.has(c)} onChange={() => toggle(c)} />{c}</label>)}
          {!shown.length && <p className="note">Không có hãng phù hợp.</p>}
        </div>
      </div>
    </details>
  );
}

function csvDownload(filename, columns, rows) {
  const quote = (v) => `"${String(v ?? '').replaceAll('"', '""')}"`;
  const text = '\uFEFF' + [columns.map((c) => quote(c[0])).join(','), ...rows.map((row) => columns.map((c) => quote(row[c[1]])).join(','))].join('\r\n');
  const link = document.createElement('a');
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8;' }));
  link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function PriorityView({ result, options, setOptions }) {
  const [showRaw, setShowRaw] = useState(false);
  const valid = result.rows.filter((r) => r.eligible);
  const first = valid[0];
  return (
    <>
      <Card title="S5 · Chọn mức ưu tiên của bốn tiêu chí">
        <div className="dss-presets" aria-label="Bộ trọng số mẫu">
          <button onClick={() => setOptions((s) => ({ ...s, weights: [...DEFAULT_WEIGHTS] }))}>Cân bằng 25/25/25/25</button>
          <button onClick={() => setOptions((s) => ({ ...s, weights: [50, 25, 25, 25] }))}>Ưu tiên tăng trưởng 50/25/25/25</button>
          <button onClick={() => setOptions((s) => ({ ...s, weights: [0, 0, 0, 0] }))}>Kiểm tra trọng số bằng 0</button>
        </div>
        <div className="dss-weights">
          {CRITERIA.map((c, i) => <label className="dss-weight" key={c.key}>
            <span className="dss-weight-title">{c.label} <b>{pct(result.weights.normalized[i])}</b></span>
            <span className="note">{c.short} · trọng số sau chuẩn hóa</span>
            <div className="dss-weight-inputs">
              <input aria-label={`Trọng số ${c.short}`} type="range" min="0" max="100" step="5" value={options.weights[i]} onChange={(e) => setOptions((s) => ({ ...s, weights: s.weights.map((v, n) => n === i ? Number(e.target.value) : v) }))} />
              <input aria-label={`Giá trị ${c.short}`} type="number" min="0" max="100" step="5" value={options.weights[i]} onChange={(e) => setOptions((s) => ({ ...s, weights: s.weights.map((v, n) => n === i ? Math.max(0, Math.min(100, Number(e.target.value))) : v) }))} onBlur={() => setOptions((s) => ({ ...s, weights: s.weights.map((v, n) => n === i ? Math.round(v / 5) * 5 : v) }))} />
            </div>
          </label>)}
        </div>
        <p className={result.weights.fallback ? 'dss-callout' : 'note'} role="status">{result.weights.fallback ? 'Tổng trọng số bằng 0: tự dùng 25% cho mỗi tiêu chí.' : `Tổng giá trị nhập ${result.weights.total}; bốn trọng số thực được chuẩn hóa về 100%.`}</p>
      </Card>

      <div className="tiles">
        <Metric label="Hãng đủ điều kiện" value={`${result.eligibleCount}/${result.rows.length}`} note="Có đủ Growth, Share, Stability và Accuracy" />
        <Metric label="Ưu tiên cao nhất" value={first?.company || '—'} note={first ? `Hạng 1 · ${dec(first.score * 100)}/100 điểm` : 'Chọn hãng và kỳ có đủ dữ liệu'} />
        <Metric label="Tập đánh giá" value={num(result.rows.length)} note="Min–max trên cùng tập hãng hợp lệ" />
      </div>

      {valid.length > 0 && <Card title="Top 10 hãng theo điểm ưu tiên" note="Điểm 0–100; điểm lớn hơn được ưu tiên hơn.">
        <ResponsiveContainer width="100%" height={Math.max(190, Math.min(10, valid.length) * 33)}>
          <BarChart data={valid.slice(0, 10).map((r) => ({ company: r.company, score: r.score * 100 }))} layout="vertical" margin={{ left: 5, right: 24 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" domain={[0, 100]} /><YAxis type="category" dataKey="company" width={115} />
            <Tooltip formatter={(v) => [dec(v), 'Điểm ưu tiên']} /><Bar dataKey="score" fill="var(--accent)" radius={[0, 4, 4, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </Card>}

      <Card title="Bảng xếp hạng và thành phần điểm">
        <div className="dss-table-actions">
          <label className="dss-check"><input type="checkbox" checked={showRaw} onChange={(e) => setShowRaw(e.target.checked)} />Hiện chỉ số gốc</label>
          <button onClick={() => csvDownload('dss-s5-ranking.csv', [['Hạng', 'rank'], ['Hãng', 'company'], ['Điểm 0-1', 'score'], ['Forecast', 'forecast'], ['Actual cùng kỳ', 'py'], ['Đủ điều kiện', 'eligible']], result.rows)}>Tải bảng CSV</button>
        </div>
        <div className="scroll"><table className="dss-table"><thead><tr><th>Hạng</th><th>Hãng</th><th>Điểm /100</th>{CRITERIA.map((c) => <th key={c.key}>{c.short}{showRaw ? ' gốc' : ' score'}</th>)}<th>Forecast (xe)</th><th>Điều kiện</th></tr></thead>
          <tbody>{result.rows.map((r) => <tr key={r.company}><td>{r.rank ?? '—'}</td><td>{r.company}</td><td><b>{r.score == null ? '—' : dec(r.score * 100)}</b></td>{CRITERIA.map((c) => <td key={c.key}>{showRaw ? (c.key === 'stability' ? dec(r.raw[c.key]) : pct(r.raw[c.key])) : dec(r.normalized[c.key])}</td>)}<td>{dec(r.forecast)}</td><td>{r.eligible ? <span className="dss-eligible">Đủ dữ liệu</span> : <span className="note" title={r.missing.join(', ')}>{r.missing.join(', ') || 'Thiếu dữ liệu'}</span>}</td></tr>)}</tbody>
        </table></div>
        {!result.rows.length && <p className="dss-empty">Chọn ít nhất một hãng để xếp hạng.</p>}
      </Card>
      <details className="defs"><summary>Cách tính S5</summary><p>Growth = forecast tháng đang chọn / số xe cùng tháng năm trước − 1. Share là tỷ trọng sản lượng lịch sử trong tập hãng đang chọn. Stability = 1 − CV sản lượng tháng lịch sử. Accuracy = 1 − WAPE backtest của model đang chọn.</p><p>Bốn tiêu chí dùng chung tập hãng đủ dữ liệu để chuẩn hóa min–max. Nếu min = max, điểm tiêu chí bằng 0,5. Điểm cuối là tổng điểm tiêu chí nhân trọng số thực; xếp hạng giảm dần, Dense.</p></details>
    </>
  );
}

const SCENARIOS = [
  { label: 'Baseline · 0%, k=1', d: 0, k: 1 },
  { label: 'Nhu cầu +20%', d: 0.2, k: 1 },
  { label: 'Nhu cầu −20%', d: -0.2, k: 1 },
  { label: 'Tăng dự phòng · k=2', d: 0, k: 2 },
];

function OrderingView({ rows, options, setOptions }) {
  const valid = rows.filter((r) => r.eligible);
  const total = (field) => valid.length ? valid.reduce((t, r) => t + r[field], 0) : null;
  return <>
    <Card title="S6 · Thử kịch bản nhu cầu và mức dự phòng">
      <div className="dss-presets" aria-label="Kịch bản mẫu">{SCENARIOS.map((p) => <button key={p.label} className={setupEqual(options.demandChange, p.d) && setupEqual(options.safetyFactor, p.k) ? 'active' : ''} onClick={() => setOptions((s) => ({ ...s, demandChange: p.d, safetyFactor: p.k }))}>{p.label}</button>)}</div>
      <div className="dss-scenario-inputs">
        <label className="dss-weight"><span className="dss-weight-title">Thay đổi nhu cầu <b>{spct(options.demandChange)}</b></span><input aria-label="Demand Change" type="range" min="-30" max="30" step="5" value={Math.round(options.demandChange * 100)} onChange={(e) => setOptions((s) => ({ ...s, demandChange: Number(e.target.value) / 100 }))} /><span className="note">−30% đến +30% · ảnh hưởng lượng nhập và doanh thu</span></label>
        <label className="dss-weight"><span className="dss-weight-title">Hệ số dự phòng <b>{dec(options.safetyFactor)}</b></span><input aria-label="Safety Factor" type="range" min="0" max="20" step="1" value={Math.round(options.safetyFactor * 10)} onChange={(e) => setOptions((s) => ({ ...s, safetyFactor: Number(e.target.value) / 10 }))} /><span className="note">0 đến 2 · ảnh hưởng lượng nhập đề xuất</span></label>
      </div>
      <p className="note">Baseline cố định ở nhu cầu 0%, k=1. Doanh thu là giá trị dự kiến theo nhu cầu, chưa tính tồn kho, chi phí hay lợi nhuận.</p>
    </Card>
    <div className="tiles">
      <Metric label="Số xe nhập · Scenario" value={num(total('orderScenario'))} note={`Baseline ${num(total('orderBaseline'))} · chênh lệch ${signed(total('orderDelta'))} xe`} />
      <Metric label="Doanh thu · Scenario" value={money(total('revenueScenario'))} note={`Chênh lệch ${signed(total('revenueDelta'), money)}`} />
      <Metric label="Hãng đủ điều kiện" value={`${valid.length}/${rows.length}`} note="Tổng ở đây chỉ cộng các hãng hợp lệ đang chọn" />
    </div>
    {valid.length > 0 && <Card title="So sánh số xe nhập theo hãng" note="Tối đa 10 hãng có lượng nhập Scenario cao nhất."><ResponsiveContainer width="100%" height={330}><BarChart data={valid.slice(0, 10)} margin={{ top: 10, right: 12, bottom: 25 }}><CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="company" angle={-20} textAnchor="end" height={65} interval={0} tick={{ fontSize: 11 }} /><YAxis tickFormatter={num} /><Tooltip formatter={(v) => num(v)} /><Legend /><Bar dataKey="orderBaseline" name="Baseline" fill="var(--muted)" isAnimationActive={false} /><Bar dataKey="orderScenario" name="Scenario" fill="var(--accent)" isAnimationActive={false} /></BarChart></ResponsiveContainer></Card>}
    <Card title="Kế hoạch nhập xe và doanh thu theo hãng">
      <div className="dss-table-actions"><span className="note">Số xe nhập làm tròn lên; doanh thu tính từ ASP lịch sử từng hãng.</span><button onClick={() => csvDownload('dss-s6-scenario.csv', [['Hãng', 'company'], ['Forecast', 'forecast'], ['CV', 'cv'], ['ASP', 'asp'], ['Order Baseline', 'orderBaseline'], ['Order Scenario', 'orderScenario'], ['Order Delta', 'orderDelta'], ['Revenue Baseline', 'revenueBaseline'], ['Revenue Scenario', 'revenueScenario'], ['Revenue Delta', 'revenueDelta']], rows)}>Tải bảng CSV</button></div>
      <div className="scroll"><table className="dss-table dss-orders"><thead><tr><th>Hãng</th><th>Forecast</th><th>CV</th><th>ASP (USD)</th><th>Nhập cơ sở</th><th>Nhập kịch bản</th><th>Δ Xe</th><th>Doanh thu cơ sở</th><th>Doanh thu kịch bản</th><th>Δ USD</th></tr></thead><tbody>{rows.map((r) => <tr key={r.company}><td>{r.company}{!r.eligible && <small className="dss-missing">Thiếu forecast, CV hoặc ASP</small>}</td><td>{dec(r.forecast)}</td><td>{dec(r.cv)}</td><td>{num(r.asp)}</td><td>{num(r.orderBaseline)}</td><td><b>{num(r.orderScenario)}</b></td><td>{signed(r.orderDelta)}</td><td>{num(r.revenueBaseline)}</td><td>{num(r.revenueScenario)}</td><td>{signed(r.revenueDelta)}</td></tr>)}</tbody></table></div>
      {!rows.length && <p className="dss-empty">Chọn ít nhất một hãng để xem kịch bản.</p>}
    </Card>
  </>;
}

function CasesView({ model, options, applyCase }) {
  const cases = reportCaseResults(model, options);
  const [comparisonCompany, setComparisonCompany] = useState(model.companies.includes('Chevrolet') ? 'Chevrolet' : model.companies[0]);
  const comparisons = forecastComparison(model, comparisonCompany);
  return <>
    <div className="tiles"><Metric label="Đạt với bộ lọc hiện tại" value={cases.filter((c) => c.status === 'PASS').length} note="PASS" tone="good" /><Metric label="Chưa chọn kịch bản" value={cases.filter((c) => c.status === 'N/A').length} note="Bấm Áp dụng để chọn đúng tham số" /><Metric label="Không đạt / thiếu dữ liệu" value={`${cases.filter((c) => c.status === 'FAIL').length} / ${cases.filter((c) => c.status === 'NO DATA').length}`} note="FAIL / NO DATA" /></div>
    <Card title="9 testcase theo mục 5.6.2 của báo cáo" note="Trạng thái tính trên dữ liệu hiện tại. Số quan sát trong PDF là tham chiếu tại thời điểm lập báo cáo.">
      <div className="scroll"><table className="dss-table dss-cases"><thead><tr><th>Mã</th><th>Testcase</th><th>Thiết lập</th><th>Kết quả</th><th>Thao tác</th></tr></thead><tbody>{cases.map((c) => <tr key={c.id}><td>{c.id}</td><td>{c.title}</td><td>{c.setupLabel}</td><td><Badge value={c.status} /></td><td><button onClick={() => applyCase(c.id)}>Áp dụng {c.id}</button></td></tr>)}</tbody></table></div>
    </Card>
    <Card title="TC-S6-05 · Đối chiếu bốn lựa chọn tháng / model">
      <label className="dss-inline-label">Hãng đối chiếu <select aria-label="Hãng đối chiếu testcase" value={comparisonCompany} onChange={(e) => setComparisonCompany(e.target.value)}>{model.companies.map((c) => <option key={c}>{c}</option>)}</select></label>
      <div className="scroll"><table className="dss-table"><thead><tr><th>Tháng</th><th>Model</th><th>Forecast hiện tại</th><th>Đối soát nguồn</th><th>Số trong báo cáo</th><th>Kết quả</th></tr></thead><tbody>{comparisons.map((r) => <tr key={`${r.month}-${r.modelName}`}><td>{monthName(r.month)}</td><td>{MODELS[r.modelName] || r.modelName}</td><td>{dec(r.actual)}</td><td>{dec(r.expected)}</td><td>{dec(r.reference)}</td><td><Badge value={r.actual == null || r.expected == null ? 'NO DATA' : Math.abs(r.actual - r.expected) <= 1e-6 ? 'PASS' : 'FAIL'} /></td></tr>)}</tbody></table></div>
      <p className="note">Bốn dòng lấy forecast cấp hãng, không backtest. Sau khi chạy lại dự báo, giá trị có thể khác snapshot trong PDF.</p>
    </Card>
    <details className="defs"><summary>Ý nghĩa trạng thái</summary><p>PASS: đạt điều kiện. FAIL: không đạt. N/A: chưa chọn đúng kịch bản. NO DATA: thiếu dữ liệu để kiểm tra. Đối chiếu doanh thu cho phép sai số 1 USD theo báo cáo; Growth, trọng số và forecast dùng dung sai 0,000001.</p></details>
  </>;
}

function DssPanel({ model, onReload, reloading }) {
  const defaults = () => ({ month: model.metadata.default_month || model.months[0], modelName: model.metadata.default_model || model.models[0], weights: [...DEFAULT_WEIGHTS], demandChange: 0, safetyFactor: 1, selectedCompanies: null });
  const [options, setOptions] = useState(defaults);
  const [mode, setMode] = useState('s5');
  const [message, setMessage] = useState('');
  useEffect(() => {
    setOptions((current) => ({ ...current,
      month: model.months.includes(current.month) ? current.month : model.metadata.default_month,
      modelName: model.models.includes(current.modelName) ? current.modelName : model.metadata.default_model,
      selectedCompanies: current.selectedCompanies?.filter((company) => model.companies.includes(company)) ?? null,
    }));
  }, [model]);
  const ranking = useMemo(() => rankCompanies(model, options), [model, options]);
  const ordering = useMemo(() => orderCompanies(model, options), [model, options]);
  function applyCase(id) {
    setOptions((s) => {
      const next = { ...s, selectedCompanies: null };
      if (id === 'TC-S5-01') { next.month = 202401; next.modelName = 'sarima'; if (model.companies.includes('Mercedes-B')) next.selectedCompanies = ['Mercedes-B']; }
      if (id === 'TC-S5-02') next.weights = [25, 25, 25, 25];
      if (id === 'TC-S5-03') next.weights = [50, 25, 25, 25];
      if (id === 'TC-S5-04') next.weights = [0, 0, 0, 0];
      if (id.startsWith('TC-S6-')) {
        const setup = model.metadata.cases.find((c) => c.id === id)?.setup || {};
        next.demandChange = setup.demand_change ?? 0;
        next.safetyFactor = setup.safety_factor ?? 1;
        if (id === 'TC-S6-05') { next.month = 202401; next.modelName = 'sarima'; if (model.companies.includes('Chevrolet')) next.selectedCompanies = ['Chevrolet']; }
      }
      return next;
    });
    setMessage(`Đã áp dụng ${id}. Các kết quả dùng bộ lọc hiện tại phía trên.`);
  }
  let exported = model.metadata.exported_at;
  if (exported && !Number.isNaN(Date.parse(exported))) exported = new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(exported));
  return <div className="dss-workspace">
    <section className="dss-intro"><div><span className="dss-eyebrow">HỖ TRỢ QUYẾT ĐỊNH</span><h2>DSS · Từ dự báo đến kế hoạch nhập xe</h2><p>Xếp hạng ưu tiên hãng xe và so sánh phương án nhập hàng theo cùng một kỳ dự báo.</p></div><div className="dss-source"><span>{model.metadata.source === 'PostgreSQL' ? 'Dữ liệu từ kho PostgreSQL' : 'Dữ liệu mẫu kèm dự án'}</span><small>Cập nhật: {exported || '—'}</small><button disabled={reloading} onClick={onReload}>{reloading ? 'Đang tải…' : 'Nạp lại dữ liệu'}</button></div></section>
    <div className="dss-controls card"><div className="dss-controls-row"><label>Tháng dự báo<select aria-label="Tháng dự báo DSS" value={options.month} onChange={(e) => setOptions((s) => ({ ...s, month: Number(e.target.value) }))}>{model.months.map((m) => <option value={m} key={m}>{monthName(m)}</option>)}</select></label><label>Mô hình<select aria-label="Mô hình DSS" value={options.modelName} onChange={(e) => setOptions((s) => ({ ...s, modelName: e.target.value }))}>{model.models.map((m) => <option value={m} key={m}>{MODELS[m] || m}</option>)}</select></label><button className="dss-reset" onClick={() => { setOptions(defaults()); setMessage('Đã đặt lại bộ lọc và tham số.'); }}>Đặt lại</button></div><CompanyPicker companies={model.companies} selected={options.selectedCompanies} onChange={(value) => setOptions((s) => ({ ...s, selectedCompanies: value }))} /></div>
    <nav className="dss-subnav" aria-label="Chức năng DSS">{[['s5', 'S5 · Xếp hạng ưu tiên'], ['s6', 'S6 · What-if & nhập xe'], ['cases', 'Testcase theo báo cáo']].map(([id, label]) => <button key={id} className={mode === id ? 'active' : ''} aria-pressed={mode === id} onClick={() => { setMode(id); setMessage(''); }}>{label}</button>)}</nav>
    {message && <p className="dss-callout" role="status">{message}</p>}
    {mode === 's5' ? <PriorityView result={ranking} options={options} setOptions={setOptions} /> : mode === 's6' ? <OrderingView rows={ordering} options={options} setOptions={setOptions} /> : <CasesView model={model} options={options} applyCase={applyCase} />}
  </div>;
}

export default function DssWorkspace({ data, onReload, reloading }) {
  const prepared = useMemo(() => {
    try { return { model: prepareDss(data.dss) }; }
    catch (error) { return { error: error.message }; }
  }, [data.dss]);
  if (prepared.error) return <Card title="Dữ liệu DSS chưa sẵn sàng"><p>{prepared.error}</p><p>Kiểm tra Terminal chạy <code>py -3 src/api.py</code> và dữ liệu forecast trong PostgreSQL.</p><button onClick={onReload}>Nạp lại dữ liệu</button></Card>;
  return <DssPanel model={prepared.model} onReload={onReload} reloading={reloading} />;
}
