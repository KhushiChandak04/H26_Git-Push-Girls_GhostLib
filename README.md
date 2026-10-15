# GhostLib

**Evidence-first dependency resilience and migration analysis.**

GhostLib is a local-first Python/React starter for inspecting dependency declarations, mapping best-effort static imports, collecting optional package metadata, and generating a reusable Dependency Exit Capsule.

> **Status:** Initial implementation. This is not yet a complete AI migration agent. Gemma 4 recommendations, safe migration execution, and baseline-versus-candidate test execution remain unfinished.

## Implemented now

- CLI and FastAPI endpoint for scanning a local repository.
- `requirements*.txt` and common PEP 621 / Poetry sections in `pyproject.toml`.
- Manifest path, declaration, line (where available), group and manifest SHA-256 evidence.
- Best-effort Python AST import mapping with a small alias map.
- Explainable triage indicators; no invented numeric risk score.
- Optional PyPI JSON metadata provider, **off by default**.
- JSON and Markdown Dependency Exit Capsule generation.
- Disposable workspace copy creation (does not run code or migration commands).
- Migration plan shape validation and test-result summary comparison helpers.
- React/Vite dashboard with Overview scan form and scaffold pages for the remaining workflows.
- Detailed project checklist in `docs/IMPLEMENTATION_CHECKLIST.md`.

## Not implemented yet

- Gemma 4 inference adapter.
- Reliable complete dependency graph and all manifest/lockfile formats.
- Automated replacement discovery and compatibility evaluation.
- Migration edits, package installation, isolated baseline/candidate test execution.
- Full behavioural equivalence checking and adaptive regression-test generation.
- Completed frontend workflows for migration, verification and capsule download.

Do not claim these features are complete until implemented and tested.

## Requirements

- Python 3.12 (recommended for the event target).
- Node.js 18+ for the dashboard.
- Network access is only needed if you explicitly request PyPI metadata.

## Backend setup

From the project root:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

python -m pip install -r backend/requirements.txt
```

Run the tests:

```bash
cd backend
python -m pytest
cd ..
```

Run the API from the project root:

```bash
uvicorn app.main:app --app-dir backend --reload
```

API base: `http://127.0.0.1:8000`; interactive docs: `http://127.0.0.1:8000/docs`.

## CLI

```bash
PYTHONPATH=backend python -m app.cli /absolute/path/to/LinkWatch --out artifacts
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = "backend"
python -m app.cli "C:\\absolute\\path\\to\\LinkWatch" --out artifacts
```

This writes `dependency-exit-capsule.json` and `dependency-exit-capsule.md`.

Optional metadata fetch (makes network requests to PyPI; only use if event rules permit):

```bash
PYTHONPATH=backend python -m app.cli /absolute/path/to/LinkWatch --out artifacts --fetch-metadata
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

By default, the UI expects the backend at `http://127.0.0.1:8000/api`. Set `VITE_API_BASE` to override it.

## Safety

- The scanner reads files but does not execute repository code.
- Workspace creation copies files and excludes common VCS/cache/environment folders.
- This starter does not install packages or execute migration commands.
- Before enabling command execution, implement strict allowlists, timeouts, environment isolation, resource limits, process cleanup and full execution logs.
- Do not commit secrets or API keys.

## Event compliance

The event brief requires a specific starter/fork submission workflow; confirm the required repository lineage and naming with organizers. Confirm the allowed Gemma 4 inference method because hosted inference may conflict with a no-cloud-services rule. Network metadata fetching is opt-in and should only be used if permitted.

## License

MIT. See [LICENSE](LICENSE).
