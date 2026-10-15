"""Deterministic Python dependency scanner.

Supported inputs: requirements*.txt and pyproject.toml (PEP 621 + Poetry).
This module reads repository files only; it does not execute repository code.
"""
from __future__ import annotations

import ast
import hashlib
import re
import tomllib
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__", "dist",
    "build", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
IMPORT_ALIASES = {
    "pillow": "PIL",
    "pyyaml": "yaml",
    "beautifulsoup4": "bs4",
    "scikit-learn": "sklearn",
    "opencv-python": "cv2",
    "opencv-python-headless": "cv2",
    "python-dateutil": "dateutil",
    "attrs": "attr",
    "beautifulsoup": "bs4",
    "python-dotenv": "dotenv",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_requirement(raw: str, relative_source: str, line_number: int | None = None,
                       group: str | None = None) -> dict | None:
    value = raw.strip()
    if not value or value.startswith("#"):
        return None
    # Handle ordinary inline comments while not trying to parse URL fragments perfectly.
    if " #" in value:
        value = value.split(" #", 1)[0].strip()
    try:
        req = Requirement(value)
        name = canonicalize_name(req.name)
        return {
            "name": req.name,
            "normalized_name": name,
            "specifier": str(req.specifier),
            "extras": sorted(req.extras),
            "markers": str(req.marker) if req.marker else None,
            "source": relative_source,
            "line": line_number,
            "group": group,
            "raw": raw.strip(),
            "parse_status": "parsed",
        }
    except Exception as exc:
        # Preserve rather than silently discard editable/VCS/path/directive entries.
        return {
            "name": value,
            "normalized_name": None,
            "specifier": "",
            "extras": [],
            "markers": None,
            "source": relative_source,
            "line": line_number,
            "group": group,
            "raw": raw.strip(),
            "parse_status": "unparsed",
            "parse_error": str(exc),
        }


def _read_requirements(path: Path, root: Path) -> list[dict]:
    result = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return [{"name": path.name, "source": str(path.relative_to(root)),
                 "parse_status": "error", "parse_error": str(exc)}]
    for number, line in enumerate(lines, start=1):
        item = _parse_requirement(line, path.relative_to(root).as_posix(), number)
        if item:
            result.append(item)
    return result


def _read_pyproject(path: Path, root: Path) -> tuple[list[dict], list[str]]:
    deps: list[dict] = []
    warnings: list[str] = []
    rel = path.relative_to(root).as_posix()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [], [f"{rel}: could not parse TOML: {exc}"]

    project = data.get("project", {})
    for raw in project.get("dependencies", []) or []:
        item = _parse_requirement(raw, rel, group="project")
        if item:
            deps.append(item)
    for group, values in (project.get("optional-dependencies", {}) or {}).items():
        for raw in values or []:
            item = _parse_requirement(raw, rel, group=f"optional:{group}")
            if item:
                deps.append(item)

    poetry = data.get("tool", {}).get("poetry", {})
    for package, spec in (poetry.get("dependencies", {}) or {}).items():
        if package.lower() == "python":
            continue
        if isinstance(spec, str):
            raw = package + spec if spec.startswith(("=", "<", ">", "!", "~")) else f"{package} {spec}".strip()
        elif isinstance(spec, dict):
            version = spec.get("version", "")
            raw = package + version if isinstance(version, str) and version.startswith(("=", "<", ">", "!", "~")) else f"{package} {version}".strip()
        else:
            raw = package
        item = _parse_requirement(raw, rel, group="poetry")
        if item:
            deps.append(item)

    for group, config in (poetry.get("group", {}) or {}).items():
        for package, spec in (config.get("dependencies", {}) or {}).items():
            if package.lower() == "python":
                continue
            version = spec if isinstance(spec, str) else (spec or {}).get("version", "")
            raw = package + version if isinstance(version, str) and version.startswith(("=", "<", ">", "!", "~")) else f"{package} {version}".strip()
            item = _parse_requirement(raw, rel, group=f"poetry-group:{group}")
            if item:
                deps.append(item)
    return deps, warnings


def _python_requirement(root: Path) -> str | None:
    path = root / "pyproject.toml"
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        return (data.get("project", {}).get("requires-python")
                or data.get("tool", {}).get("poetry", {}).get("dependencies", {}).get("python"))
    except Exception:
        return None


def _source_files(root: Path):
    for path in root.rglob("*.py"):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        try:
            if path.stat().st_size > 1_000_000:
                continue
        except OSError:
            continue
        yield path, rel.as_posix()


def map_import_usage(root: Path, dependencies: list[dict]) -> list[dict]:
    """Map top-level imports to declared packages; best-effort and intentionally conservative."""
    package_imports = {}
    for dep in dependencies:
        normalized = dep.get("normalized_name")
        if not normalized:
            continue
        package_imports.setdefault(normalized, IMPORT_ALIASES.get(normalized, normalized.replace("-", "_")))

    found = {package: [] for package in package_imports}
    parse_errors = []
    for path, relative in _source_files(root):
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=relative)
        except (OSError, SyntaxError, UnicodeError) as exc:
            parse_errors.append({"file": relative, "error": str(exc)})
            continue
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        for package, import_name in package_imports.items():
            if import_name in imported:
                found[package].append(relative)

    return [
        {
            "package": package,
            "import_name": package_imports[package],
            "files": sorted(set(files)),
            "status": "observed" if files else "not_observed_static",
            "confidence": "static-best-effort",
        }
        for package, files in sorted(found.items())
    ]


def scan_repository(repository: str | Path) -> dict:
    root = Path(repository).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    dependencies: list[dict] = []
    manifests: list[dict] = []
    warnings: list[str] = []
    for path in sorted(root.glob("requirements*.txt")):
        if path.is_file():
            manifests.append({
                "path": path.relative_to(root).as_posix(),
                "sha256": _sha256(path),
                "type": "requirements",
            })
            dependencies.extend(_read_requirements(path, root))

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        manifests.append({
            "path": "pyproject.toml",
            "sha256": _sha256(pyproject),
            "type": "pyproject",
        })
        parsed, parse_warnings = _read_pyproject(pyproject, root)
        dependencies.extend(parsed)
        warnings.extend(parse_warnings)

    # Deduplicate identical declarations without losing distinct source locations/groups.
    unique = []
    seen = set()
    for dep in dependencies:
        key = (dep.get("normalized_name"), dep.get("specifier"), dep.get("source"),
               dep.get("line"), dep.get("group"), dep.get("raw"))
        if key not in seen:
            unique.append(dep)
            seen.add(key)

    usage = map_import_usage(root, unique)
    usage_by_package = {item["package"]: item for item in usage}
    for dep in unique:
        dep["usage"] = usage_by_package.get(dep.get("normalized_name"))
        dep["evidence"] = {
            "manifest": dep.get("source"),
            "line": dep.get("line"),
            "raw_declaration": dep.get("raw"),
        }

    return {
        "schema_version": "0.2",
        "repository": str(root),
        "python_requirement": _python_requirement(root),
        "manifests": manifests,
        "dependencies": unique,
        "usage": usage,
        "warnings": warnings,
        "limitations": [
            "Only requirements*.txt and pyproject.toml are parsed in this starter.",
            "Nested -r includes, constraints files, setup.py/setup.cfg, lockfiles and dynamic dependencies are not resolved.",
            "Static imports can miss dynamic/plugin use and can report no observed import even when a dependency is used indirectly.",
            "Package names and import names are not always the same; alias mapping is incomplete.",
            "No transitive dependency graph or package-release metadata is collected by this local scanner.",
            "This is not a vulnerability scanner and does not establish package safety.",
        ],
    }
