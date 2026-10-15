# GhostLib — Full Project Implementation Checklist

**Status convention**
- `[x]` Implemented in the starter code. This does not imply end-to-end validation unless explicitly stated.
- `[ ]` Not implemented, or not yet verified.
- `[~]` Partially implemented / prototype only.

Last reviewed: 2026-10-15.

## 0. Current status (updated 2026-10-15)

Verified end to end on LinkWatch `f52f393`; see README "Example" and `docs/DEMO_SCRIPT.md`. The detailed sections
below are the original starter checklist and are partly outdated.

- [x] Recursive manifest scan, AST usage map (file/line/statement/symbols), private-API use, undeclared imports,
      declaration conflicts, transitive test relations.
- [x] PyPI metadata (latest + pinned version) with 24 h cache, source URL and retrieval time.
- [x] Transparent rule-based risk score; every indicator has an evidence type and its evidence.
- [x] Gemma 4 adapter (AI Studio REST, strict Pydantic schema, AI_UNAVAILABLE / AI_ERROR / AI_INVALID_OUTPUT);
      mocked tests pass. **Live call not yet verified: it needs a GEMINI_API_KEY.**
- [x] Deterministic validation of AI candidates (PyPI existence, declared Python support, stdlib presence).
- [x] Experiments: propose → diff → explicit approval → disposable copy + uv venv → baseline vs candidate pytest
      → per-test comparison → original-repo unchanged check. Verified on Python 3.12.14 and 3.13.7.
- [x] Capsule JSON + Markdown per run with evidence labels, gaps, concerns, reproduction and rollback.
- [x] CLI (`ghostlib scan|recommend|experiment|capsule|runs|ai-check`) and REST API.
- [x] React dashboard wired to the API (5 pages); production build passes.
- [x] GhostLib's own tests: 18 passing on Python 3.12.14 and 3.13.7.
- [ ] Live Gemma 4 recommendation and AI code-change experiment (e.g. toml → tomllib): pending an API key.
- [ ] Confirm the organizer's fork/submission naming requirements.

## 1. Product definition and architecture

- [x] Local-first architecture; no database or Firebase required.
- [x] Backend/frontend/docs/artifacts separated.
- [x] CLI path exists independently of the dashboard.
- [x] Safety boundary: starter does not execute repository code, package installation, or migration commands.
- [ ] Confirm organizer's required fork/submission repository arrangement before final submission.
- [ ] Write architecture diagram and data-flow documentation.
- [ ] Define stable API response schemas and error conventions.
- [ ] Add operation IDs / scan IDs so artifacts can be tied to a specific run.
- [ ] Add cancellation and progress reporting for long scans.
- [ ] Add resource limits for large repositories and large manifests.

## 2. Repository scanning and dependency inventory

- [x] Parse `requirements*.txt` declarations.
- [x] Parse PEP 621 `project.dependencies` and optional dependency groups.
- [x] Parse common Poetry dependency declarations and groups.
- [x] Preserve raw declaration, manifest path, line where available, group and parsed constraint.
- [x] Record SHA-256 for supported manifest files.
- [~] Static import mapping for Python files, with known package/import aliases.
- [ ] Resolve recursive `-r` includes and `-c` constraints safely.
- [ ] Parse `setup.py`, `setup.cfg`, `Pipfile`, `Pipfile.lock`, Poetry lock, `uv.lock`, `pdm.lock`, and other formats relevant to LinkWatch.
- [ ] Parse editable installs, VCS references, local paths and direct URL dependencies robustly.
- [ ] Resolve environment markers against a declared target Python/platform.
- [ ] Build direct vs. transitive dependency graph from lockfiles where available.
- [ ] Deduplicate equivalent declarations while preserving every source location.
- [ ] Distinguish dependency declaration, installed package and actual runtime usage.
- [ ] Improve package-name-to-import-name mapping; optionally use curated mapping data with provenance.
- [ ] Detect imports inside notebooks and non-`.py` source files if relevant.
- [ ] Add scanner fixtures based on actual LinkWatch files and edge cases.
- [ ] Add a scan summary with supported/unsupported files and parse errors.

