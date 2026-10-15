"""Optional PyPI JSON metadata provider.

Network calls are opt-in. Callers must confirm network access is allowed by event rules.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def get_package_metadata(package_name: str, *, allow_network: bool = False, timeout: float = 4.0) -> dict:
    if not allow_network:
        return {
            "package": package_name,
            "status": "not_fetched",
            "source": None,
            "retrieved_at": None,
            "reason": "Network access is disabled unless explicitly enabled by the caller.",
        }
    url = f"https://pypi.org/pypi/{package_name}/json"
    request = Request(url, headers={"User-Agent": "GhostLib/0.1 dependency-resilience-prototype"})
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        info = data.get("info", {})
        releases = data.get("releases", {})
        release_dates = [
            file.get("upload_time_iso_8601")
            for files in releases.values() for file in files
            if file.get("upload_time_iso_8601")
        ]
        return {
            "package": info.get("name", package_name),
            "status": "fetched",
            "source": url,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "latest_version": info.get("version"),
            "requires_python": info.get("requires_python"),
            "summary": info.get("summary"),
            "project_urls": info.get("project_urls") or {},
            "release_count": len(releases),
            "last_release_upload": max(release_dates) if release_dates else None,
            "license_expression": info.get("license_expression"),
            "license": info.get("license"),
        }
    except HTTPError as exc:
        return {"package": package_name, "status": "http_error", "source": url,
                "retrieved_at": datetime.now(timezone.utc).isoformat(), "reason": f"HTTP {exc.code}"}
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        return {"package": package_name, "status": "fetch_error", "source": url,
                "retrieved_at": datetime.now(timezone.utc).isoformat(), "reason": str(exc)}
