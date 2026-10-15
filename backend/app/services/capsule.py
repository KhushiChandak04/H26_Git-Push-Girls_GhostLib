"""Dependency Exit Capsule builder and JSON/Markdown writer."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from app.services.risk_engine import assess_dependency


def build_capsule(scan_result: dict, metadata: dict | None = None) -> dict:
    metadata = metadata or {}
    dependencies = []
    for dep in scan_result.get("dependencies", []):
        package_key = dep.get("normalized_name") or dep.get("name", "").lower()
        dependencies.append({
            **dep,
            "assessment": assess_dependency(dep, scan_result.get("python_requirement")),
            "metadata": metadata.get(package_key, {
                "status": "not_fetched",
                "reason": "Metadata enrichment has not been run for this package.",
            }),
            "replacement": {"status": "not_assessed", "candidate": None, "rationale": None, "migration_steps": []},
            "verification": {"status": "not_run", "baseline": None, "candidate": None, "compatibility_gaps": []},
        })
    return {
        "schema_version": "0.2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": scan_result.get("repository"),
        "python_requirement": scan_result.get("python_requirement"),
        "manifest_files": scan_result.get("manifests", []),
        "dependencies": dependencies,
        "evidence_status": "partial",
        "warnings": scan_result.get("warnings", []),
        "limitations": scan_result.get("limitations", []),
        "open_concerns": [
            "Replacement candidates have not been evaluated.",
            "Gemma 4 recommendations are not configured.",
            "No baseline/candidate migration tests have been executed.",
            "Metadata may be absent; inspect per-package metadata status.",
        ],
    }


def capsule_markdown(capsule: dict) -> str:
    lines = [
        "# Dependency Exit Capsule", "",
        f"- Generated: {capsule.get('generated_at')}",
        f"- Project: `{capsule.get('project')}`",
        f"- Evidence status: **{capsule.get('evidence_status')}**",
        f"- Python requirement: `{capsule.get('python_requirement') or 'not declared'}`", "",
        "## Manifest files", "",
    ]
    for manifest in capsule.get("manifest_files", []):
        if isinstance(manifest, str):
            lines.append(f"- `{manifest}`")
        else:
            lines.append(f"- `{manifest.get('path')}` ({manifest.get('type')}, SHA-256 `{manifest.get('sha256')}`)")
    lines += ["", "## Dependencies", ""]
    if not capsule.get("dependencies"):
        lines.append("No dependency declarations were found in the supported manifests.")
    for dep in capsule.get("dependencies", []):
        usage = dep.get("usage") or {}
        assessment = dep.get("assessment") or {}
        metadata = dep.get("metadata") or {}
        lines += [
            f"### {dep.get('name')}",
            f"- Constraint: `{dep.get('specifier') or '(none parsed)'}`",
            f"- Manifest: `{dep.get('source')}`" + (f", line {dep['line']}" if dep.get("line") else ""),
            f"- Static usage: `{usage.get('status', 'unknown')}`; files: {', '.join(f'`{p}`' for p in usage.get('files', [])) or 'none observed'}",
            f"- Assessment: `{assessment.get('risk_status', 'unknown')}`",
            f"- Metadata: `{metadata.get('status', 'unknown')}`",
            "- Replacement: not assessed",
            "- Verification: not run", "",
        ]
        for indicator in assessment.get("indicators", []):
            lines.append(f"  - Indicator `{indicator['indicator']}` ({indicator['severity']}): {indicator['evidence']}")
        lines.append("")
    lines += ["## Warnings", ""] + [f"- {item}" for item in capsule.get("warnings", [])]
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in capsule.get("limitations", [])]
    lines += ["", "## Open concerns", ""] + [f"- {item}" for item in capsule.get("open_concerns", [])]
    return "\n".join(lines).rstrip() + "\n"


def write_capsule(capsule: dict, output_dir: Path | str) -> list[str]:
    out = Path(output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "dependency-exit-capsule.json"
    md_path = out / "dependency-exit-capsule.md"
    json_path.write_text(json.dumps(capsule, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(capsule_markdown(capsule), encoding="utf-8")
    return [str(json_path), str(md_path)]