## 3. Evidence collection and data quality

- [x] Manifest SHA-256 and declaration source information are recorded.
- [x] Scanner returns explicit limitations and parse warnings.
- [x] Capsule labels evidence as partial and notes unimplemented checks.
- [ ] Use a common evidence schema across scanner, metadata, model, test runner and capsule.
- [ ] Record evidence IDs and reference them from every generated claim.
- [ ] Record source URL, retrieval timestamp, package/version and response status for metadata.
- [ ] Record command, working directory, environment, start/end time, stdout/stderr, exit code and timeout state for executions.
- [ ] Record changed-file diffs and hashes before/after migration.
- [ ] Keep observed facts, derived indicators, model suggestions and human decisions as separate types.
- [ ] Add provenance/confidence explanations; avoid treating missing evidence as negative evidence.
- [ ] Add deterministic JSON schema validation and artifact versioning.

## 4. Dependency risk / resilience indicators

- [x] Flag declarations that could not be parsed as standard requirements.
- [x] Flag missing version constraints.
- [x] Flag no-static-import-observed as informational only.
- [x] Avoid arbitrary numeric risk scores.
- [ ] Add explainable release-cadence indicators from permitted metadata.
- [ ] Add Python-version compatibility comparison between project and candidate metadata.
- [ ] Add dependency constraint conflicts and incompatible version-range detection.
- [ ] Add deprecated/unmaintained status only when supported by reliable, cited metadata.
- [ ] Define an explicit rubric for severity and test it against examples.
- [ ] Keep vulnerability scanning out of the scoring-critical path because the event brief says it does not score.
- [ ] Add unit tests for every indicator, including false-positive cases.

## 5. Package metadata

- [x] Optional PyPI JSON metadata provider implemented.
- [x] Network access is disabled by default; CLI/API require an explicit opt-in flag.
- [ ] Confirm event rules permit network metadata requests.
- [ ] Add caching with timestamps and cache provenance.
- [ ] Add retries/backoff and strict timeouts without making scans hang.
- [ ] Record PyPI response status and missing fields accurately.
- [ ] Handle packages not hosted on PyPI.
- [ ] Compare declared version constraint with latest release only as a signal, not as an automatic upgrade recommendation.
- [ ] Add tests with mocked HTTP responses; no live network required in unit tests.

## 6. Gemma 4 integration — mandatory AI track component

- [ ] Confirm which Gemma 4 runtime/access method is permitted by organizers.
- [ ] Record exact model identifier/version, provider/runtime, access method and applicable terms.
- [ ] Implement an adapter with timeout, retries, token/input limits and structured output validation.
- [ ] Send only relevant evidence to the model; do not upload repository contents without permission.
- [ ] Prompt Gemma to produce candidate alternatives, migration rationale, compatibility risks, and test suggestions.
- [ ] Require evidence references for every factual claim where possible.
- [ ] Validate all package names and structured output before display.
- [ ] Treat model output as advisory, never as observed fact.
- [ ] Do not execute model-generated shell commands directly.
- [ ] Add offline/mock adapter for repeatable tests and demos.
- [ ] Add tests for malformed output, hallucinated package fields, timeouts and refusal/errors.
- [ ] Show AI-generated vs. deterministic findings distinctly in UI and capsule.
- [ ] Include model disclosure and terms in README/submission materials.

## 7. Replacement discovery and evaluation

- [x] Candidate name normalization helper exists.
- [x] Basic candidate object shape validation exists.
- [ ] Verify candidate package existence through an approved metadata source.
- [ ] Compare supported Python versions, operating systems, license, API surface and dependency footprint.
- [ ] Explain why each candidate was selected, with evidence and unknowns.
- [ ] Add Replacement Tournament scoring with transparent criteria and no unsupported claims.
- [ ] Check import/API compatibility where static inspection is feasible.
- [ ] Produce migration steps and rollback plan.
- [ ] Include “no safe replacement found” as a valid result.
- [ ] Test with real dependency cases from LinkWatch.

