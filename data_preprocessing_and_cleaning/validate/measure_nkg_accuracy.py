#!/usr/bin/env python

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_dom_ids(html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    ids: set[str] = set()
    for tag in soup.find_all(attrs={"id": True}):
        dom_id = str(tag.get("id", "")).strip()
        if dom_id:
            ids.add(dom_id)
    return ids


def resolve_html_path(repo_root: Path, nkg_path: Path, nkg_obj: dict[str, Any]) -> Path:
    meta = nkg_obj.get("meta", {}) if isinstance(nkg_obj.get("meta"), dict) else {}
    filename = str(meta.get("filename", "")).strip()
    source_html = str(meta.get("source_html", "")).strip()

    candidates: list[Path] = []

    if source_html:
        raw_source = Path(source_html)
        candidates.append(raw_source)
        if raw_source.name:
            candidates.append(repo_root / "data" / "cleaned_html_2" / raw_source.name)
            candidates.append(repo_root / "data" / "cleaned_html" / raw_source.name)
            candidates.append(repo_root / "data" / "actual_raw_html" / raw_source.name)
            candidates.append(repo_root / "data" / "scraped_html" / raw_source.name)

    if filename:
        candidates.append(repo_root / "data" / "cleaned_html_2" / filename)
        candidates.append(repo_root / "data" / "cleaned_html" / filename)
        candidates.append(repo_root / "data" / "actual_raw_html" / filename)
        candidates.append(repo_root / "data" / "scraped_html" / filename)

    candidates.append(nkg_path.with_suffix(".html"))

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    attempted = "\n".join(str(p) for p in candidates)
    raise FileNotFoundError(f"Could not resolve HTML for {nkg_path}\nAttempted:\n{attempted}")


def compute_selector_metrics(soup: BeautifulSoup, elements: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    valid_single = 0
    not_found = 0
    invalid = 0
    ambiguous = 0
    missing_selector = 0

    for element in elements:
        if not isinstance(element, dict):
            continue

        total += 1
        selector = str(element.get("selector", "")).strip()
        if not selector:
            missing_selector += 1
            continue

        try:
            matches = soup.select(selector)
        except Exception:
            invalid += 1
            continue

        if len(matches) == 1:
            valid_single += 1
        elif len(matches) == 0:
            not_found += 1
        else:
            ambiguous += 1

    strict_fail = not_found + invalid + ambiguous + missing_selector
    executable_fail = not_found + invalid
    strict_accuracy = (valid_single / total * 100.0) if total else 100.0
    executable_accuracy = ((total - executable_fail) / total * 100.0) if total else 100.0

    return {
        "total_elements": total,
        "valid_single": valid_single,
        "not_found": not_found,
        "invalid": invalid,
        "ambiguous": ambiguous,
        "missing_selector": missing_selector,
        "strict_fail": strict_fail,
        "executable_fail": executable_fail,
        "strict_accuracy_percent": round(strict_accuracy, 2),
        "executable_accuracy_percent": round(executable_accuracy, 2),
    }


def evaluate_file(repo_root: Path, nkg_path: Path) -> dict[str, Any]:
    nkg_obj = load_json(nkg_path)
    html_path = resolve_html_path(repo_root=repo_root, nkg_path=nkg_path, nkg_obj=nkg_obj)
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")

    dom_ids = parse_dom_ids(html)
    nkg = nkg_obj.get("nkg", {}) if isinstance(nkg_obj.get("nkg"), dict) else {}
    elements = [e for e in nkg.get("elements", []) if isinstance(e, dict)]

    element_ids = {str(e.get("id", "")).strip() for e in elements if str(e.get("id", "")).strip()}
    dom_ids_in_nkg = sorted(x for x in element_ids if x in dom_ids)
    missing_dom_ids = sorted(x for x in dom_ids if x not in element_ids)

    coverage_accuracy = (len(dom_ids_in_nkg) / len(dom_ids) * 100.0) if dom_ids else 100.0
    selector_metrics = compute_selector_metrics(soup=soup, elements=elements)

    return {
        "file": nkg_path.name,
        "nkg_path": str(nkg_path.relative_to(repo_root)).replace("\\", "/"),
        "html_path": str(html_path.relative_to(repo_root)).replace("\\", "/") if html_path.is_relative_to(repo_root) else str(html_path),
        "coverage": {
            "dom_ids_total": len(dom_ids),
            "dom_ids_in_nkg_total": len(dom_ids_in_nkg),
            "missing_dom_ids_total": len(missing_dom_ids),
            "coverage_accuracy_percent": round(coverage_accuracy, 2),
            "missing_dom_ids": missing_dom_ids,
        },
        "selectors": selector_metrics,
    }


def aggregate(file_results: list[dict[str, Any]]) -> dict[str, Any]:
    dom_total = 0
    dom_in_nkg = 0
    missing_dom = 0

    total_elements = 0
    valid_single = 0
    not_found = 0
    invalid = 0
    ambiguous = 0
    missing_selector = 0

    for row in file_results:
        c = row["coverage"]
        s = row["selectors"]

        dom_total += c["dom_ids_total"]
        dom_in_nkg += c["dom_ids_in_nkg_total"]
        missing_dom += c["missing_dom_ids_total"]

        total_elements += s["total_elements"]
        valid_single += s["valid_single"]
        not_found += s["not_found"]
        invalid += s["invalid"]
        ambiguous += s["ambiguous"]
        missing_selector += s["missing_selector"]

    coverage_accuracy = (dom_in_nkg / dom_total * 100.0) if dom_total else 100.0
    strict_fail = not_found + invalid + ambiguous + missing_selector
    executable_fail = not_found + invalid
    strict_selector_accuracy = (valid_single / total_elements * 100.0) if total_elements else 100.0
    executable_selector_accuracy = ((total_elements - executable_fail) / total_elements * 100.0) if total_elements else 100.0

    return {
        "files_evaluated": len(file_results),
        "coverage": {
            "dom_ids_total": dom_total,
            "dom_ids_in_nkg_total": dom_in_nkg,
            "missing_dom_ids_total": missing_dom,
            "coverage_accuracy_percent": round(coverage_accuracy, 2),
        },
        "selectors": {
            "total_elements": total_elements,
            "valid_single": valid_single,
            "not_found": not_found,
            "invalid": invalid,
            "ambiguous": ambiguous,
            "missing_selector": missing_selector,
            "strict_fail": strict_fail,
            "executable_fail": executable_fail,
            "strict_accuracy_percent": round(strict_selector_accuracy, 2),
            "executable_accuracy_percent": round(executable_selector_accuracy, 2),
        },
    }


def write_csv(path: Path, file_results: list[dict[str, Any]]) -> None:
    fieldnames = [
        "file",
        "coverage_accuracy_percent",
        "missing_dom_ids_total",
        "dom_ids_total",
        "dom_ids_in_nkg_total",
        "selector_strict_accuracy_percent",
        "selector_executable_accuracy_percent",
        "selector_total_elements",
        "selector_valid_single",
        "selector_not_found",
        "selector_invalid",
        "selector_ambiguous",
        "selector_missing_selector",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in file_results:
            writer.writerow(
                {
                    "file": row["file"],
                    "coverage_accuracy_percent": row["coverage"]["coverage_accuracy_percent"],
                    "missing_dom_ids_total": row["coverage"]["missing_dom_ids_total"],
                    "dom_ids_total": row["coverage"]["dom_ids_total"],
                    "dom_ids_in_nkg_total": row["coverage"]["dom_ids_in_nkg_total"],
                    "selector_strict_accuracy_percent": row["selectors"]["strict_accuracy_percent"],
                    "selector_executable_accuracy_percent": row["selectors"]["executable_accuracy_percent"],
                    "selector_total_elements": row["selectors"]["total_elements"],
                    "selector_valid_single": row["selectors"]["valid_single"],
                    "selector_not_found": row["selectors"]["not_found"],
                    "selector_invalid": row["selectors"]["invalid"],
                    "selector_ambiguous": row["selectors"]["ambiguous"],
                    "selector_missing_selector": row["selectors"]["missing_selector"],
                }
            )


def write_markdown(
    path: Path,
    summary: dict[str, Any],
    file_results: list[dict[str, Any]],
    skipped: list[dict[str, str]],
) -> None:
    lines: list[str] = []

    lines.append("# NKG Accuracy Report")
    lines.append("")
    lines.append("## Aggregate Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Files evaluated | {summary['files_evaluated']} |")
    lines.append(f"| Skipped files | {len(skipped)} |")
    lines.append(
        "| Coverage (DOM-id recall) | "
        f"{summary['coverage']['dom_ids_in_nkg_total']}/{summary['coverage']['dom_ids_total']} "
        f"({summary['coverage']['coverage_accuracy_percent']}%) |"
    )
    lines.append(
        "| Selector strict accuracy | "
        f"{summary['selectors']['valid_single']}/{summary['selectors']['total_elements']} "
        f"({summary['selectors']['strict_accuracy_percent']}%) |"
    )
    lines.append(
        "| Selector executable accuracy | "
        f"{summary['selectors']['executable_accuracy_percent']}% "
        f"(not_found={summary['selectors']['not_found']}, invalid={summary['selectors']['invalid']}) |"
    )
    lines.append("")

    lines.append("## Per-file Metrics")
    lines.append("")
    lines.append(
        "| File | Coverage % | Missing DOM IDs | DOM IDs Total | Selector Strict % | Selector Exec % | Not Found | Invalid | Ambiguous |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")

    for row in file_results:
        c = row["coverage"]
        s = row["selectors"]
        lines.append(
            "| "
            f"{row['file']} | "
            f"{c['coverage_accuracy_percent']} | "
            f"{c['missing_dom_ids_total']} | "
            f"{c['dom_ids_total']} | "
            f"{s['strict_accuracy_percent']} | "
            f"{s['executable_accuracy_percent']} | "
            f"{s['not_found']} | "
            f"{s['invalid']} | "
            f"{s['ambiguous']} |"
        )

    if skipped:
        lines.append("")
        lines.append("## Skipped Files")
        lines.append("")
        lines.append("| File | Reason |")
        lines.append("|---|---|")
        for item in skipped:
            reason = str(item.get("reason", "")).replace("\n", " ").replace("|", "\\|")
            lines.append(f"| {item.get('file', '')} | {reason} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Measure NKG extraction accuracy across JSON files")
    parser.add_argument(
        "--nkg-dir",
        required=True,
        help="Folder containing *.nkg.json files",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional path to write full JSON report",
    )
    parser.add_argument(
        "--output-csv",
        default="",
        help="Optional path to write per-file CSV summary",
    )
    parser.add_argument(
        "--output-md",
        default="",
        help="Optional path to write Markdown table report",
    )
    parser.add_argument(
        "--fail-on-missing-html",
        action="store_true",
        help="Exit with error if one file cannot be mapped to HTML",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    nkg_dir = Path(args.nkg_dir).resolve()

    if not nkg_dir.exists():
        raise FileNotFoundError(f"NKG directory not found: {nkg_dir}")

    nkg_files = sorted(nkg_dir.glob("*.nkg.json"))
    if not nkg_files:
        raise FileNotFoundError(f"No .nkg.json files found in {nkg_dir}")

    file_results: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for nkg_path in nkg_files:
        try:
            file_results.append(evaluate_file(repo_root=repo_root, nkg_path=nkg_path))
        except Exception as exc:
            if args.fail_on_missing_html:
                raise
            skipped.append({"file": nkg_path.name, "reason": str(exc)})

    summary = aggregate(file_results)
    report = {
        "summary": summary,
        "files": file_results,
        "skipped": skipped,
        "metric_notes": {
            "coverage_accuracy_percent": "DOM-id recall: dom_ids_in_nkg_total / dom_ids_total",
            "selector_strict_accuracy_percent": "valid_single / total_elements (selector must match exactly 1 element)",
            "selector_executable_accuracy_percent": "(total_elements - (not_found + invalid)) / total_elements",
        },
    }

    print("=== NKG Accuracy Summary ===")
    print(f"Files evaluated: {summary['files_evaluated']}")
    print(
        "Coverage (DOM-id recall): "
        f"{summary['coverage']['dom_ids_in_nkg_total']}/{summary['coverage']['dom_ids_total']} "
        f"({summary['coverage']['coverage_accuracy_percent']}%)"
    )
    print(
        "Selector strict accuracy: "
        f"{summary['selectors']['strict_accuracy_percent']}% "
        f"(valid_single={summary['selectors']['valid_single']}, total={summary['selectors']['total_elements']})"
    )
    print(
        "Selector executable accuracy: "
        f"{summary['selectors']['executable_accuracy_percent']}% "
        f"(not_found={summary['selectors']['not_found']}, invalid={summary['selectors']['invalid']})"
    )
    print(f"Skipped files: {len(skipped)}")

    if args.output_json:
        out_json = Path(args.output_json).resolve()
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved JSON report: {out_json}")

    if args.output_csv:
        out_csv = Path(args.output_csv).resolve()
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        write_csv(out_csv, file_results)
        print(f"Saved CSV summary: {out_csv}")

    if args.output_md:
        out_md = Path(args.output_md).resolve()
        out_md.parent.mkdir(parents=True, exist_ok=True)
        write_markdown(out_md, summary, file_results, skipped)
        print(f"Saved Markdown report: {out_md}")


if __name__ == "__main__":
    main()
