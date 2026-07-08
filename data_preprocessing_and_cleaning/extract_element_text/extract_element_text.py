"""
extract_element_text.py
=======================
Extracts visible text labels from HTML elements for every entry in the NKG JSON files.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

try:
    from bs4 import BeautifulSoup, Tag
except ImportError:
    print("ERROR: beautifulsoup4 is required. Run: pip install beautifulsoup4 lxml")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_HTML_DIR = "../data/cleaned_html_2"
DEFAULT_NKG_DIR  = "../data/nkg_gpu3_fix_orphans"
DEFAULT_REPORT   = "../data/element_text_review/review_report.json"
DEFAULT_SUMMARY  = "../data/element_text_review/review_summary.txt"


# ---------------------------------------------------------------------------
# Classification Constants
# ---------------------------------------------------------------------------
CONTAINER_TYPES = {"table", "modal", "section", "element"}
INPUT_TYPES = {"input", "textarea"}
LABEL_TEXT_TYPES = {"button", "link", "tab", "select"}


def clean_text(raw: str) -> str:
    """Normalise whitespace, strip leading/trailing noise."""
    text = re.sub(r"\s+", " ", raw).strip()
    text = re.sub(r"^[•·▪▸►‣\-\*]+\s*", "", text)
    return text


def is_only_digits(text: str) -> bool:
    return bool(re.fullmatch(r"[\d\s/\-\.,:]+", text))


def is_dynamic_selector(selector: str) -> bool:
    if "data-date=" in selector:
        return True
    if re.search(r"\[.*=.*\d{4,}", selector):
        return True
    return False


def extract_text_for_element(elem: Optional[Tag], nkg_type: str, selector: str) -> Tuple[Optional[str], str]:
    """
    Returns (extracted_text, method_used).
    """
    if elem is None:
        return None, "not_found"

    # For inputs/textareas: prefer placeholder > aria-label > title
    if nkg_type in INPUT_TYPES:
        for attr in ("placeholder", "aria-label", "title"):
            val = elem.get(attr)
            if val and isinstance(val, str):
                val = val.strip()
                if val:
                    return clean_text(val), attr
        return None, "no_placeholder"

    # For selects: use the aria-label or the placeholder option
    if nkg_type == "select":
        aria = elem.get("aria-label")
        if aria and isinstance(aria, str):
            aria = aria.strip()
            if aria:
                return clean_text(aria), "aria-label"
        
        first_option = elem.find("option")
        if first_option:
            val = clean_text(first_option.get_text())
            if val:
                return val, "first_option"
        return None, "no_select_label"

    # For containers: skip by default but we will extract text anyway for review
    if nkg_type in CONTAINER_TYPES:
        return None, "container_skipped"

    # For buttons, links, tabs: get inner text
    raw = elem.get_text(separator=" ")
    text = clean_text(raw)
    if text:
        return text, "inner_text"

    # Fall back to aria-label or title
    for attr in ("aria-label", "title", "data-original-title"):
        val = elem.get(attr)
        if val and isinstance(val, str):
            val = val.strip()
            if val:
                return clean_text(val), attr

    return None, "empty"


def classify(nkg_type: str, selector: str, text: Optional[str]) -> str:
    """
    Returns 'INCLUDE', 'SKIP', or 'REVIEW'.
    """
    if text is None or not text:
        return "SKIP"

    if is_dynamic_selector(selector):
        return "SKIP"

    if nkg_type in CONTAINER_TYPES:
        return "SKIP"

    if is_only_digits(text):
        return "SKIP"

    if nkg_type in ("button", "link", "tab") and text:
        return "INCLUDE"

    if nkg_type in INPUT_TYPES and text:
        return "INCLUDE"

    if nkg_type == "select":
        return "REVIEW"

    return "REVIEW"


def process_file(html_path: Path, nkg_path: Path) -> List[Dict[str, Any]]:
    """Process one pair of files."""
    with html_path.open("r", encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f, "lxml")

    with nkg_path.open("r", encoding="utf-8") as f:
        nkg_data = json.load(f)

    page = nkg_data.get("nkg", {}).get("page", {})
    page_id = page.get("id", "")
    elements = nkg_data.get("nkg", {}).get("elements", [])

    results = []
    for elem_def in elements:
        elem_id   = elem_def.get("id", "")
        nkg_type  = elem_def.get("type", "")
        selector  = elem_def.get("selector", "")
        desc      = elem_def.get("desc", "")
        nkg_id    = f"{page_id}/{elem_id}"

        try:
            found = soup.select_one(selector) if selector else None
        except Exception:
            found = None

        text, method = extract_text_for_element(found, nkg_type, selector)
        
        # Raw fallback if method returned nothing but element exists
        if text is None and found:
            raw = found.get_text(separator=" ").strip()
            if raw:
                text = clean_text(raw)
                method = "raw_fallback"

        status = classify(nkg_type, selector, text)

        results.append({
            "nkg_id":   nkg_id,
            "id":       elem_id,
            "type":     nkg_type,
            "selector": selector,
            "desc":     desc,
            "text":     text,
            "method":   method,
            "status":   status,
        })

    return results


def main():
    parser = argparse.ArgumentParser(description="Extract and classify element text from HTML → NKG JSON.")
    parser.add_argument("--html-dir", default=DEFAULT_HTML_DIR)
    parser.add_argument("--nkg-dir",  default=DEFAULT_NKG_DIR)
    parser.add_argument("--output",   default=DEFAULT_REPORT)
    parser.add_argument("--summary",  default=DEFAULT_SUMMARY)
    args = parser.parse_args()

    html_dir = Path(args.html_dir)
    nkg_dir  = Path(args.nkg_dir)
    out_path = Path(args.output)
    sum_path = Path(args.summary)

    if not html_dir.exists():
        print(f"ERROR: HTML dir not found: {html_dir}")
        sys.exit(1)
    if not nkg_dir.exists():
        print(f"ERROR: NKG dir not found: {nkg_dir}")
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    nkg_files = sorted(nkg_dir.glob("*.nkg.json"))
    print(f"Found {len(nkg_files)} NKG files.\n")

    html_map = {p.stem: p for p in html_dir.glob("*.html")}

    report   = {}
    stats    = {"INCLUDE": 0, "SKIP": 0, "REVIEW": 0, "no_html": 0}
    summary_lines = []

    for nkg_path in nkg_files:
        base_name = nkg_path.stem.replace(".nkg", "")
        html_path = html_map.get(base_name)

        if not html_path:
            print(f"  [WARN] No matching HTML for {nkg_path.name}")
            stats["no_html"] += 1
            continue

        results = process_file(html_path, nkg_path)

        counts = {"INCLUDE": 0, "SKIP": 0, "REVIEW": 0}
        by_status = {"INCLUDE": [], "REVIEW": [], "SKIP": []}
        
        for r in results:
            counts[r["status"]] += 1
            stats[r["status"]] += 1
            by_status[r["status"]].append(r)

        print(f"  {nkg_path.name:<55}  "
              f"INCLUDE={counts['INCLUDE']}  "
              f"REVIEW={counts['REVIEW']}  "
              f"SKIP={counts['SKIP']}")

        report[nkg_path.name] = results

        summary_lines.append(f"\n{'='*80}")
        summary_lines.append(f" FILE: {nkg_path.name}")
        summary_lines.append(f"{'='*80}")

        # Group by status but keep the inline status= field for editing
        for status_group in ["INCLUDE", "REVIEW", "SKIP"]:
            items = by_status[status_group]
            if not items:
                continue
            
            summary_lines.append(f"\n--- {status_group} ({len(items)} items) ---")
            for r in items:
                text_val = repr(r['text'])
                if len(text_val) > 1000:
                    text_val = text_val[:997] + "..."
                line = f"  {r['nkg_id']:<65} | type={r['type']:<8} | status={r['status']:<7} | text={text_val}"
                summary_lines.append(line)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    with sum_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines))

    print(f"\n{'='*60}")
    print(f"INCLUDE : {stats['INCLUDE']}")
    print(f"REVIEW  : {stats['REVIEW']}  <-- inspect these in review_summary.txt")
    print(f"SKIP    : {stats['SKIP']}")
    print(f"Review report  -> {out_path}")
    print(f"Summary text   -> {sum_path}")


if __name__ == "__main__":
    main()
