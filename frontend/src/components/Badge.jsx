const LABELS = {
  OBSERVED: "Observed",
  SOURCED: "Sourced",
  "EXECUTION-VERIFIED": "Execution-verified",
  "AI-RECOMMENDED": "AI-recommended",
  UNKNOWN: "Unknown",
};

export function Evidence({ type }) {
  const key = (type || "UNKNOWN").toUpperCase();
  return <span className={`badge ev-${key.toLowerCase()}`} title={key}>{LABELS[key] || key}</span>;
}

export function Band({ band, score }) {
  return <span className={`badge band-${band}`}>{band}{score !== undefined ? ` · ${score}` : ""}</span>;
}

export function Status({ value }) {
  const tone = /ok|passed|completed|no_regressions_observed|exists|fixed|consistent/.test(value || "") ? "good"
    : /fail|error|regression|rejected|could_not|INVALID|contradicted/i.test(value || "") ? "bad"
    : /UNAVAILABLE|running|proposed|still_failing|remain/i.test(value || "") ? "warn" : "neutral";
  return <span className={`badge tone-${tone}`}>{value || "—"}</span>;
}
