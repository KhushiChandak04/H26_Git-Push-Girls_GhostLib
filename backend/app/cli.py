"""GhostLib command-line interface."""
import argparse
import json
from pathlib import Path
from app.services.scanner import scan_repository
from app.services.capsule import build_capsule, write_capsule
from app.services.metadata import get_package_metadata


def main():
    parser = argparse.ArgumentParser(description="Scan Python dependency manifests and create an Exit Capsule.")
    parser.add_argument("repository", type=Path, help="Path to the local repository")
    parser.add_argument("--out", type=Path, default=Path("artifacts"), help="Capsule output directory")
    parser.add_argument("--fetch-metadata", action="store_true",
                        help="Fetch PyPI metadata (network access; use only if event rules permit)")
    args = parser.parse_args()

    result = scan_repository(args.repository)
    metadata = {}
    if args.fetch_metadata:
        for dep in result["dependencies"]:
            name = dep.get("normalized_name")
            if name and name not in metadata:
                metadata[name] = get_package_metadata(name, allow_network=True)
    capsule = build_capsule(result, metadata)
    files = write_capsule(capsule, args.out)
    print(json.dumps({
        "repository": result["repository"],
        "manifest_count": len(result["manifests"]),
        "dependency_declarations": len(result["dependencies"]),
        "usage_entries": len(result["usage"]),
        "capsule_files": files,
        "warnings": result["warnings"],
    }, indent=2))


if __name__ == "__main__":
    main()
