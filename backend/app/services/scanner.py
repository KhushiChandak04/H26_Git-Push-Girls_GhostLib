"""Deterministic Python dependency scanner.

Supported inputs: requirements*.txt (recursive) and pyproject.toml (PEP 621 + Poetry).
This module reads repository files only; it never executes repository code.
Every finding carries the file/line it was observed at.
"""
from __future__ import annotations

import ast
import hashlib
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

SKIP_DIRS = {
    ".git", ".venv", "venv", "env", ".env", "node_modules", "__pycache__", "dist",
    "build", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".nox",
    "site-packages", ".eggs", "htmlcov",
}
MAX_SOURCE_BYTES = 1_000_000

# Distribution name -> import names. Used only when the names differ; every mapping
# that falls back to the "name with dashes replaced" heuristic is marked as such.
IMPORT_ALIASES: dict[str, list[str]] = {
    "pillow": ["PIL"],
    "pyyaml": ["yaml"],
    "beautifulsoup4": ["bs4"],
    "scikit-learn": ["sklearn"],
    "opencv-python": ["cv2"],
    "opencv-python-headless": ["cv2"],
    "python-dateutil": ["dateutil"],
    "attrs": ["attr", "attrs"],
    "python-dotenv": ["dotenv"],
    "setuptools": ["setuptools", "pkg_resources", "distutils"],
    "jinja2": ["jinja2"],
    "markupsafe": ["markupsafe"],
    "charset-normalizer": ["charset_normalizer"],
    "typing-extensions": ["typing_extensions"],
    "protobuf": ["google.protobuf"],
    "pyjwt": ["jwt"],
    "nose": ["nose"],
    # Machine-learning stack: distribution names that differ from their import names.
    "tensorflow-cpu": ["tensorflow"],
    "tensorflow-gpu": ["tensorflow"],
    "tensorflow-intel": ["tensorflow"],
    "tensorflow-macos": ["tensorflow"],
    "tensorflow-aarch64": ["tensorflow"],
    "tf-nightly": ["tensorflow"],
    "tf-keras": ["tf_keras"],
    "keras": ["keras", "tensorflow.keras"],
    "keras-nightly": ["keras", "tensorflow.keras"],
    "keras-preprocessing": ["keras_preprocessing"],
    "tensorflow-hub": ["tensorflow_hub"],
    "tensorflow-datasets": ["tensorflow_datasets"],
    "tensorflow-probability": ["tensorflow_probability"],
    "tensorflow-addons": ["tensorflow_addons"],
    "tensorflow-text": ["tensorflow_text"],
    "tflite-runtime": ["tflite_runtime"],
    "torch": ["torch"],
    "pytorch-lightning": ["pytorch_lightning"],
    "lightning": ["lightning"],
    "opencv-contrib-python": ["cv2"],
    "opencv-contrib-python-headless": ["cv2"],
    "scikit-image": ["skimage"],
    "sentence-transformers": ["sentence_transformers"],
    "faiss-cpu": ["faiss"],
    "faiss-gpu": ["faiss"],
    "onnxruntime-gpu": ["onnxruntime"],
    "jax": ["jax"],
    "jaxlib": ["jaxlib"],
}
# Packages commonly installed transitively; an import of these that is not declared
# directly is reported as an undeclared (transitive) dependency.
KNOWN_TRANSITIVE = {
    "certifi": "certifi", "urllib3": "urllib3", "charset_normalizer": "charset-normalizer",
    "markupsafe": "markupsafe", "idna": "idna", "typing_extensions": "typing-extensions",
}
TEST_RUNNER_PACKAGES = {"pytest", "nose", "nose2", "tox", "coverage", "pytest-cov"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_files(root: Path, pattern: str):
    for path in sorted(root.rglob(pattern)):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        if path.is_file():
            yield path, rel.as_posix()


# --------------------------------------------------------------------------- manifests

def _parse_requirement(raw: str, relative_source: str, line_number: int | None = None,
                       group: str | None = None) -> dict | None:
    value = raw.strip()
    if not value or value.startswith("#"):
        return None
    if " #" in value:
        value = value.split(" #", 1)[0].strip()
    if value.startswith(("-r", "--requirement", "-c", "--constraint")):
        return {
            "name": value, "normalized_name": None, "specifier": "", "extras": [], "markers": None,
            "source": relative_source, "line": line_number, "group": group, "raw": raw.strip(),
            "parse_status": "directive", "parse_error": "Include/constraint directive (target file is scanned separately if found).",
        }
    try:
        req = Requirement(value)
        return {
            "name": req.name,
            "normalized_name": canonicalize_name(req.name),
            "specifier": str(req.specifier),
            "extras": sorted(req.extras),
            "markers": str(req.marker) if req.marker else None,
            "source": relative_source,
            "line": line_number,
            "group": group,
            "raw": raw.strip(),
            "parse_status": "parsed",
        }
    except Exception as exc:  # editable/VCS/path entries are preserved, not dropped
        return {
            "name": value, "normalized_name": None, "specifier": "", "extras": [], "markers": None,
            "source": relative_source, "line": line_number, "group": group, "raw": raw.strip(),
            "parse_status": "unparsed", "parse_error": str(exc),
        }


def _manifest_group(rel: str) -> str:
    name = Path(rel).name.lower()
    return "dev" if any(token in name for token in ("dev", "test", "lint", "doc")) else "runtime"


def _read_requirements(path: Path, rel: str) -> tuple[list[dict], list[dict]]:
    deps: list[dict] = []
    commented: list[dict] = []
    group = _manifest_group(rel)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            # A commented-out requirement is worth surfacing: it records an earlier decision.
            candidate = stripped.lstrip("#").strip()
            if re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*\s*(==|>=|<=|~=|!=|>|<)", candidate):
                commented.append({"source": rel, "line": number, "raw": stripped})
            continue
        item = _parse_requirement(line, rel, number, group=group)
        if item:
            deps.append(item)
    return deps, commented


def _toml_line(lines: list[str], needle: str) -> int | None:
    for number, line in enumerate(lines, start=1):
        if needle in line:
            return number
    return None


def _read_pyproject(path: Path, rel: str) -> tuple[list[dict], list[str], dict]:
    deps: list[dict] = []
    warnings: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return [], [f"{rel}: could not parse TOML: {exc}"], {}

    def add(raw: str, group: str):
        item = _parse_requirement(raw, rel, _toml_line(lines, f'"{raw}"'), group=group)
        if item:
            deps.append(item)

    project = data.get("project", {}) or {}
    for raw in project.get("dependencies", []) or []:
        add(raw, "runtime")
    for group, values in (project.get("optional-dependencies", {}) or {}).items():
        for raw in values or []:
            add(raw, f"optional:{group}")
    for group, values in (data.get("dependency-groups", {}) or {}).items():
        for raw in values or []:
            if isinstance(raw, str):
                add(raw, f"group:{group}")

    poetry = (data.get("tool", {}) or {}).get("poetry", {}) or {}
    sections = [("poetry", poetry.get("dependencies", {}) or {})]
    sections += [(f"poetry-group:{g}", (c or {}).get("dependencies", {}) or {})
                 for g, c in (poetry.get("group", {}) or {}).items()]
    for group, table in sections:
        for package, spec in table.items():
            if package.lower() == "python":
                continue
            version = spec if isinstance(spec, str) else (spec or {}).get("version", "") if isinstance(spec, dict) else ""
            version = version if isinstance(version, str) else ""
            if version in ("*", ""):
                raw = package
            elif version.startswith(("=", "<", ">", "!", "~")):
                raw = package + version
            elif version.startswith("^"):
                raw = f"{package}>={version[1:]}"
                warnings.append(f"{rel}: Poetry caret constraint for {package} approximated as '>={version[1:]}'.")
            else:
                raw = f"{package}=={version}"
            item = _parse_requirement(raw, rel, _toml_line(lines, package), group=group)
            if item:
                deps.append(item)

    info = {
        "name": project.get("name") or poetry.get("name"),
        "version": project.get("version") or poetry.get("version"),
        "requires_python": project.get("requires-python") or (poetry.get("dependencies", {}) or {}).get("python"),
        "requires_python_line": _toml_line(lines, "requires-python"),
        "build_requires": (data.get("build-system", {}) or {}).get("requires", []),
        "pytest_configured": "pytest" in ((data.get("tool", {}) or {})),
    }
    return deps, warnings, info


# --------------------------------------------------------------------------- source analysis

def _local_modules(root: Path) -> set[str]:
    names = set()
    for path, rel in _iter_files(root, "*.py"):
        parts = Path(rel).parts
        names.add(parts[0].removesuffix(".py"))
    for child in root.iterdir():
        if child.is_dir() and (child / "__init__.py").exists():
            names.add(child.name)
    return names


def _module_name(rel: str) -> str:
    parts = list(Path(rel).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


class _ImportVisitor(ast.NodeVisitor):
    """Collect import statements and attribute/symbol uses of the imported names."""

    def __init__(self, lines: list[str], module: str = "", is_package: bool = False):
        self.lines = lines
        self.module = module
        self.is_package = is_package
        self.imports: list[dict] = []
        self.relative_imports: list[dict] = []
        self.bound: dict[str, str] = {}  # local name -> top-level module
        self.symbol_uses: list[dict] = []

    def _stmt(self, node) -> str:
        start, end = node.lineno, getattr(node, "end_lineno", node.lineno) or node.lineno
        return " ".join(line.strip() for line in self.lines[start - 1:end])

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            top = alias.name.split(".", 1)[0]
            local = alias.asname or top
            self.bound[local] = top
            self.imports.append({"module": alias.name, "top": top, "names": [], "line": node.lineno,
                                 "statement": self._stmt(node), "kind": "import"})

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.level:
            # Relative import: local code. Resolve to an absolute module for the test graph.
            base = self.module.split(".") if self.module else []
            drop = node.level - 1 if self.is_package else node.level
            base = base[:len(base) - drop] if drop else base
            absolute = ".".join(base + ([node.module] if node.module else []))
            self.relative_imports.append({"module": absolute, "names": [a.name for a in node.names]})
            return
        if not node.module:
            return
        top = node.module.split(".", 1)[0]
        names = [a.name for a in node.names]
        for alias in node.names:
            self.bound[alias.asname or alias.name] = top
        self.imports.append({"module": node.module, "top": top, "names": names, "line": node.lineno,
                             "statement": self._stmt(node), "kind": "from"})

    def visit_Attribute(self, node: ast.Attribute):
        chain = []
        current = node
        while isinstance(current, ast.Attribute):
            chain.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name) and current.id in self.bound:
            chain.append(current.id)
            self.symbol_uses.append({"top": self.bound[current.id], "symbol": ".".join(reversed(chain)),
                                     "line": node.lineno})
            return  # don't double count inner attributes
        self.generic_visit(node)


def _analyze_sources(root: Path) -> tuple[dict, list[dict]]:
    files: dict[str, dict] = {}
    errors: list[dict] = []
    for path, rel in _iter_files(root, "*.py"):
        try:
            if path.stat().st_size > MAX_SOURCE_BYTES:
                errors.append({"file": rel, "error": "skipped: larger than size limit"})
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=rel)
        except (OSError, SyntaxError, ValueError) as exc:
            errors.append({"file": rel, "error": str(exc)})
            continue
        visitor = _ImportVisitor(source.splitlines(), _module_name(rel), path.name == "__init__.py")
        visitor.visit(tree)
        files[rel] = {"imports": visitor.imports, "relative_imports": visitor.relative_imports,
                      "symbol_uses": visitor.symbol_uses, "is_test": _is_test_file(rel)}
    return files, errors


