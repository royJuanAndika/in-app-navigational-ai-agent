#!/usr/bin/env python

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_html_path(nkg_path: Path, nkg_obj: dict[str, Any], explicit_html: str | None) -> Path:
    repo_root = Path(__file__).resolve().parent.parent

    candidates: list[Path] = []

    if explicit_html:
        candidates.append(Path(explicit_html))

    source_html = nkg_obj.get("meta", {}).get("source_html")
    if isinstance(source_html, str) and source_html.strip():
        source_path = Path(source_html)
        candidates.append(source_path)
        candidates.append(repo_root / source_path.name)

    filename = nkg_obj.get("meta", {}).get("filename")
    if isinstance(filename, str) and filename.strip():
        candidates.extend(
            [
                repo_root / "data" / "cleaned_html" / filename,
                repo_root / "data" / "scraped_html" / filename,
                repo_root / "data" / "actual_raw_html" / filename,
            ]
        )

    candidates.append(nkg_path.with_suffix(".html"))

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    searched = "\n".join(f"- {path}" for path in candidates)
    raise FileNotFoundError(f"Could not resolve source HTML for {nkg_path}. Searched:\n{searched}")


def extract_html_texts(nkg_obj: dict[str, Any], html_path: Path) -> dict[str, Any]:
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    nkg = nkg_obj.setdefault("nkg", {})
    elements = nkg.get("elements", [])

    matched_count = 0
    text_count = 0

    for element in elements:
        if not isinstance(element, dict):
            continue

        selector = element.get("selector")
        if not isinstance(selector, str) or not selector.strip():
            continue

        try:
            matches = soup.select(selector)
        except Exception:
            element["html_text"] = element.get("html_text", "") or ""
            continue

        if not matches:
            element["html_text"] = element.get("html_text", "") or ""
            continue

        matched_count += 1
        text = matches[0].get_text(" ", strip=True)
        if text:
            text_count += 1
        element["html_text"] = text

    nkg_obj.setdefault("meta", {})
    nkg_obj["meta"]["html_text_source"] = str(html_path)
    nkg_obj["meta"]["html_text_matched_elements"] = matched_count
    nkg_obj["meta"]["html_text_non_empty_elements"] = text_count
    return nkg_obj


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract rendered text for every NKG element selector and store it as html_text"
    )
    parser.add_argument("--input", required=True, help="Path to the .nkg.json file")
    parser.add_argument(
        "--output",
        default="",
        help="Output path (default: write to <input>.html_text.json)",
    )
    parser.add_argument(
        "--html",
        default="",
        help="Optional explicit HTML file path. If omitted, the script tries source_html and local data folders.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    nkg_path = Path(args.input).resolve()
    if not nkg_path.exists():
        raise FileNotFoundError(f"Input not found: {nkg_path}")

    nkg_obj = load_json(nkg_path)
    html_path = resolve_html_path(nkg_path=nkg_path, nkg_obj=nkg_obj, explicit_html=args.html or None)

    updated = extract_html_texts(nkg_obj, html_path)

    output_path = Path(args.output).resolve() if args.output else nkg_path.with_name(f"{nkg_path.stem}.html_text.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(output_path, updated)

    print(f"saved: {output_path}")
    print(f"html: {html_path}")
    print(f"elements with selector match: {updated.get('meta', {}).get('html_text_matched_elements', 0)}")
    print(f"elements with non-empty text: {updated.get('meta', {}).get('html_text_non_empty_elements', 0)}")


if __name__ == "__main__":
    main()