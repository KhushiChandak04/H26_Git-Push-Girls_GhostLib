"""Known-vulnerability advisories from OSV.dev (SOURCED, informational).

Deliberately separate from the rule-based resilience score: an outdated package is not
necessarily vulnerable, and a vulnerability is not a maintenance signal. Only exactly pinned
versions (==x.y.z) are checked, because a range cannot be matched honestly. When OSV cannot be
reached the status says so; nothing is inferred or invented.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

OSV_QUERY = "https://api.osv.dev/v1/querybatch"
OSV_VULN = "https://api.osv.dev/v1/vulns/{}"
TIMEOUT = 10


def _post(url: str, body: dict) -> dict:
    req = Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
                  headers={"Content-Type": "application/json", "User-Agent": "GhostLib/0.2"})
    with urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(url: str) -> dict:
    with urlopen(Request(url, headers={"User-Agent": "GhostLib/0.2"}), timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _is_version(v: str) -> bool:
    from packaging.version import InvalidVersion, Version
    try:
        Version(v)
        return True
    except InvalidVersion:
        return False


def unique_issue_count(vulns: list[dict]) -> int:
    """OSV lists one CVE under several IDs (GHSA, PYSEC); count connected alias groups."""
    groups: list[set[str]] = []
    for v in vulns:
        ids = {v["id"], *v.get("aliases", [])}
        merged = [g for g in groups if g & ids]
        for g in merged:
            groups.remove(g)
            ids |= g
        groups.append(ids)
    return len(groups)


def resolved_by(record: dict, version: str | None) -> dict | None:
    """Which advisories a candidate version is past the fix for (version comparison, SOURCED data)."""
    from packaging.version import InvalidVersion, Version
    if not record or record.get("status") != "checked" or not version:
        return None
    try:
        cand = Version(version)
    except InvalidVersion:
        return None
    fixed, open_ = [], []
    for v in record.get("vulnerabilities", []):
        fixes = [Version(f) for f in v.get("fixed_in", []) if _is_version(f)]
        (fixed if fixes and any(cand >= f for f in fixes) else open_).append(v["id"])
    return {"candidate_version": version, "resolved": fixed, "not_resolved": open_,
            "note": "By comparing the candidate version with OSV 'fixed' versions; not a security test."}


def _fixed_versions(vuln: dict, package: str) -> list[str]:
    out = set()
    for aff in vuln.get("affected", []):
        if (aff.get("package") or {}).get("name", "").lower() != package.lower():
            continue
        for rng in aff.get("ranges", []):
            for ev in rng.get("events", []):
                if ev.get("fixed") and _is_version(ev["fixed"]):
                    out.add(ev["fixed"])
    return sorted(out)


def check(packages: list[dict], *, post=_post, get=_get) -> dict[str, dict]:
    """Return {normalized_name: advisory record} for every package."""
    now = datetime.now(timezone.utc).isoformat()
    results: dict[str, dict] = {}
    queries, names = [], []
    for pkg in packages:
        name = pkg["normalized_name"]
        pins = pkg.get("pinned_versions") or []
        if not pins:
            results[name] = {"status": "not_checked", "evidence_type": "UNKNOWN",
                             "reason": "No exact version is pinned, so advisories cannot be matched to a version."}
            continue
        queries.append({"package": {"name": name, "ecosystem": "PyPI"}, "version": pins[0]})
        names.append((name, pins[0]))
    if not queries:
        return results
    try:
        batch = post(OSV_QUERY, {"queries": queries})
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        for name, ver in names:
            results[name] = {"status": "unavailable", "evidence_type": "UNKNOWN", "version": ver, "source": OSV_QUERY,
                             "reason": f"OSV.dev could not be reached ({exc}). Vulnerability status unknown."}
        return results

    def details(vid: str) -> dict:
        try:
            return get(OSV_VULN.format(quote(vid)))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            return {"id": vid}

    ids = sorted({v["id"] for res in batch.get("results", []) for v in res.get("vulns", []) or []})
    with ThreadPoolExecutor(max_workers=6) as pool:
        info = dict(zip(ids, pool.map(details, ids)))
    for (name, ver), res in zip(names, batch.get("results", [])):
        vulns = []
        for v in res.get("vulns", []) or []:
            d = info.get(v["id"], {"id": v["id"]})
            vulns.append({
                "id": v["id"],
                "aliases": d.get("aliases", []),
                "summary": (d.get("summary") or (d.get("details") or "")[:200]) or None,
                "published": d.get("published"),
                "fixed_in": _fixed_versions(d, name),
                "url": f"https://osv.dev/vulnerability/{v['id']}",
            })
        results[name] = {"status": "checked", "evidence_type": "SOURCED", "version": ver, "source": OSV_QUERY,
                         "retrieved_at": now, "count": len(vulns), "unique_issues": unique_issue_count(vulns),
                         "vulnerabilities": vulns,
                         "note": "Informational; not part of the risk score."}
    return results