def _is_test_file(rel: str) -> bool:
    p = Path(rel)
    return "tests" in p.parts or "test" in p.parts or p.name.startswith("test_") or p.name.endswith("_test.py") \
        or p.name == "conftest.py"


def _git_info(root: Path) -> dict:
    def run(*args):
        try:
            out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10)
            return out.stdout.strip() if out.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None
    commit = run("rev-parse", "HEAD")
    return {
        "is_git_repository": commit is not None,
        "commit": commit,
        "branch": run("rev-parse", "--abbrev-ref", "HEAD"),
        "remote_url": run("config", "--get", "remote.origin.url"),
        "dirty": bool(run("status", "--porcelain")) if commit else None,
    }


# --------------------------------------------------------------------------- main entry

def scan_repository(repository: str | Path) -> dict:
    root = Path(repository).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    dependencies: list[dict] = []
    manifests: list[dict] = []
    warnings: list[str] = []
    commented: list[dict] = []
    project_info: dict = {}

    for path, rel in _iter_files(root, "requirements*.txt"):
        manifests.append({"path": rel, "sha256": _sha256(path), "type": "requirements",
                          "group": _manifest_group(rel)})
        try:
            parsed, comments = _read_requirements(path, rel)
        except OSError as exc:
            warnings.append(f"{rel}: could not read: {exc}")
            continue
        dependencies.extend(parsed)
        commented.extend(comments)

    for path, rel in _iter_files(root, "pyproject.toml"):
        manifests.append({"path": rel, "sha256": _sha256(path), "type": "pyproject", "group": "mixed"})
        parsed, parse_warnings, info = _read_pyproject(path, rel)
        dependencies.extend(parsed)
        warnings.extend(parse_warnings)
        if rel == "pyproject.toml":
            project_info = info

    for other in ("setup.py", "setup.cfg", "Pipfile", "Pipfile.lock", "poetry.lock", "uv.lock", "environment.yml"):
        for _, rel in _iter_files(root, other):
            manifests.append({"path": rel, "sha256": None, "type": "unsupported"})
            warnings.append(f"{rel}: manifest format not parsed by GhostLib; its dependencies are not included.")

    if not manifests:
        warnings.append("No supported dependency manifests were found (requirements*.txt, pyproject.toml).")

    sources, parse_errors = _analyze_sources(root)
    local = _local_modules(root)
    stdlib = set(sys.stdlib_module_names)

    packages = _group_packages(dependencies)
    import_index = {}
    for pkg in packages.values():
        names = pkg["import_names"]
        for name in names:
            import_index.setdefault(name, []).append(pkg["normalized_name"])

    # Map imports to packages with locations and symbols.
    undeclared: dict[str, dict] = {}
    for rel, info in sources.items():
        for imp in info["imports"]:
            top = imp["top"]
            # Owners of the top-level module, plus owners of dotted aliases this import reaches
            # (e.g. `from tensorflow import keras` / `tensorflow.keras.layers` also use the keras package).
            reached = {imp["module"]} | {f"{imp['module']}.{n}" for n in imp["names"]}
            candidates = list(dict.fromkeys(
                (import_index.get(top) or [])
                + [o for key, owners in import_index.items() if "." in key
                   and any(r == key or r.startswith(key + ".") for r in reached) for o in owners]))
            symbols = sorted({u["symbol"] for u in info["symbol_uses"] if u["top"] == top})
            location = {
                "file": rel, "line": imp["line"], "statement": imp["statement"],
                "imported_names": imp["names"], "symbols_used": symbols, "is_test": info["is_test"],
                "private_api": sorted({n for n in imp["names"] if n.startswith("_") and not n.startswith("__")}
                                      | {s for s in symbols if any(p.startswith("_") and not p.startswith("__")
                                                                    for p in s.split(".")[1:])}),
            }
            if candidates:
                for owner in candidates:
                    packages[owner]["locations"].append(location)
            elif top not in stdlib and top not in local and top != "__future__":
                entry = undeclared.setdefault(top, {
                    "import_name": top,
                    "likely_distribution": KNOWN_TRANSITIVE.get(top),
                    "mapping_confidence": "known-alias" if top in KNOWN_TRANSITIVE else "uncertain",
                    "locations": [],
                })
                entry["locations"].append(location)

    module_to_tests = _test_relations(sources)
    for pkg in packages.values():
        files = sorted({loc["file"] for loc in pkg["locations"]})
        src_files = [f for f in files if not sources[f]["is_test"]]
        tests = set()
        for f in src_files:
            tests.update(module_to_tests.get(_module_name(f), set()))
        tests.update(f for f in files if sources[f]["is_test"])
        pkg["usage"] = {
            "status": "observed" if files else "not_observed_static",
            "files": files,
            "source_files": src_files,
            "relevant_tests": sorted(tests),
            "symbols": sorted({s for loc in pkg["locations"] for s in loc["symbols_used"]}
                              | {f"{loc['statement']}" for loc in pkg["locations"] if not loc["symbols_used"]}),
            "private_api_uses": [loc for loc in pkg["locations"] if loc["private_api"]],
            "coverage_gap": bool(src_files) and not tests,
        }

    conflicts = [
        {"package": p["normalized_name"],
         "declarations": [{"source": d["source"], "line": d["line"], "specifier": d["specifier"] or "(any)"}
                          for d in p["declarations"]]}
        for p in packages.values()
        if len({d["specifier"] for d in p["declarations"]}) > 1
    ]

    # Back-compat flat views used by the capsule/tests.
    for dep in dependencies:
        pkg = packages.get(dep.get("normalized_name") or "")
        dep["usage"] = {"status": pkg["usage"]["status"], "files": pkg["usage"]["files"]} if pkg else None
        dep["evidence"] = {"manifest": dep.get("source"), "line": dep.get("line"), "raw_declaration": dep.get("raw")}

    usage = [
        {"package": p["normalized_name"], "import_name": ", ".join(p["import_names"]),
         "mapping_confidence": p["mapping_confidence"], "files": p["usage"]["files"],
         "status": p["usage"]["status"], "confidence": "static-best-effort"}
        for p in sorted(packages.values(), key=lambda x: x["normalized_name"])
    ]

    return {
        "schema_version": "0.3",
        "repository": str(root),
        "git": _git_info(root),
        "project": project_info,
        "python_requirement": project_info.get("requires_python"),
        "manifests": manifests,
        "dependencies": dependencies,
        "packages": sorted(packages.values(), key=lambda x: x["normalized_name"]),
        "usage": usage,
        "undeclared_imports": sorted(undeclared.values(), key=lambda x: x["import_name"]),
        "declaration_conflicts": conflicts,
        "commented_out_requirements": commented,
        "source_files_scanned": len(sources),
        "test_files": sorted(f for f, i in sources.items() if i["is_test"]),
        "source_parse_errors": parse_errors,
        "warnings": warnings,
        "limitations": [
            "Parsed formats: requirements*.txt (all directories) and pyproject.toml (PEP 621, PEP 735 groups, Poetry). "
            "setup.py/setup.cfg/lockfiles are listed but not parsed.",
            "Declared versions are reported; installed versions are only known where tests were executed.",
            "Static AST analysis misses dynamic imports, plugins, and indirect use through other libraries.",
            "Distribution-to-import-name mapping uses a small curated alias table plus a name heuristic; "
            "entries marked 'heuristic' may be wrong.",
            "Relevant tests are inferred from direct imports of the affected modules; conftest-level imports are not traced.",
            "This is not a vulnerability scanner and does not establish package safety.",
        ],
    }


