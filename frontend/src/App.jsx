import { useEffect, useMemo, useState } from 'react';
import Card from './components/Card.jsx';
import Kpis from './components/Kpis.jsx';
import TrendChart from './components/TrendChart.jsx';
import ForecastChart from './components/ForecastChart.jsx';
import PlanTable from './components/PlanTable.jsx';
import BarsChart from './components/BarsChart.jsx';
import DealerTable from './components/DealerTable.jsx';
import DqTable from './components/DqTable.jsx';
import ModelCompareTab from './components/ModelCompareTab.jsx';
import { BIAS_MAX, WAPE_MAX, num, pct, poolAccuracy } from './format.js';

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState('overview');

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`Không tải được data.json (${r.status})`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  const pooled = useMemo(() => (data ? poolAccuracy(data.accuracy) : []), [data]);

  if (error) {
    return (
      <main className="page">
        <p className="bad">{error}. Chạy <code>python src/export_frontend_data.py</code> để tạo lại.</p>
      </main>
    );
  }
  if (!data) return <main className="page"><p className="note">Đang tải dữ liệu…</p></main>;

  const y23 = data.annual.find((r) => r.year === 2023);
  const tot = pooled.find((r) => r.level === 'total' && r.model === 'sarima');
  const anyCompany = pooled.some((r) => r.level === 'company' && r.wape <= WAPE_MAX && Math.abs(r.bias) <= BIAS_MAX);

  return (
    <main className="page">
      <header>
        <h1>Dự báo nhu cầu</h1>
      </header>

      <nav className="tabs">
        <button className={tab === 'overview' ? 'on' : ''} onClick={() => setTab('overview')}>Tổng quan</button>
        <button className={tab === 'ranking' ? 'on' : ''} onClick={() => setTab('ranking')}>Xếp hạng</button>
        <button className={tab === 'models' ? 'on' : ''} onClick={() => setTab('models')}>So sánh hiệu suất mô hình</button>
      </nav>

      {tab === 'ranking' ? (
        <>
      <div className="grid">
        <Card title="Top 10 hãng theo sản lượng 2023" >
          <BarsChart rows={data.company.slice(0, 10)} />
        </Card>
        <Card title="Sản lượng 2023 theo vùng" >
          <BarsChart rows={data.region} />
        </Card>
      </div>

      <Card title="Top 50 dòng xe theo doanh thu 2023" >
        <BarsChart rows={data.model} labelWidth={190} valueKey="revenue" yoyKey="revenue_yoy_pct" shareKey="revenue_share_pct" tip="USD" />
      </Card>

      <Card title="Top 10 dealer có doanh thu cao nhất 2023" >
        <DealerTable rows={data.dealer} />
      </Card>
        </>
      ) : tab === 'models' ? <ModelCompareTab forecast={data.forecast} pooled={pooled} /> : (<>
      <Kpis annual={data.annual} pooled={pooled} dq={data.dq} />

      <div className="grid">
        <Card title="Sản lượng theo tháng của các năm">
          <TrendChart monthly={data.monthly} />
        </Card>
        <Card title="Thực tế và dự báo SARIMA, cấp tổng" >
          <ForecastChart forecast={data.forecast} />
        </Card>
      </div>

      <Card title="Dự báo 6 tháng đầu 2024 (SARIMA, cấp tổng)" >
        <PlanTable forecast={data.forecast} />
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
