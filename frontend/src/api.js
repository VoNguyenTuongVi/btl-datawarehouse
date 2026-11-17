const ARRAY_FIELDS = ['monthly', 'forecast', 'accuracy', 'company', 'region', 'annual', 'dq', 'model', 'dealer'];

export async function loadDashboard({ signal, fetcher = globalThis.fetch } = {}) {
  let response;
  try {
    response = await fetcher('/api/dashboard', { cache: 'no-store', signal });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new Error('Không kết nối được API. Mở Terminal tại gốc dự án và chạy py -3 src/api.py.');
  }
  let payload;
  try { payload = await response.json(); }
  catch { throw new Error('API chưa sẵn sàng. Kiểm tra Terminal chạy py -3 src/api.py.'); }
  if (!response.ok) throw new Error(payload.message || `Không tải được dữ liệu từ PostgreSQL (${response.status}).`);
  if (ARRAY_FIELDS.some((field) => !Array.isArray(payload[field])) || !payload.dss?.history || !payload.dss?.forecasts) {
    throw new Error('Dữ liệu API không đúng định dạng dashboard. Kiểm tra phiên bản backend.');
  }
  return payload;
}
