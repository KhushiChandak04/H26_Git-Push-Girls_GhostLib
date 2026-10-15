# GhostLib

**Evidence-first dependency resilience.** GhostLib scans a real Python repository, shows the evidence behind every
dependency risk, asks **Gemma 4** for a migration plan, runs **baseline-versus-candidate tests in a disposable
workspace**, and writes a reusable **Dependency Exit Capsule** that says exactly what was proven and what was not.

> Most tools tell you a library is risky. GhostLib shows you the evidence, experiments with a replacement, and tells
> you exactly what was proven and what remains uncertain.

Built for the hackathon's Track 1 (Gemma 4: Dependency Resilience). The target repository is
[rishrek/LinkWatch](https://github.com/rishrek/LinkWatch), which is analysed dynamically. No findings are hard-coded.

## Two ways to use it: CLI and browser

GhostLib is **one Python engine with two front doors**. Both produce identical results and artifacts.

| | Terminal (CLI) | Browser (local dashboard) |
|---|---|---|
| Start | `pip install -e .` then `ghostlib scan targets/LinkWatch` | `uvicorn app.main:app --app-dir backend` + `npm --prefix frontend run dev`, then open http://localhost:5173 |
| Best for | CI, scripting, power users, reproducing a capsule | Demos, reviewing evidence, clicking through a migration |
| Output | Tables in the terminal + `artifacts/runs/<run-id>/` | The same run files, rendered in five tabs |

The dashboard runs **locally**. It is not a hosted website: the backend reads the repository on your machine and runs
tests in temporary copies there. Nothing is uploaded except the evidence sent to Gemma 4 when you ask for a
recommendation.

### Use it on your own project, right where you work

```bash
pip install -e /path/to/H26_Git-Push-Girls_GhostLib   # once; Python 3.12 or 3.13
cd /path/to/your-project
ghostlib scan                     # scans the current folder; findings print as clickable file:line
ghostlib scan --format problems   # file:line:col: severity: message (compiler style)
ghostlib ui                       # dashboard + API on http://127.0.0.1:8000 (run `npm --prefix frontend run build` once)
ghostlib scan https://github.com/rishrek/LinkWatch   # or a public GitHub URL (shallow-cloned into artifacts/clones/)
```

**VS Code:** copy [`integrations/vscode/tasks.json`](integrations/vscode/tasks.json) to `<your-project>/.vscode/tasks.json`.
Then press `Ctrl+Shift+P`, choose **Tasks: Run Task**, then **GhostLib: scan this workspace**. Every finding
(risky declarations, private-API calls, undeclared imports) appears in the **Problems** panel, and clicking one
jumps to the exact line. The same file also has tasks to open the dashboard and to show what GhostLib has learned.
No extension needs to be installed. Applying a migration also happens in VS Code: the Migration tab's
*Open patch in VS Code* button, or `git apply <patch>`.

**Input rules:** the main input is a local repository path. A public `https://github.com/<owner>/<repo>` URL is also
accepted and shallow-cloned without prompting for credentials. Other hosts, private repositories and files give a
clear error asking for a local path.

## Evidence labels

Every statement in the dashboard and the capsule carries one of these labels:

| Label | Meaning |
|---|---|
| **OBSERVED** | Read directly from repository files (manifests, Python AST) or git metadata |
| **SOURCED** | Retrieved from PyPI's JSON API. The URL and retrieval time are recorded |
| **EXECUTION-VERIFIED** | Produced by a command GhostLib actually ran. The argv, exit code and full log are recorded |
| **AI-RECOMMENDED** | Suggested by Gemma 4. Schema-validated, but not established as true |
| **UNKNOWN** | Could not be established, or not tested |

## What it does

1. **Scan (OBSERVED):** finds `requirements*.txt` and `pyproject.toml` recursively, skipping venvs and build dirs. It records:
   - every declaration with file and line;
   - every import with file, line, statement and the symbols used (e.g. `toml.load`);
   - private-API use and undeclared imports;
   - conflicting declarations and commented-out requirements;
   - which tests reach each usage, through direct, transitive and function-level imports.
2. **Metadata (SOURCED):** fetches PyPI facts for the latest release and the pinned version: release dates,
   `Requires-Python`, classifiers and yanked status. Responses are cached for 24 h in `artifacts/cache/pypi`.
3. **Risk (rule-based):** a transparent points rubric (`backend/app/services/risk_engine.py`). Each indicator shows its
   evidence, type and points. It is not a probability, not proof of abandonment, and excludes vulnerability data.
4. **Gemma 4 (AI-RECOMMENDED):** receives only the collected evidence and returns candidates, migration steps,
   breaking changes, suggested tests and uncertainties.
   - The output is validated with a strict Pydantic schema.
   - Candidate packages are then checked deterministically: PyPI existence, declared Python 3.12/3.13 support,
     stdlib presence.
   - Failures surface as `AI_UNAVAILABLE` / `AI_ERROR` / `AI_INVALID_OUTPUT`. Output is never invented.
5. **Migration Flight Simulator (EXECUTION-VERIFIED):** **propose → review diff → approve → run → compare**.
   - Manifest edits are deterministic. Code edits for replacements come from Gemma and are limited to the affected
     files plus one new `tests/test_ghostlib_*.py`.
   - Approval records the reviewer and the diff's SHA-256.
   - The baseline and the candidate each run in their own disposable copy and uv virtualenv.
   - The comparison covers per-test outcomes (fixed / regression / still failing), installed-version changes and
     warnings, plus a check that the original repository is unchanged.
6. **Dependency Exit Capsule:** `capsule.json` + `capsule.md` per run. They contain:
   - dependency details, risk indicators and usage locations;
   - the proposed replacement, migration steps and suggested tests;
   - the diff, the exact commands and the test results;
   - compatibility gaps, open concerns and limitations;
   - reproduction and rollback instructions.

### Example: real result on LinkWatch (`f52f393`, Python 3.12.14)

| | Tests | Notes |
|---|---|---|
| Baseline (`Jinja2==2.11.3`) | 9 passed, 1 failed | `test_report` fails because `jinja2` imports `soft_unicode`, which `markupsafe` 3.x removed |
| Candidate (`Jinja2==3.1.6`) | 10 passed | 1 fixed, 0 regressions; original repository verified unchanged |
| Candidate `toml` → stdlib `tomllib` (Gemma 4 code edit, reviewed diff) | 9 passed, 1 failed | 0 regressions; only the pre-existing Jinja2 failure remains; `toml` no longer installed |

Two caveats GhostLib recorded for the tomllib experiment:
- Gemma's proposed regression test had a bug (a missing `import tempfile`), so it failed to collect. It ran in a
  separate pass, so it could not hide the migration's real result.
- The project still allows Python 3.10 (`requires-python >=3.10`), but the stdlib replacement was only verified on
  the versions tested here.

Other findings from the same scan:
- `certifi` is imported but not declared.
- `pydantic` is declared `==1.10.13` in `requirements.txt` but `>=2` in `pyproject.toml`.
- `requests` private API `_parse_content_type_header` is used, and `requests.Session.request` is monkey-patched.
- `toml` and `appdirs` have had no release since 2020.
- `idna` and `six` are declared but never imported.
- `nose==1.3.7` crashes on Python 3.12 (`No module named 'imp'`).

## Requirements

- Python **3.12 or 3.13** (not 3.14)
- [uv](https://docs.astral.sh/uv/) for experiment virtualenvs. It downloads Python 3.12/3.13 automatically if needed.
  Without uv, GhostLib falls back to `venv` + `pip` using its own interpreter version.
- Node.js 18+ for the dashboard
- Network access for PyPI metadata and the Gemma API (both optional; the scan still works without them)

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest            # GhostLib's own tests
git clone https://github.com/rishrek/LinkWatch.git targets/LinkWatch   # targets/ is git-ignored
```

### Gemma 4 configuration

GhostLib uses **Gemma 4 via the Google AI Studio / Gemini API** (REST `v1beta/models/{model}:generateContent`).

```bash
cp backend/.env.example backend/.env    # git-ignored; put your key here, never commit it
# GEMINI_API_KEY=...                    # https://aistudio.google.com/apikey
# GEMMA_MODEL=gemma-4-26b-a4b-it        # default; gemma-4-31b-it also works
ghostlib ai-check                       # verifies the model is reachable and records its resource name
```

- **Model:** `gemma-4-26b-a4b-it` by default, configurable with `GEMMA_MODEL`. The exact `modelVersion` returned by the
  API is stored with every response.
- **Access method:** Google AI Studio API key, hosted inference.
- **Terms:** Gemma is provided under the [Gemma Terms of Use](https://ai.google.dev/gemma/terms). Use of the API is
  also subject to the Gemini API terms.
- **What is sent:** only the collected evidence. That means declarations, PyPI facts, risk indicators, usage
  locations with short snippets, and the bodies of functions that use the dependency. For code-change proposals, the
  full content of the affected source files is sent too.
- **Generation settings:** requests use JSON output mode and `thinkingConfig.thinkingLevel = "minimal"`
  (`GEMMA_THINKING_LEVEL`). Without it, Gemma 4's hidden reasoning was observed to use the entire output budget:
  8,189 thought tokens, no answer, then HTTP 500s. With it, recommendations return in about 12–22 s.
- **AI-written tests:** they run in a second pytest pass, separate from the repository's own suite. Only the
  repository's suite is compared against the baseline.
- **Fallback:** without a key, every AI step reports `AI_UNAVAILABLE`. Scanning, metadata, risk, deterministic upgrade
  and removal experiments, and the capsule all keep working.

## CLI

```bash
ghostlib scan targets/LinkWatch                      # scan + PyPI + risk + capsule
ghostlib scan targets/LinkWatch --recommend          # ... + Gemma 4 for every package with score >= 1
ghostlib recommend <run-id> toml                     # Gemma 4 for one package
ghostlib experiment <run-id> jinja2                  # propose: prints the diff, executes nothing
ghostlib experiment <run-id> jinja2 --approve        # run baseline + candidate tests (Python 3.12)
ghostlib experiment <run-id> jinja2 --approve --python 3.13
ghostlib experiment <run-id> toml --candidate tomllib --kind stdlib   # replacement with Gemma code edits
ghostlib experiment <run-id> jinja2 --reject         # discard the candidate workspace
ghostlib capsule <run-id>                            # regenerate capsule.json / capsule.md
ghostlib runs
ghostlib auto targets/LinkWatch --top 3              # agent: scan, rank, ask Gemma, choose, prepare diffs (stops for approval)
ghostlib auto targets/LinkWatch --top 3 --approve-all   # explicit up-front approval: also run the tests
ghostlib learn                                       # what GhostLib has learned from past experiments
```

### Learning from experience (agentic mode)

GhostLib improves as it tests more repositories. This is a small, explainable reinforcement-learning loop
(a multi-armed bandit), not a trained neural model:

- **Experience:** every completed experiment, on any repository, is replayed from `artifacts/runs/`. Each has a
  reward computed only from executed tests: 1.0 = fixed failing tests with no regressions, 0.5 = nothing broke,
  0 = something broke or the tests could not run.
- **Choosing a fix:** each (package, kind, candidate) option is an "arm". Its value is the smoothed mean reward, and
  untried options get an exploration bonus (UCB1). The dashboard marks the "best bet from experience".
- **Spotting risky packages:** for each risk rule, GhostLib tracks how often a flagged package turned out to be
  worth migrating. That re-weights the rule score into a **learned priority**, shown next to the unchanged rule score.
- **Memory in prompts:** past verified outcomes for a package are sent to Gemma as evidence.
- **Agent loop:** `ghostlib auto` = scan → rank by learned priority → Gemma → choose with UCB → prepare diffs.
  It runs nothing without approval, unless you pass `--approve-all`.

Limits: small samples are noisy, and a reward only reflects the tests a repository has.

Artifacts are written to `artifacts/runs/<run-id>/`: `scan.json`, `recommendations/`, `baseline-py3.12/`,
`experiments/<pkg>/` (diff, logs, junit, workspace) and `capsule/`.

## Dashboard

```bash
uvicorn app.main:app --app-dir backend --port 8000      # API + docs at http://127.0.0.1:8000/docs
cd frontend && npm ci && npm run dev                    # http://localhost:5173
```

The dashboard has five pages:
1. **Overview:** scan form, run history, risk ranking and repository findings.
2. **Dependency Explorer:** declarations, PyPI facts, indicators with evidence, usage locations with a source viewer,
   and relevant tests.
3. **Migration Workbench:** Gemma recommendation with validation, candidate choice, the diff, and the approval
   checkbox with Approve or Reject.
4. **Verification Center:** baseline vs candidate, the per-test table, command logs and warnings.
5. **Exit Capsule:** the rendered report with JSON and Markdown downloads.

Set `VITE_API_BASE` if the API is not on `http://127.0.0.1:8000/api`.

## Safety and isolation (what is and is not provided)

- Scans read files only. GhostLib never writes to the target repository. After each experiment it compares
  `git status --porcelain` and the manifest SHA-256 hashes before and after.
- Experiments run in **disposable copies** (without `.git`) with **separate virtualenvs**. Commands are fixed argv
  lists with no shell, run with timeouts, and must stay inside the run directory. The environment is allow-listed,
  so API keys and git credentials are not passed to tests.
- **This is not a security sandbox.** The target's tests execute as the current OS user and have network access. Only
  run GhostLib against repositories you trust.
- Nothing is merged automatically. To adopt a candidate, review `experiments/<pkg>/proposal.diff` and apply it yourself.
- Model output never becomes a shell command.

## Known limitations

- Parsed manifests: `requirements*.txt` and `pyproject.toml` (PEP 621, PEP 735 groups, Poetry).
  `setup.py`/`setup.cfg`/lockfiles are listed but not parsed.
- Static analysis misses dynamic imports. The import-to-distribution mapping uses a small curated table, and
  heuristic matches are labelled as such.
- Test relevance comes from the import graph, not line coverage.
- Passing tests show no regressions in the behaviour those tests exercise. They do not prove equivalence.
- Experiments install the root `requirements*.txt` files, falling back to `pip install -e .`.

## License

MIT. See [LICENSE](LICENSE).
