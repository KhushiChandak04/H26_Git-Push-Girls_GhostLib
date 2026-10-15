"""PyPI JSON metadata provider (SOURCED evidence).

Every record carries its source URL, retrieval time and fetch status. Responses are
cached on disk under ``artifacts/cache/pypi`` for 24 hours to keep scans fast and
reproducible; the cache file path is recorded in the result.
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.config import ARTIFACTS_DIR

CACHE_TTL_SECONDS = 24 * 3600
USER_AGENT = "GhostLib/0.2 dependency-resilience (hackathon prototype)"


def _cache_dir() -> Path:
    path = Path(ARTIFACTS_DIR) / "cache" / "pypi"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _fetch_json(url: str, timeout: float) -> tuple[dict | None, dict]:
    """Return (data, fetch_info). Uses the disk cache when fresh."""
    key = re.sub(r"[^A-Za-z0-9._-]+", "_", url.removeprefix("https://pypi.org/pypi/"))
    cache_file = _cache_dir() / f"{key}.json"
    if cache_file.is_file() and time.time() - cache_file.stat().st_mtime < CACHE_TTL_SECONDS:
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            return cached["data"], {"status": "fetched", "source": url, "retrieved_at": cached["retrieved_at"],
                                    "cache": "hit"}
        except (ValueError, KeyError, OSError):
            pass
    retrieved_at = datetime.now(timezone.utc).isoformat()
    try:
        with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        status = "not_found" if exc.code == 404 else "http_error"
        return None, {"status": status, "source": url, "retrieved_at": retrieved_at, "reason": f"HTTP {exc.code}"}
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        return None, {"status": "fetch_error", "source": url, "retrieved_at": retrieved_at, "reason": str(exc)}
    try:
        cache_file.write_text(json.dumps({"retrieved_at": retrieved_at, "data": data}), encoding="utf-8")
    except OSError:
        pass
    return data, {"status": "fetched", "source": url, "retrieved_at": retrieved_at, "cache": "miss"}


def _python_classifiers(classifiers: list[str]) -> list[str]:
    out = []
    for c in classifiers or []:
        m = re.match(r"Programming Language :: Python :: (3\.\d+)$", c)
        if m:
            out.append(m.group(1))
    return sorted(set(out), key=lambda v: tuple(int(x) for x in v.split(".")))


def _upload_time(files: list[dict]) -> str | None:
    times = [f.get("upload_time_iso_8601") for f in files or [] if f.get("upload_time_iso_8601")]
    return min(times) if times else None


def installability(files: list[dict], targets=("3.12", "3.13")) -> dict:
    """Can the pinned release be installed on each target Python? Read from the real wheel tags.

    "wheel" = a compatible pre-built wheel exists; "source_build" = only an sdist (may need compilers);
    "none" = nothing installable (common for old ML releases such as tensorflow 2.10 on Python 3.12).
    """
    wheels = [f.get("filename", "") for f in files if f.get("packagetype") == "bdist_wheel"]
    has_sdist = any(f.get("packagetype") == "sdist" for f in files)
    out = {}
    for t in targets:
        minor = int(t.split(".")[1])
        ok = False
        for name in wheels:
            parts = name[:-4].split("-")
            if len(parts) < 5:
                continue
            py_tags, abi_tags = parts[-3].split("."), parts[-2].split(".")
            for tag in py_tags:
                if tag in ("py3", "py2.py3") or tag == f"cp3{minor}" or tag == f"py3{minor}":
                    ok = True
                elif tag.startswith("cp3") and "abi3" in abi_tags and tag[3:].isdigit() and int(tag[3:]) <= minor:
                    ok = True
        out[t] = "wheel" if ok else ("source_build" if has_sdist else "none")
    return out


def get_package_metadata(package_name: str, *, pinned_version: str | None = None,
                         allow_network: bool = True, timeout: float = 8.0) -> dict:
    if not allow_network:
        return {"package": package_name, "status": "not_fetched", "source": None, "retrieved_at": None,
                "reason": "Network access disabled by caller."}
    url = f"https://pypi.org/pypi/{quote(package_name)}/json"
    data, fetch = _fetch_json(url, timeout)
    if data is None:
        return {"package": package_name, **fetch}
    info = data.get("info", {}) or {}
    releases = data.get("releases", {}) or {}
    release_times = {v: _upload_time(files) for v, files in releases.items()}
    dated = sorted((t, v) for v, t in release_times.items() if t)
    classifiers = info.get("classifiers") or []
    result = {
        "package": info.get("name", package_name),
        **fetch,
        "evidence_type": "SOURCED",
        "latest_version": info.get("version"),
        "latest_release_date": release_times.get(info.get("version")),
        "most_recent_upload": dated[-1][0] if dated else None,
        "first_release_date": dated[0][0] if dated else None,
        "release_count": len(releases),
        "requires_python": info.get("requires_python"),
        "python_classifiers": _python_classifiers(classifiers),
        "development_status": next((c.split("::")[-1].strip() for c in classifiers
                                    if c.startswith("Development Status")), None),
        "summary": info.get("summary"),
        "home_page": info.get("home_page"),
        "project_urls": info.get("project_urls") or {},
        "license": info.get("license_expression") or (info.get("license") or "")[:120] or None,
        "yanked_latest": bool(info.get("yanked")),
    }
    if pinned_version:
        files = releases.get(pinned_version)
        if files is None:
            result["pinned"] = {"version": pinned_version, "exists_on_pypi": False}
        else:
            vurl = f"https://pypi.org/pypi/{quote(package_name)}/{quote(pinned_version)}/json"
            vdata, vfetch = _fetch_json(vurl, timeout)
            vinfo = (vdata or {}).get("info", {}) or {}
            result["pinned"] = {
                "version": pinned_version,
                "exists_on_pypi": True,
                "release_date": release_times.get(pinned_version),
                "yanked": any(f.get("yanked") for f in files) if files else None,
                "requires_python": vinfo.get("requires_python"),
                "python_classifiers": _python_classifiers(vinfo.get("classifiers") or []),
                "has_wheels": any(f.get("packagetype") == "bdist_wheel" for f in files),
                "installable": installability(files),
                "source": vurl if vdata else None,
                "fetch_status": vfetch["status"],
            }
    return result


def fetch_all(packages: list[dict], *, allow_network: bool = True) -> dict[str, dict]:
    """Fetch metadata for scanner ``packages`` concurrently, keyed by normalized name."""
    def job(pkg):
        pinned = pkg.get("pinned_versions") or []
        return pkg["normalized_name"], get_package_metadata(
            pkg["normalized_name"], pinned_version=pinned[0] if pinned else None, allow_network=allow_network)
    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(pool.map(job, packages))
