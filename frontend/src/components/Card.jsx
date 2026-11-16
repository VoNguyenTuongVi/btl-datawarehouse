export default function Card({ title, note, children }) {
  return (
    <section className="card">
      <h2>{title}</h2>
      {children}
      {note && <p className="note">{note}</p>}
    </section>
  );
}
