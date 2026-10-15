export default function Panel({ title, eyebrow, children, className = "" }) {
  return <section className={`panel ${className}`}><div className="panel-heading"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h2>{title}</h2></div></div>{children}</section>;
}
