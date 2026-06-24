#!/usr/bin/env python3
"""Generate deterministic OKF wiki readers from solutions.manifest.json."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path


def rel(repo: Path, value: str) -> Path:
    return repo / value.replace("\\", "/")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def markdown_to_html(text: str) -> str:
    out: list[str] = []
    in_list = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("# "):
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h1>{html.escape(line[2:].strip())}</h1>")
        elif line.startswith("## "):
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h2>{html.escape(line[3:].strip())}</h2>")
        elif line.startswith("- "):
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append(f"<li>{html.escape(line[2:].strip())}</li>")
        elif line.strip():
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<p>{html.escape(line.strip())}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def page(title: str, body: str) -> str:
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        f"  <title>{html.escape(title)}</title>",
        '  <style>body{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;line-height:1.5} code{background:#f3f3f3;padding:.1rem .25rem}</style>',
        "</head>",
        "<body>",
        body,
        "</body>",
        "</html>",
        "",
    ])


def expected_outputs(repo: Path, manifest: dict) -> dict[Path, str]:
    outputs: dict[Path, str] = {}
    links = []
    for solution in manifest.get("solutions", []):
        docs = solution["docs"]
        required = [docs["routing_guidance_card"], docs["solution"], docs["routing"], docs["log"]]
        missing = [p for p in required if not rel(repo, p).exists()]
        if missing:
            raise FileNotFoundError(f"{solution['id']} missing OKF docs: {', '.join(missing)}")
        body = [f"<h1>{html.escape(solution['name'])}</h1>"]
        for key in ("routing_guidance_card", "solution", "routing", "log"):
            body.append(markdown_to_html(read(rel(repo, docs[key]))))
        wiki_path = rel(repo, docs["wiki"])
        outputs[wiki_path] = page(f"{solution['name']} OKF Wiki", "\n".join(body))
        links.append(f"- [{solution['name']}]({docs['wiki']})")
    index_md = "# OKF Wiki Index\n\n" + "\n".join(links) + "\n"
    outputs[rel(repo, manifest["wiki"].get("index", "docs/okf/index.md"))] = index_md
    outputs[rel(repo, manifest["wiki"].get("umbrella", "documentation/wiki.html"))] = page("OKF Wiki", markdown_to_html(index_md))
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--browser-smoke", action="store_true")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    manifest = json.loads(read(repo / "documentation" / "solutions.manifest.json"))
    outputs = expected_outputs(repo, manifest)
    stale: list[str] = []
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or read(path) != content:
                stale.append(str(path.relative_to(repo)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    if args.browser_smoke:
        for path, content in outputs.items():
            if path.suffix == ".html" and "<html" not in content.lower():
                raise RuntimeError(f"bad html output: {path}")
    if stale:
        print("OKF generated files are stale:")
        for item in stale:
            print(f"- {item}")
        return 1
    print("OKF wiki build check passed." if args.check else "OKF wiki build complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