def _group_packages(dependencies: list[dict]) -> dict[str, dict]:
    packages: dict[str, dict] = {}
    for dep in dependencies:
        name = dep.get("normalized_name")
        if not name:
            continue
        pkg = packages.setdefault(name, {
            "name": dep["name"], "normalized_name": name,
            "import_names": IMPORT_ALIASES.get(name, [name.replace("-", "_")]),
            "mapping_confidence": "curated-alias" if name in IMPORT_ALIASES else "heuristic",
            "declarations": [], "groups": set(), "locations": [],
            "is_test_tooling": name in TEST_RUNNER_PACKAGES,
        })
        pkg["declarations"].append({k: dep.get(k) for k in ("source", "line", "raw", "specifier", "markers", "extras", "group")})
        pkg["groups"].add(dep.get("group") or "runtime")
    for pkg in packages.values():
        pkg["groups"] = sorted(pkg["groups"])
        pkg["pinned_versions"] = sorted({d["specifier"][2:] for d in pkg["declarations"]
                                         if d["specifier"].startswith("==") and "," not in d["specifier"]})
    return packages


def _test_relations(sources: dict) -> dict[str, set[str]]:
    """module name -> test files that reach it through direct or transitive local imports.

    Local edges include relative and function-level imports, so a test importing
    ``pkg.cli`` is related to every local module ``pkg.cli`` imports (statically).
    """
    modules = {_module_name(rel): rel for rel in sources}
    graph: dict[str, set[str]] = {}
    for rel, info in sources.items():
        name = _module_name(rel)
        edges = graph.setdefault(name, set())
        for imp in info["imports"] + info.get("relative_imports", []):
            for target in {imp["module"]} | {f"{imp['module']}.{n}" for n in imp["names"]}:
                if target in modules:
                    edges.add(target)
    relations: dict[str, set[str]] = {}
    for rel, info in sources.items():
        if not info["is_test"]:
            continue
        seen: set[str] = set()
        stack = list(graph.get(_module_name(rel), set()))
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(graph.get(current, set()))
        for module in seen:
            relations.setdefault(module, set()).add(rel)
    return relations


def map_import_usage(root: Path, dependencies: list[dict]) -> list[dict]:
    """Back-compat facade: run a scan on root and return the flat usage list."""
    return scan_repository(root)["usage"]
