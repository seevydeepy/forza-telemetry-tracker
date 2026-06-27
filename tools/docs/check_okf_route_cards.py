#!/usr/bin/env python3
"""Check OKF routing cards are usable as first-hop route-pack entries."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DOC_ROOT_PREFERENCES = ("docs", "documentation", "doc", "wiki", "manual", "manuals")
SIMILAR_DOC_TOKENS = ("doc", "wiki", "manual")
SECTION_NAMES = ("owned_paths", "read_first", "keywords", "handoffs", "validation", "stale_notes")


def norm(value: str) -> str:
    return value.strip().replace("\\", "/").lstrip("./")


def find_manifest(repo: Path) -> Path:
    for root in DOC_ROOT_PREFERENCES:
        path = repo / root / "solutions.manifest.json"
        if path.exists():
            return path
    for path in sorted(repo.glob("*/solutions.manifest.json")):
        if any(token in path.parent.name.lower() for token in SIMILAR_DOC_TOKENS):
            return path
    raise FileNotFoundError("could not find solutions.manifest.json in a docs/documentation-like folder")


def scalar(text: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", text, re.M)
    return match.group(1).strip() if match else ""


def section_values(lines: list[str], section: str) -> list[str]:
    values: list[str] = []
    collecting = False
    section_header = f"{section}:"
    for raw in lines:
        line = raw.strip()
        if line == section_header:
            collecting = True
            continue
        if collecting and re.match(r"^[A-Za-z_][A-Za-z0-9_]*:\s*$", line):
            break
        if collecting and line.startswith("- "):
            values.append(line[2:].strip())
    return values


def check_card(repo: Path, solution: dict, errors: list[str]) -> None:
    docs = solution.get("docs") or {}
    card_rel = norm(str(docs.get("routing_guidance_card") or ""))
    solution_rel = norm(str(docs.get("solution") or ""))
    if not card_rel:
        errors.append(f"{solution.get('id', '<unknown>')}: missing docs.routing_guidance_card")
        return
    card_path = repo / card_rel
    if not card_path.exists():
        errors.append(f"{solution.get('id', '<unknown>')}: missing routing card {card_rel}")
        return

    text = card_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    sid = str(solution.get("id") or "").strip()
    if scalar(text, "id") != sid:
        errors.append(f"{card_rel}: id does not match manifest solution id {sid}")

    sections = {name: section_values(lines, name) for name in SECTION_NAMES}
    for name, values in sections.items():
        if not values:
            errors.append(f"{card_rel}: missing non-empty {name} section")

    owned = [norm(p) for p in solution.get("owned_paths", [])]
    card_owned = [norm(p) for p in sections["owned_paths"]]
    missing_owned = [p for p in owned if p not in card_owned]
    if missing_owned:
        errors.append(f"{card_rel}: owned_paths missing manifest paths {missing_owned}")

    read_first = [norm(p) for p in sections["read_first"]]
    expected_first = [card_rel, solution_rel]
    if read_first[:2] != expected_first:
        errors.append(f"{card_rel}: read_first must start with {expected_first}")

    keywords = [str(k).strip() for k in solution.get("routing_keywords", []) if str(k).strip()]
    card_keywords = sections["keywords"]
    missing_keywords = [k for k in keywords if k not in card_keywords]
    if not keywords:
        errors.append(f"{card_rel}: manifest routing_keywords is empty")
    elif missing_keywords:
        errors.append(f"{card_rel}: keywords missing manifest terms {missing_keywords}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check OKF routing-card completeness.")
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    manifest_path = find_manifest(repo)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for solution in manifest.get("solutions", []):
        check_card(repo, solution, errors)
    if errors:
        print("OKF route-card check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("OKF route-card check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
