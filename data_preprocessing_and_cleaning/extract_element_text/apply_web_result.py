"""
apply_web_result.py
===================
Applies the JSON output from a web LLM (like ChatGPT or Claude) back to review_report.json.

USAGE:
  1. Save the LLM's JSON output (which should look like {"decisions": {...}}) into a file, e.g., web_result.json
  2. Run: python apply_web_result.py web_result.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPORT_PATH   = Path("../data/element_text_review/review_report.json")
SUMMARY_PATH  = Path("../data/element_text_review/review_summary.txt")

def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return {}

def write_summary(report: dict, summary_path: Path):
    lines = []
    for filename, elements in report.items():
        by_status: dict[str, list] = {"INCLUDE": [], "REVIEW": [], "SKIP": []}
        for elem in elements:
            s = elem.get("status", "SKIP")
            by_status.setdefault(s, []).append(elem)

        lines.append(f"\n{'='*80}")
        lines.append(f" FILE: {filename}")
        lines.append(f"{'='*80}")

        for status_group in ["INCLUDE", "REVIEW", "SKIP"]:
            items = by_status.get(status_group, [])
            if not items:
                continue
            lines.append(f"\n--- {status_group} ({len(items)} items) ---")
            for r in items:
                text_val = repr(r.get("text"))
                if len(text_val) > 1000:
                    text_val = text_val[:997] + "..."
                lines.append(
                    f"  {r['nkg_id']:<65} | type={r['type']:<8} | status={r['status']:<7} | text={text_val}"
                )

    with summary_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Summary rewritten -> {summary_path}")

def main():
    parser = argparse.ArgumentParser(description="Apply JSON output from web LLM to review report")
    parser.add_argument("input_file", help="Path to the file containing the LLM JSON output")
    args = parser.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    with input_path.open("r", encoding="utf-8") as f:
        raw_text = f.read()

    result = extract_json(raw_text)
    decisions = result.get("decisions", {})
    
    if not decisions:
        print("No 'decisions' dictionary found in the input JSON.")
        sys.exit(1)

    if not REPORT_PATH.exists():
        print(f"Error: {REPORT_PATH} not found.")
        sys.exit(1)

    with REPORT_PATH.open("r", encoding="utf-8") as f:
        report: dict = json.load(f)

    # Flatten elements from all files to find the nkg_ids
    # We assume nkg_ids are globally unique across all pages
    total_updated = 0
    
    for filename, elements in report.items():
        elem_map = {e["nkg_id"]: e for e in elements}
        page_updated = 0
        for nkg_id, decision in decisions.items():
            if nkg_id not in elem_map:
                continue
            if decision not in ("INCLUDE", "SKIP"):
                continue
            
            elem = elem_map[nkg_id]
            if elem["status"] != decision:
                elem["status"] = decision
                page_updated += 1
        
        total_updated += page_updated

    if total_updated > 0:
        with REPORT_PATH.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"Success! Updated {total_updated} element statuses in review_report.json")
        
        # Rewrite the summary file so the manual review txt stays in sync
        write_summary(report, SUMMARY_PATH)
    else:
        print("No changes were needed (or nkg_ids didn't match).")

if __name__ == "__main__":
    main()
