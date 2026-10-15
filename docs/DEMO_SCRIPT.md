# GhostLib — 3-minute demo script

**Before the demo:** start the backend and the frontend, and confirm `ghostlib ai-check` says `available`.
Run one scan in advance so the PyPI cache is warm.

```bash
uvicorn app.main:app --app-dir backend --port 8000
npm --prefix frontend run dev        # http://localhost:5173
```

---

**0:00 Pitch (15 s).** "Most tools tell you a library is risky. GhostLib shows you the evidence, experiments with a
replacement, and tells you exactly what was proven and what remains uncertain. Everything is labelled Observed,
Sourced, Execution-verified, AI-recommended, or Unknown."

**0:15 Scan the real LinkWatch repo (30 s).** In Overview, paste the path to the LinkWatch clone and click **Run scan**.
- Point at the commit hash and remote URL. This is the organizer's repo, scanned live.
- Point at the ranking: pydantic is high risk, and the indicators explain why.
- Under **Repository findings**, show that `certifi` is imported but never declared, and that pydantic is declared
  `==1.10.13` in one file and `>=2` in another. Both are Observed.

**0:45 Evidence, not vibes (30 s).** Click `requests` in the ranking.
- Show the **private API** `_parse_content_type_header` and the monkey-patched `Session.request`.
- Click a usage row. The source viewer opens at that exact line.
- Click `toml`. The Sourced PyPI facts show the last release was 2020-11-01, with no 3.12/3.13 classifiers.
- Note the disclaimer: "not proof of abandonment".

**1:15 Gemma 4 (30 s).** Open the Migration Workbench, select `toml`, and click **Ask Gemma 4**.
- The purple dashed box is AI-recommended. Show the candidate (`tomllib`, stdlib), the steps, the suggested tests
  and the model's own uncertainties.
- Show the **validation** checks underneath: GhostLib confirmed `tomllib` exists in the stdlib on the running Python.
  That proves the module exists, not that the migration is compatible.

**1:45 Flight Simulator (45 s).** Select `jinja2` and choose *Upgrade to latest PyPI release*, then click
**Propose change**.
- The diff updates two manifests. Nothing has executed yet.
- Tick "I reviewed this diff" and click **Approve & run**. It takes about 40 s; talk while it runs:
  "Disposable copy, separate uv venv, fixed argv commands with timeouts, keys stripped from the environment. It is
  not a sandbox, and we say so."
- *(If time is short, open the jinja2 experiment that already ran.)*

**2:30 Verification (20 s).** Open the Verification Center.
- The baseline shows 9 passed, 1 failed: Jinja2 2.11.3 breaks with modern markupsafe (`soft_unicode`).
- The candidate shows 10 passed: one test fixed, zero regressions.
- The original repository is unchanged, checked against git status and manifest hashes.
- Read the caveat: passing tests are not proof of equivalence.

**2:50 Capsule (10 s).** Open Exit Capsule and download `capsule.md` / `capsule.json`. Every claim is labelled, and
the report includes compatibility gaps (e.g. "not executed on Python 3.13"), reproduction steps and rollback.

## Backup lines
- *No Gemma key or quota?* The UI shows `AI_UNAVAILABLE` and never invents output. The deterministic upgrade and
  remove experiments still work.
- *Why not a single risk score from the AI?* The score is a visible rule sum. Each point links to evidence.