## 8. Isolated migration workflow

- [x] Disposable workspace copy helper exists and skips common caches/VCS/virtualenv folders.
- [x] Plan validator rejects unsupported action types and missing rationale.
- [ ] Prefer Git worktrees where repository state allows; otherwise create a well-defined disposable copy.
- [ ] Verify source tree remains unchanged using `git status` and hashes.
- [ ] Create a fresh isolated Python environment for baseline and candidate runs.
- [ ] Implement a strict command allowlist and deny arbitrary shell strings.
- [ ] Add subprocess timeouts, output-size limits, environment sanitization and process cleanup.
- [ ] Do not run untrusted code on the host; use a permitted sandbox/container if available.
- [ ] Apply candidate edits only in the disposable workspace.
- [ ] Capture complete patch/diff and rollback data.
- [ ] Record install failures, resolver conflicts and environment differences.
- [ ] Add explicit cleanup command and retention policy for temporary workspaces.
- [ ] Test failure paths: invalid path, disk full, permission error, interrupted command and cleanup failure.

## 9. Verification and behavioural comparison

- [x] Result-summary comparison helper compares exit code and pass/fail/skip counts when supplied.
- [ ] Implement a baseline test runner.
- [ ] Implement candidate test runner with the same declared environment and timeout.
- [ ] Capture stdout, stderr, exit code, duration, timeout and collection errors.
- [ ] Compare dependency-resolution output and import smoke tests.
- [ ] Run existing LinkWatch tests before and after migration.
- [ ] Add targeted regression tests for dependency call sites.
- [ ] Compare selected outputs/contracts, not only aggregate test counts.
- [ ] Report skipped tests and environment mismatches.
- [ ] Distinguish `passed`, `failed`, `timed_out`, `not_run`, and `inconclusive`.
- [ ] Never claim that passing tests prove complete behavioral equivalence.
- [ ] Add deterministic tests for comparison statuses and missing evidence.

## 10. Adaptive regression testing

- [x] Basic heuristic can propose reviewing tests associated with observed usage files.
- [ ] Find existing tests covering dependency call sites.
- [ ] Ask Gemma for candidate test ideas grounded in usage evidence.
- [ ] Require human review before writing/accepting generated test code.
- [ ] Run proposed tests only in isolated workspaces.
- [ ] Track which regression tests were model-suggested, human-edited, passed, failed or skipped.
- [ ] Avoid claiming coverage improvement without a coverage measurement.

## 11. Dependency Exit Capsule

- [x] JSON output implemented.
- [x] Markdown output implemented.
- [x] Contains dependency declarations, manifest hashes, usage, indicators, metadata status and explicit limitations.
- [x] Contains placeholder fields for replacement and verification status.
- [ ] Add schema validation and schema-version migration.
- [ ] Include complete evidence references and source URLs.
- [ ] Include recommended replacement, rationale, migration steps and rollback.
- [ ] Include suggested tests separately from tests actually executed.
- [ ] Include baseline/candidate commands and full outcomes.
- [ ] Include compatibility gaps, unresolved questions and human approvals.
- [ ] Add artifact download/export in frontend.
- [ ] Add reproducible capsule test fixtures and snapshot tests.

## 12. Frontend UI/UX

- [x] React/Vite app created with dark theme and navigation.
- [x] Overview page includes local repository scan form and displays returned dependency list.
- [x] Dependency Explorer page scaffold exists.
- [x] Migration Workbench page scaffold exists with safety messaging.
- [x] Verification Center page scaffold exists.
- [x] Exit Capsule page scaffold exists.
- [x] API helper for scan and capsule endpoints exists.
- [ ] Add API health status and actionable connection errors.
- [ ] Add scan loading/progress, cancellation and empty/error states.
- [ ] Build dependency table with search, sort, filters, groups and detail drawer.
- [ ] Show usage evidence, manifest location and risk rationale per dependency.
- [ ] Display metadata source, timestamp and unknown fields.
- [ ] Display Gemma recommendations with evidence references and confidence/uncertainty.
- [ ] Add replacement candidate comparison view.
- [ ] Add migration plan review/approval before execution.
- [ ] Show baseline vs candidate test results and diffs.
- [ ] Show command logs, environment and changed files.
- [ ] Implement capsule preview and JSON/Markdown download.
- [ ] Add keyboard accessibility, responsive layout, focus states and readable contrast.
- [ ] Ensure UI labels placeholders clearly; never imply an unimplemented operation succeeded.
- [ ] Remove or self-host external font requests if internet-independent demo is required.

