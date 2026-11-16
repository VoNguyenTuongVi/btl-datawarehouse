export default function DqTable({ dq }) {
  return (
    <div className="scroll">
      <table>
        <thead>
          <tr><th>Mã</th><th>Kiểm tra</th><th>Kết quả</th><th>Trạng thái</th></tr>
        </thead>
        <tbody>
          {dq.map((r) => (
            <tr key={r.check_code}>
              <td>{r.check_code}</td>
              <td>{r.check_name}</td>
              <td>{r.detail}</td>
              <td><span className={`pill ${r.passed ? 'good' : 'bad'}`}>{r.passed ? 'Đạt' : 'Không đạt'}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
