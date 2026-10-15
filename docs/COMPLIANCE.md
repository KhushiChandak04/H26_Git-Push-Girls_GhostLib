# GhostLib vs. the hackathon problem statement (Track 1: Gemma 4, Dependency Resilience)

This is an honest audit. It's based on run `20261015T082337Z-f52f393` of the organizer's repository
[rishrek/LinkWatch](https://github.com/rishrek/LinkWatch) at commit `f52f393`. Everything below can be regenerated with
the commands in the README. Nothing is hard-coded.

## Track 1 requirements

| # | Requirement (problem statement) | Status | Where to see it |
|---|---|---|---|
| — | Works on the organizer-provided repository; analysis is dynamic | ✅ | Scans a local clone or the GitHub URL; every value comes from the scan, PyPI or executed commands |
| — | Python 3.12 and 3.13, not 3.14 | ✅ | GhostLib's tests pass on 3.12.14 and 3.13.7; experiments run on either (`--python`) |
| — | Gemma 4 is a meaningful part, with model / version / access / terms documented | ✅ | README "Gemma 4 configuration"; capsule `ai.calls` audit trail (model version returned by the API, tokens, latency, prompt hash) |
| 1 | Identify potentially at-risk dependencies from repository and dependency metadata | ✅ | 14 transparent rules over manifests, AST and PyPI → Overview ranking + "Where do these risk scores come from?" |
| 2 | For all identified dependencies, determine where and how each is used | ✅ | All 14 packages: file, line, import statement, symbols used, private-API use, relevant tests |
| 3 | Propose a suitable replacement and migration approach for all identified dependencies | ✅ | Gemma 4 recommendations for **14/14** packages, each schema-validated and checked against PyPI or the stdlib |
| 4 | Where feasible, execute tests against the original and the proposed replacement | ✅ | Baseline vs candidate pytest for **10/10** at-risk packages, in disposable copies with separate virtualenvs (see results below) |
| 5 | Compare the observed results; identify compatibility gaps and unresolved risks | ✅ | Per-test before/after table, verdict sentence, installed-version diff, gaps list per package |
| 6 | Generate a reusable Dependency Exit Capsule | ✅ | `capsule.json` + `capsule.md` per run (download from the Capsule tab) |

### Capsule contents required by the problem statement

| Field | In the capsule |
|---|---|
| Dependency details | `dependencies[].declarations`, `metadata` (PyPI, sourced) |
| Risk indicators | `dependencies[].risk.indicators` (each with evidence type, evidence and points) |
| Usage locations | `dependencies[].usage.locations` (file, line, statement, symbols) |
| Proposed replacement | `dependencies[].recommendation` (AI-recommended) + `candidate_validation` |
| Migration steps | `recommendation.recommendation.migration_steps` + the experiment's `diff` |
| Suggested tests | `recommendation.recommendation.suggested_tests` + AI-written tests run separately |
| Executed test results | `experiment.baseline_run` / `candidate_run` (argv, exit codes, logs, per-test outcomes) |
| Compatibility gaps | `dependencies[].compatibility_gaps` |
| Open concerns and limitations | `open_concerns`, `limitations`, plus isolation limits and reproduce/rollback steps |
| AI separated from observed/verified | Every item carries one of OBSERVED / SOURCED / EXECUTION-VERIFIED / AI-RECOMMENDED / UNKNOWN |

## Experiment results (run `20261015T082337Z-f52f393`)

RESULTS_TABLE

## Known limitations (stated, not hidden)

- Experiments run in disposable copies with separate virtualenvs. They are **not a security sandbox**: tests run as
  the current user with network access.
- Passing tests do not prove behavioural equivalence. Example: Gemma's `requests` migration changes how a
  `charset=utf-8` header is handled, which LinkWatch's tests do not exercise. The reviewer caught this; the tests did not.
- The learning loop is a small bandit over executed outcomes, currently from one repository. It is an honest start,
  not a trained model.
- `setup.py` / `setup.cfg` / lockfiles are listed but not parsed.