## 13. API, validation and reliability

- [x] Basic FastAPI routes and Pydantic request models exist.
- [ ] Add typed response models for scan, metadata, migration plan, verification and capsule.
- [ ] Add consistent exception handling and request validation.
- [ ] Restrict filesystem paths to user-selected workspaces and validate path boundaries.
- [ ] Add request size/time limits and safe logging.
- [ ] Add CORS configuration restricted to the local frontend origin.
- [ ] Add API integration tests with temporary repositories.
- [ ] Add tests for invalid paths, malformed manifests and empty repositories.
- [ ] Add API health checks and version endpoint.
- [ ] Add a reproducible setup script or Makefile.

## 14. Testing and quality

- [x] Initial unit tests authored for scanner, import usage, risk indicators and capsule output.
- [ ] Run all tests under Python 3.12.
- [ ] Add unit tests for metadata parsing, candidate validation, workspace isolation and equivalence comparison.
- [ ] Add route-level tests using FastAPI TestClient.
- [ ] Add regression fixtures from LinkWatch.
- [ ] Add static linting/type checks if time allows.
- [ ] Test on a clean clone and document exact setup commands.
- [ ] Check all generated reports for deterministic fields where practical.
- [ ] Do not mark a feature complete until tests pass and evidence exists.

## 15. Documentation, open source and hackathon submission

- [x] README includes setup, CLI/API instructions, known limitations and safety notes.
- [x] MIT license included.
- [x] `.gitignore` excludes environments, secrets and generated artifacts.
- [x] Model integration is not falsely claimed as complete.
- [ ] Add architecture diagram, demo workflow and screenshots.
- [ ] Add example capsule from a real scan of LinkWatch, with no private files/secrets.
- [ ] Add demo script and expected output.
- [ ] Add model card/disclosure and inference-method details once selected.
- [ ] Ensure public repo has meaningful incremental commits and correct organizer-required naming.
- [ ] Confirm fork/starter lineage requirement with organizers.
- [ ] Include team/contributor attribution as required.
- [ ] Verify no API keys, secrets, private repository data or generated environments are committed.
- [ ] Run all tests and a complete clean-clone demo before submission.

## 16. Suggested execution order

1. [ ] Run the starter tests and fix any failures.
2. [ ] Scan the actual LinkWatch checkout and inspect the report.
3. [ ] Add fixture-based scanner tests and improve manifest coverage based on LinkWatch.
4. [ ] Confirm the allowed Gemma 4 runtime with organizers, then implement the adapter.
5. [ ] Add metadata enrichment with provenance and mocked tests.
6. [ ] Implement one complete replacement case from scan → recommendation → isolated patch.
7. [ ] Implement controlled baseline/candidate test execution and result capture.
8. [ ] Complete capsule evidence and frontend views.
9. [ ] Add one end-to-end demo and document honest limitations.
10. [ ] Add P1/P2 features only after the P0 path works end to end.

## Safety constraints to preserve

- Never mutate the original LinkWatch working tree during migration experiments.
- Never execute raw model-generated commands.
- Never claim that static import absence proves a dependency is unused.
- Never claim tests prove complete behavioral equivalence.
- No vulnerability scanning in the scoring-critical path: the event brief says vulnerabilities do not count toward scoring.
- Confirm whether network metadata access and hosted/local Gemma inference are permitted by event rules.
