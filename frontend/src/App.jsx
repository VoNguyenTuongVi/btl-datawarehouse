import { useEffect, useMemo, useState } from 'react';
import Card from './components/Card.jsx';
import Kpis from './components/Kpis.jsx';
import TrendChart from './components/TrendChart.jsx';
import ForecastChart from './components/ForecastChart.jsx';
import PlanTable from './components/PlanTable.jsx';
import ModelsTable from './components/ModelsTable.jsx';
import BarsChart from './components/BarsChart.jsx';
import DqTable from './components/DqTable.jsx';
import { BIAS_MAX, WAPE_MAX, num, pct, poolAccuracy } from './format.js';

export default function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

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
        <h1>Dự báo nhu cầu xe: Car Sales 2022–2023</h1>
        <p className="lead">
          Nhu cầu 2023 tăng {pct(y23.units_yoy_pct)} so với 2022 ({num(y23.units)} xe) và vượt mục tiêu +5%. Ở cấp tổng, SARIMA dự báo sai {pct(tot.wape)} (đạt ngưỡng {pct(WAPE_MAX)});{' '}
          {anyCompany ? 'ở cấp hãng có mô hình đạt ngưỡng.' : 'ở cấp hãng chưa mô hình nào đạt ngưỡng vì dữ liệu mỗi hãng quá thưa.'}
        </p>
        <p className="note">Dữ liệu xuất từ PostgreSQL (schema mart) lúc {String(data.exported_at).replace('T', ' ')}</p>
      </header>

      <Kpis annual={data.annual} pooled={pooled} dq={data.dq} />

      <div className="grid">
        <Card title="Sản lượng theo tháng: 2023 cao hơn 2022 ở hầu hết các tháng" note="Số xe bán mỗi tháng. Quý IV là cao điểm, tháng 1–2 thấp nhất.">
          <TrendChart monthly={data.monthly} />
        </Card>
        <Card title="Thực tế và dự báo SARIMA, cấp tổng" note="Chấm là dự báo, râu là khoảng 80%. Vùng xám đậm là 01–06/2024, vùng xám nhạt là backtest 07–12/2023.">
          <ForecastChart forecast={data.forecast} />
        </Card>
      </div>

      <Card title="Dự báo 6 tháng đầu 2024 (SARIMA, cấp tổng)" note="Cận dưới chạm 0 ở nhiều tháng: 24 tháng dữ liệu chưa đủ để thu hẹp khoảng bất định. Dùng như mức kỳ vọng kèm đệm.">
        <PlanTable forecast={data.forecast} />
      </Card>

      <Card title="Mô hình nào đáng tin? So sánh trên backtest 07–12/2023" note={`Đạt khi WAPE ≤ ${pct(WAPE_MAX)} và |Bias| ≤ ${pct(BIAS_MAX)}. Chuỗi đạt là số chuỗi đạt cả hai điều kiện trên tổng số chuỗi của cấp đó.`}>
        <ModelsTable pooled={pooled} />
      </Card>

      <div className="grid">
        <Card title="Top 10 hãng theo sản lượng 2023" note="Nhãn bên phải: số xe và tăng trưởng so với 2022.">
          <BarsChart rows={data.company.slice(0, 10)} />
        </Card>
        <Card title="Sản lượng 2023 theo vùng" note="Nhãn bên phải: số xe và tăng trưởng so với 2022.">
          <BarsChart rows={data.region} />
        </Card>
      </div>

      <Card title="Chất lượng Data Warehouse">
        <DqTable dq={data.dq} />
      </Card>

      <details className="defs">
        <summary>Định nghĩa các chỉ số</summary>
        <p><b>WAPE</b>: tổng sai lệch tuyệt đối chia tổng số xe thực tế; 20% nghĩa là cứ 5 xe thì lệch trung bình 1 xe.</p>
        <p><b>Bias</b>: tổng (dự báo trừ thực tế) chia tổng thực tế; dương là dự báo dư, âm là dự báo thiếu.</p>
        <p><b>Độ phủ 80%</b>: tỷ lệ tháng có số thực tế nằm trong khoảng dự báo 80%.</p>
        <p>Nhu cầu là số xe đã bán, không tính nhu cầu bị mất do hết hàng. Dữ liệu tĩnh 01/2022–12/2023. Mục tiêu +5% và ngưỡng 20% / 5% do nhóm đề xuất.</p>
      </details>
    </main>
  );
}
