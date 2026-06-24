#!/usr/bin/env python3
"""Map changed paths to OKF solutions using documentation/solutions.manifest.json."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def norm(value: str) -> str:
    value = value.strip().replace("\\", "/")
    return value[2:] if value.startswith("./") else value


def is_match(path: str, owned: str) -> bool:
    owned = norm(owned)
    path = norm(path)
    if owned.endswith("/"):
        return path.startswith(owned)
    return path == owned or path.startswith(owned + "/")


def git_paths(repo: Path) -> list[str]:
    commands = [
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ]
    found: list[str] = []
    for command in commands:
        result = subprocess.run(command, cwd=repo, text=True, capture_output=True, check=False)
        if result.returncode == 0:
            found.extend(p for p in result.stdout.splitlines() if p.strip())
    return sorted(set(found))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    manifest_path = repo / "documentation" / "solutions.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = [norm(p) for p in (args.paths or git_paths(repo))]
    excluded_prefixes = [norm(p) for p in manifest.get("excluded_paths", [])]
    result = {"manifest": str(manifest_path), "matched": [], "excluded": [], "unmapped": [], "ambiguous": []}
    for path in paths:
        if any(is_match(path, prefix) for prefix in excluded_prefixes):
            result["excluded"].append(path)
            continue
        matches = [s for s in manifest.get("solutions", []) if any(is_match(path, p) for p in s.get("owned_paths", []))]
        if len(matches) == 1:
            s = matches[0]
            result["matched"].append({"path": path, "solution_id": s["id"], "docs": s["docs"]})
        elif len(matches) > 1:
            result["ambiguous"].append({"path": path, "solution_ids": [s["id"] for s in matches]})
        else:
            result["unmapped"].append(path)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
