# GhostLib — demo flow (about 3 minutes)

## Before you present (5 minutes earlier)

```bash
uvicorn app.main:app --app-dir backend --port 8000     # terminal 1
npm --prefix frontend run dev                          # terminal 2 → http://localhost:5173
ghostlib ai-check                                      # must say "available"
```

- Open the dashboard. Under **Overview → Previous runs**, click the run that has experiments
  (e.g. `20261015T082337Z-…`). Its PyPI data is cached, so everything loads instantly.
- Keep a third terminal open in the repo for the CLI moment.
- **Fallback:** if the Wi-Fi or Gemma fails, every screen still works from saved runs, and AI panels say
  `AI_UNAVAILABLE` instead of inventing anything.

---

## The flow

| Time | Tab | What you do | What you say |
|---|---|---|---|
| 0:00 | Overview hero | Nothing | "Most tools tell you a library is risky. GhostLib shows the evidence, tests a replacement on a copy of your project, and tells you exactly what was proven and what wasn't." |
| 0:15 | Overview → scan | Point at the path to the organizer's **LinkWatch** clone and the run's commit `f52f393` | "This is a real scan of the organizer's repo. Nothing here is pre-written." |
| 0:25 | Overview → Haunted packages | Point at **pydantic: high · 6** | "Ranked by rules. pydantic is pinned `==1.10.13` in one file and `>=2` in another." |
| 0:35 | Overview → *Where do these risk scores come from?* | Scroll the rule table | "Scores come from **14 fixed rules**, using data from the code and PyPI. **Gemma never scores anything.** Every chip tells you how we know: Observed, Sourced, Verified, AI, Unknown." |
| 0:55 | Dependencies → `requests` | Click it and show the highlighted line and the **private API** tag | "Exact file and line. LinkWatch calls a private `requests` function. That breaks silently on upgrades." |
| 1:10 | Migration → `toml` | Show step **1 Choose**: Gemma's summary and the cards | "Now Gemma 4 suggests replacements, using only the evidence we collected. The AI chip means: a suggestion, not a fact. GhostLib then checks each suggestion: `tomllib` really is built into Python." |
| 1:30 | Migration → `jinja2` | Show steps **2 Review → 3 Test → 4 Adopt** | "We review the exact change. *Run tests on a copy* installs old and new versions in two temporary folders and runs the project's own tests. The real repo is never touched, and adopting the change is your call, in VS Code or with `git apply`." |
| 1:55 | Verification → `jinja2` | Read the green sentence and the first table row | "**Nothing new broke, and it fixes a test that was failing.** The old Jinja2 crashes with modern markupsafe; the new one passes. Verified by running it." |
| 2:15 | Verification → `toml` | Show the AI-tests box and *What is still not proven* | "Honesty: Gemma's own test had a bug (a missing `import`). We ran it separately, so it couldn't hide the real result. And we flag that the project still allows Python 3.10, where `tomllib` doesn't exist." |
| 2:35 | Overview → *What GhostLib has learned* | Show the table of past experiments | "It learns. Every experiment, on any repo, becomes experience: a reward from real test results. The more repos it tests, the better it ranks risky packages and picks fixes." |
| 2:45 | Terminal | `ghostlib learn` (or show the `ghostlib auto` log) | "Same engine as a CLI. `ghostlib auto` scans, ranks, asks Gemma, chooses with what it learned, prepares diffs, and **stops for human approval**." |
| 2:55 | Capsule | Click **Export capsule.md** | "And everything is saved in a Dependency Exit Capsule, a reusable record of what we observed, what AI suggested, what we tested, and what's still unproven." |

## Likely questions

- **"Is this RL?"** It's a multi-armed bandit, a small, explainable reinforcement-learning setup. The reward comes only
  from executed tests. It re-weights the transparent rule score; it never replaces it. It's an honest start, not a
  trained model.
- **"Is it safe to run tests?"** Disposable copies, separate virtualenvs, no shell, timeouts, and keys stripped from the
  environment. It is **not** a security sandbox, and we say so in every report.
- **"Why not just trust Gemma?"** We showed it writing a buggy test. That's exactly why every AI output is
  labelled and checked by execution.
- **"Website or CLI?"** Both: one engine. The dashboard runs locally next to your code; the CLI suits scripts and CI.
