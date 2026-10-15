# GhostLib

**Evidence-first dependency resilience.** GhostLib scans a local Python repository or a public GitHub URL, shows the
evidence behind dependency risk, asks **Gemma 4** for migration plans, prepares reviewable patches, and writes a
reusable **Dependency Exit Capsule**. Repository tests are fail-closed until a supported OS/container sandbox is
available; GhostLib will not execute untrusted project code as the current user.

> Most tools tell you a library is risky. GhostLib shows you the evidence, experiments with a replacement, and tells
> you exactly what was proven and what remains uncertain.

Built for the hackathon's Track 1 (Gemma 4: Dependency Resilience). The target repository is
[rishrek/LinkWatch](https://github.com/rishrek/LinkWatch), which is analysed dynamically. No findings are hard-coded.

**Requirement audit:** [docs/COMPLIANCE.md](docs/COMPLIANCE.md) maps every Track 1 requirement and capsule field
to where it is implemented, with the executed results for all 10 at-risk LinkWatch dependencies.
**Demo flow:** [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## Two ways to use it: CLI and browser

GhostLib is **one Python engine with two front doors**. Both produce identical results and artifacts.

| | Terminal (CLI) | Browser (local dashboard) |
|---|---|---|
| Start | `pip install -e .` then `ghostlib scan targets/LinkWatch` | `uvicorn app.main:app --app-dir backend` + `npm --prefix frontend run dev`, then open http://localhost:5173 |
| Best for | CI, scripting, power users, reproducing a capsule | Demos, reviewing evidence, clicking through a migration |
| Output | Findings, recommendations, proposed patches + `artifacts/runs/<run-id>/` | Backend run history, findings, recommendations, verification state and capsule |

The dashboard runs **locally**. It is not a hosted website: the backend reads repository files on your machine.
Evidence is sent to Gemma 4 when a recommendation or code-change proposal is requested.

### Use it on your own project, right where you work

```bash
pip install -e /path/to/H26_Git-Push-Girls_GhostLib   # once; Python 3.12 or 3.13
cd /path/to/your-project
ghostlib scan                     # scans the current folder; findings print as clickable file:line
ghostlib scan --format problems   # file:line:col: severity: message (compiler style)
ghostlib ui                       # dashboard + API on http://127.0.0.1:8000 (run `npm --prefix frontend run build` once)
python -m app.cli https://github.com/rishrek/LinkWatch # full pipeline; fresh shallow clone per scan
```

**VS Code:** copy [`integrations/vscode/tasks.json`](integrations/vscode/tasks.json) to `<your-project>/.vscode/tasks.json`.
Then press `Ctrl+Shift+P`, choose **Tasks: Run Task**, then **GhostLib: scan this workspace**. Every finding
(risky declarations, private-API calls, undeclared imports) appears in the **Problems** panel, and clicking one
jumps to the exact line. The same file also has tasks to open the dashboard and to show what GhostLib has learned.
No extension needs to be installed. Applying a migration also happens in VS Code: the Migration tab's
*Open patch in VS Code* button, or `git apply <patch>`.

**Opening files in VS Code from the dashboard:** the *Open in VS Code* buttons ask the local backend to run
`code -g <file>:<line>`. A web page cannot launch desktop apps, but the backend runs on your machine. Only files inside
the scanned repository or the run's own folder can be opened. This needs the `code` command on PATH (VS Code:
*Shell Command: Install 'code' command in PATH*); if it is missing, the button shows a `vscode://` fallback link.

**Input rules:** the main input is a local repository path. A public `https://github.com/<owner>/<repo>` URL is also
accepted and shallow-cloned without prompting for credentials. Other hosts, private repositories and files give a
clear error asking for a local path.

## Machine-learning stacks (TensorFlow / Keras / NumPy)

GhostLib was tested on [`examples/ml-keras-demo`](examples/ml-keras-demo). It's a TensorFlow 2.10 / Keras 2 era project
pinned to `tensorflow==2.10.0`, `keras==2.10.0`, `numpy==1.23.5`, `scikit-learn==1.1.3` and `h5py==3.7.0`. It uses the
Keras-2-only `Adam(lr=...)` and has a real test suite that trains a model and round-trips an `.h5` save.

What GhostLib found, all sourced or executed:

| Finding | Evidence |
|---|---|
| `tensorflow==2.10.0` **cannot be installed on Python 3.12/3.13**, although its metadata says `Requires-Python >=3.7` | PyPI wheel tags (only cp37–cp310); confirmed by the baseline install failing |
| `numpy`, `scikit-learn`, `h5py` pins have only source builds for 3.12 | PyPI file list (rule `pinned_needs_source_build`) |
| 48 known vulnerabilities in `tensorflow==2.10.0`, 14 in `keras==2.10.0`, 1 in `scikit-learn==1.1.3` | OSV.dev |
| `keras` is used through `from tensorflow import keras` | AST (dotted-import mapping) |
| Upgrading **keras alone** is impossible: the old tensorflow pin blocks it | Executed install; the resolver's reason is shown |
| Pinning the stack to the latest of everything is impossible: tensorflow 2.21 requires `h5py<3.15` | `uv pip compile` picks compatible versions (h5py 3.14.0) |
| **Stack migration works:** tensorflow 2.21.0 + keras 3.15.1 + numpy 2.5.4 + scikit-learn 1.9.1 + h5py 3.14.0, with Gemma's `lr=` → `learning_rate=` fix | **All 3 project tests pass** on Python 3.12.14, and Gemma's 2 extra tests pass too (the original cannot even install) |

Run a stack migration with `ghostlib experiment <run-id> tensorflow --also keras numpy scikit-learn h5py --approve`.
The `also` packages are resolved to a compatible set by uv's resolver, not blindly pinned to their latest release.

**Why ML experiments are slow, and what is not our code:** in the run above, uv resolved the versions in 0.14 s,
downloading took 4 min 28 s, unpacking 1 min 22 s, and the tests 53 s (TensorFlow alone takes ~30 s to import). Download
time depends on your network. uv caches the downloads, so later TensorFlow experiments skip that step. GhostLib's own
overhead per action is now well under a second; see "Performance" below.

## Performance

| Step | Typical time | What dominates |
|---|---|---|
| Scan + PyPI + OSV | 15–25 s first time, then ~2 s (24 h cache) | Network calls to PyPI and OSV |
| Gemma recommendation | 12–22 s per package | Model inference (Google AI Studio) |
| Gemma code change | 20–50 s | Model inference (writes whole files) |
| Experiment (LinkWatch) | ~25 s | The project's own tests (they include deliberate 6 s and 2 s waits) |
| Experiment (TensorFlow, first time) | ~7 min | Downloading ~600 MB of wheels; cached afterwards |
| Opening a run in the dashboard | ~0.2–0.3 s | — (was ~3 s before caching) |

## What it does

1. **Scan (OBSERVED):** finds `requirements*.txt` and `pyproject.toml` recursively, skipping venvs and build dirs. It records:
   - every declaration with file and line;
   - every import with file, line, statement and the symbols used (e.g. `toml.load`);
   - private-API use and undeclared imports;
   - conflicting declarations and commented-out requirements;
   - which tests reach each usage, through direct, transitive and function-level imports.
2. **Metadata and advisories (SOURCED):** fetches PyPI facts and queries OSV.dev for exact pinned versions.
   Unpinned declarations and unavailable advisory data remain explicitly unknown.
3. **Risk (rule-based):** a transparent points rubric (`backend/app/services/risk_engine.py`). Each indicator shows its
   evidence, type and points. The rule score is not a probability or proof of safety.
4. **Gemma 4 (AI-RECOMMENDED):** receives only the collected evidence and returns candidates, migration steps,
   breaking changes, suggested tests and uncertainties.
   - The output is validated with a strict Pydantic schema.
   - Candidate packages are then checked deterministically: PyPI existence, declared Python 3.12/3.13 support,
     stdlib presence.
   - Failures surface as `AI_UNAVAILABLE` / `AI_ERROR` / `AI_INVALID_OUTPUT`. Output is never invented.
5. **Migration proposals:** manifest edits are deterministic; Gemma can propose source changes for replacements.
   The patch is reviewable and never applied to the original repository automatically.
   - Test verification is currently **blocked**: a copied directory and virtualenv do not safely contain untrusted
     test code. No OS/container sandbox runner is configured.
   - Blocked runs are recorded as `not_run` / `UNKNOWN`, never as successful tests or genuine regression results.
6. **Dependency Exit Capsule:** `capsule.json` + `capsule.md` per run. They contain:
   - dependency details, risk indicators and usage locations;
   - the proposed replacement, migration steps and suggested tests;
   - the diff, Gemma call evidence, advisory results and test results only when tests actually ran;
   - compatibility gaps, open concerns and limitations;
   - reproduction and rollback instructions.


## Requirements

- Python **3.12 or 3.13** (not 3.14)
- An OS/container isolation runtime is required for repository test execution. No runner is configured yet, so GhostLib
  records migration verification as blocked rather than executing tests on the host.
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


## CLI

```bash
python -m app.cli targets/LinkWatch                  # scan + recommendations + migration proposals + capsule
ghostlib scan targets/LinkWatch                      # scan + PyPI + risk + capsule
ghostlib scan targets/LinkWatch --recommend          # ... + Gemma 4 for every package with score >= 1
ghostlib recommend <run-id> toml                     # Gemma 4 for one package
ghostlib experiment <run-id> jinja2                  # propose: prints the diff, executes nothing
ghostlib experiment <run-id> jinja2 --approve        # blocked until a safe sandbox runner is configured
ghostlib experiment <run-id> jinja2 --approve --python 3.13
ghostlib experiment <run-id> toml --candidate tomllib --kind stdlib   # replacement with Gemma code edits
ghostlib experiment <run-id> jinja2 --reject         # discard the candidate workspace
ghostlib capsule <run-id>                            # regenerate capsule.json / capsule.md
ghostlib runs
ghostlib auto targets/LinkWatch --top 3              # agent: scan, rank, ask Gemma, choose, prepare diffs (stops for approval)
ghostlib auto targets/LinkWatch --top 3 --approve-all   # cannot bypass the sandbox requirement
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
  It does not execute repository code; `--approve-all` cannot bypass the missing sandbox.

Limits: small samples are noisy, and a reward only reflects the tests a repository has.

Artifacts are written to `artifacts/runs/<run-id>/`: `scan.json`, `recommendations/`, `baseline-py3.12/`,
`experiments/<pkg>/` (diff, logs, junit, workspace) and `capsule/`.

## Dashboard

```bash
uvicorn app.main:app --app-dir backend --port 8000      # API + docs at http://127.0.0.1:8000/docs
cd frontend && npm ci && npm run dev                    # http://localhost:5173
```

The dashboard has five pages:
1. **Overview:** local/GitHub source selector, run history, risk ranking and repository findings.
2. **Dependency Explorer:** declarations, PyPI/OSV facts, indicators with evidence, usage locations with a source viewer,
   and relevant tests.
3. **Migration Workbench:** Gemma recommendation with validation, candidate choice, the diff, and the approval
   checkbox with Approve or Reject.
4. **Verification Center:** baseline-vs-candidate results when available; blocked and untested runs are not presented
   as test results.
5. **Exit Capsule:** the rendered report with JSON and Markdown downloads.

Set `VITE_API_BASE` if the API is not on `http://127.0.0.1:8000/api`.

## License

MIT. See [LICENSE](LICENSE).
