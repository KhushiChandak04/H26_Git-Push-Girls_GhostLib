export default function Stat({ label, value, detail }) {
  return <div className="stat"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>;
}
