import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Card from './components/Card.jsx';
import Kpis from './components/Kpis.jsx';
import TrendChart from './components/TrendChart.jsx';
import ForecastChart from './components/ForecastChart.jsx';
import PlanTable from './components/PlanTable.jsx';
import BarsChart from './components/BarsChart.jsx';
import DealerTable from './components/DealerTable.jsx';
import DqTable from './components/DqTable.jsx';
import ModelCompareTab from './components/ModelCompareTab.jsx';
import DssWorkspace from './components/DssWorkspace.jsx';
import { MODELS, monthLabel, poolAccuracy } from './format.js';
import { loadDashboard } from './api.js';

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState('overview');
  const [reloading, setReloading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const pending = useRef(null);

  const loadData = useCallback(() => {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setReloading(true);
    const timeout = setTimeout(() => controller.abort(), 60000);
    return loadDashboard({ signal: controller.signal })
      .then((payload) => {
        if (pending.current !== controller) return;
        setData(payload);
        setError(null);
      })
      .catch((e) => {
        if (pending.current === controller) setError(controller.signal.aborted ? 'API phản hồi quá lâu. Thử tải lại và kiểm tra PostgreSQL.' : e.message);
      })
      .finally(() => {
        clearTimeout(timeout);
        if (pending.current === controller) { pending.current = null; setReloading(false); }
      });
  }, []);
  useEffect(() => {
    loadData();
    return () => { const controller = pending.current; pending.current = null; controller?.abort(); };
  }, [loadData]);
  useEffect(() => {
    if (!autoRefresh) return undefined;
    const refresh = () => { if (!document.hidden && !pending.current) loadData(); };
    const timer = setInterval(refresh, 30000);
    document.addEventListener('visibilitychange', refresh);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, [autoRefresh, loadData]);

  const pooled = useMemo(() => (data ? poolAccuracy(data.accuracy, data.parameters) : []), [data]);

  if (error && !data) {
    return (
      <main className="page">
        <h1>Chưa tải được dữ liệu từ PostgreSQL</h1>
        <p className="bad" role="alert">{error}</p>
        <p>Kiểm tra <code>DATABASE_URL</code> trong <code>.env</code> và giữ Terminal <code>py -3 src/api.py</code> đang chạy.</p>
        <button disabled={reloading} onClick={loadData}>{reloading ? 'Đang tải…' : 'Thử tải lại'}</button>
      </main>
    );
  }
  if (!data) return <main className="page"><p className="note">Đang tải dữ liệu…</p></main>;
  const year = data.latest_year ?? Math.max(...data.annual.map((row) => row.year));
  const mainModel = data.parameters?.main_model || data.dss.default_model;
  const modelName = MODELS[mainModel] || mainModel;
  const future = data.forecast.filter((row) => row.model_name === mainModel && row.series_type === 'Dự báo');
  const period = future.length ? `${monthLabel(future[0].month)} – ${monthLabel(future.at(-1).month)}` : 'chưa có kỳ dự báo';
  const loadedAt = new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'medium' }).format(new Date(data.exported_at));

  return (
    <main className="page">
      <header>
        <h1>Dự báo nhu cầu</h1>
      </header>
      <section className="data-status" aria-label="Nguồn dữ liệu">
        <div><strong>PostgreSQL</strong><p className="note">{error ? 'Lần tải thành công gần nhất' : 'Đọc DB lúc'}: {loadedAt}</p></div>
        <label><input type="checkbox" checked={autoRefresh} onChange={(event) => setAutoRefresh(event.target.checked)} /> Tự cập nhật mỗi 30 giây</label>
        <button disabled={reloading} onClick={loadData}>{reloading ? 'Đang đọc DB…' : 'Nạp lại dữ liệu'}</button>
      </section>
      {error && <p className="refresh-error" role="alert">{error} Đang hiển thị dữ liệu từ lần tải thành công gần nhất.</p>}

      <nav className="tabs">
        <button className={tab === 'overview' ? 'on' : ''} onClick={() => setTab('overview')}>Tổng quan</button>
        <button className={tab === 'ranking' ? 'on' : ''} onClick={() => setTab('ranking')}>Xếp hạng</button>
        <button className={tab === 'models' ? 'on' : ''} onClick={() => setTab('models')}>So sánh hiệu suất mô hình</button>
        <button className={tab === 'dss' ? 'on' : ''} onClick={() => setTab('dss')}>DSS</button>
      </nav>

      {tab === 'dss' ? <DssWorkspace data={data} onReload={loadData} reloading={reloading} /> : tab === 'ranking' ? (
        <>
      <div className="grid">
        <Card title={`Top 10 hãng theo sản lượng ${year}`} >
          <BarsChart rows={data.company.slice(0, 10)} />
        </Card>
        <Card title={`Sản lượng ${year} theo vùng`} >
          <BarsChart rows={data.region} />
        </Card>
      </div>

      <Card title={`Top 50 dòng xe theo doanh thu ${year}`} >
        <BarsChart rows={data.model} labelWidth={190} valueKey="revenue" yoyKey="revenue_yoy_pct" shareKey="revenue_share_pct" tip="USD" />
      </Card>

      <Card title={`Top 10 dealer có doanh thu cao nhất ${year}`} >
        <DealerTable rows={data.dealer} />
      </Card>
        </>
      ) : tab === 'models' ? <ModelCompareTab forecast={data.forecast} pooled={pooled} /> : (<>
      <Kpis annual={data.annual} pooled={pooled} dq={data.dq} parameters={data.parameters} mainModel={mainModel} forecast={data.forecast} />

      <div className="grid">
        <Card title="Sản lượng theo tháng của các năm">
          <TrendChart monthly={data.monthly} />
        </Card>
        <Card title={`Thực tế và dự báo ${modelName}, cấp tổng`} >
          <ForecastChart forecast={data.forecast} model={mainModel} />
        </Card>
      </div>

      <Card title={`Dự báo ${period} (${modelName}, cấp tổng)`} >
        <PlanTable forecast={data.forecast} model={mainModel} />
      </Card>


      <Card title="Chất lượng Data Warehouse">
        <DqTable dq={data.dq} />
      </Card>

      <details className="defs">
        <summary>Định nghĩa các chỉ số</summary>
        <p><b>WAPE</b>: tổng sai lệch tuyệt đối chia tổng số xe thực tế; 20% nghĩa là cứ 5 xe thì lệch trung bình 1 xe.</p>
        <p><b>Bias</b>: tổng (dự báo trừ thực tế) chia tổng thực tế; dương là dự báo dư, âm là dự báo thiếu.</p>
        <p>Nhu cầu chỉ dựa trên số xe đã bán, chưa xét đến phần ảnh hưởng do các yếu tố khách quan khác.</p>
      </details>
      </>)}
    </main>
  );
}
