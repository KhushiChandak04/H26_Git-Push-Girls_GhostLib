# Evidence: Dependency Exit Capsule for LinkWatch

These files are the **unedited output** of GhostLib run `20261015T082337Z-f52f393` on the organizer's repository
[rishrek/LinkWatch](https://github.com/rishrek/LinkWatch) at commit `f52f3930c8e7c33d934ccf614955a38e26984bd5`.
They are copied from `artifacts/runs/<run-id>/capsule/`, which is git-ignored.

| File | What it is |
|---|---|
| [`capsule.md`](capsule.md) | Human-readable report |
| [`capsule.json`](capsule.json) | Machine-readable capsule (schema 1.0) |

What it contains:
- 14 dependencies, each with its risk indicators, usage locations and PyPI facts.
- Gemma 4 recommendations for all 14.
- Baseline-vs-candidate test executions for all 10 at-risk dependencies.
- An audit trail of all 23 Gemma 4 calls.
- Compatibility gaps, open concerns and limitations.

Every statement is labelled OBSERVED, SOURCED, EXECUTION-VERIFIED, AI-RECOMMENDED or UNKNOWN.

Paths inside the files (e.g. `C:\Users\...\targets\LinkWatch`) are from the machine that produced the run. To
regenerate the evidence on your own machine, follow the README; your results will carry your own paths and
timestamps:

```bash
ghostlib scan targets/LinkWatch --recommend
ghostlib experiment <run-id> <package> --approve
ghostlib capsule <run-id>
```

Summary table and requirement mapping: [../COMPLIANCE.md](../COMPLIANCE.md).
