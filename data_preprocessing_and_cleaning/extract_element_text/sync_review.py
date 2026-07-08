"""
sync_review.py
==============
Reads your edits from review_summary.txt and pushes them into review_report.json.

Handles status changes AND text edits. 
Safe: Won't overwrite full JSON text with truncated "..." text from summary.
"""

import json
import re
from pathlib import Path

REPORT_PATH  = Path("../data/element_text_review/review_report.json")
SUMMARY_PATH = Path("../data/element_text_review/review_summary.txt")

LINE_RE = re.compile(
    r"^\s+(\S+)"            # nkg_id
    r"\s+\|"
    r"\s+type=\S+"          # type
    r"\s+\|"
    r"\s+status=(\w+)"      # status
    r"\s+\|"
    r"\s+text=(.*)"         # text
)

def parse_text_value(raw: str):
    """Returns (text_string, is_truncated)"""
    raw = raw.strip()
    if raw == "None":
        return None, False
    
    is_truncated = raw.endswith("...'") or raw.endswith('..."')
    
    # Remove surrounding quotes
    if (raw.startswith("'") and raw.endswith("'")) or \
       (raw.startswith('"') and raw.endswith('"')):
        return raw[1:-1], is_truncated
    
    # If it was truncated, the closing quote might be inside the ... or missing
    if is_truncated:
        return raw[1:-3], True
        
    return raw, False

def main():
    if not SUMMARY_PATH.exists():
        print(f"Error: {SUMMARY_PATH} not found.")
        return
    if not REPORT_PATH.exists():
        print(f"Error: {REPORT_PATH} not found.")
        return

    edits = {} 

    with SUMMARY_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            m = LINE_RE.match(line)
            if not m: continue
            
            nkg_id = m.group(1)
            status = m.group(2).strip()
            text_val, is_truncated = parse_text_value(m.group(3).strip())

            edits[nkg_id] = {
                "status": status, 
                "text": text_val, 
                "is_truncated": is_truncated
            }

    with REPORT_PATH.open("r", encoding="utf-8") as f:
        report: dict = json.load(f)

    total_updates = 0
    for filename, elements in report.items():
        for elem in elements:
            nkg_id = elem.get("nkg_id", "")
            if nkg_id not in edits: continue
            
            new = edits[nkg_id]
            changed = False
            
            # 1. Update status
            if elem.get("status") != new["status"]:
                elem["status"] = new["status"]
                changed = True
            
            # 2. Update text (ONLY if not truncated in summary)
            if not new["is_truncated"]:
                if elem.get("text") != new["text"]:
                    elem["text"] = new["text"]
                    changed = True
            else:
                # If it IS truncated, only update if the non-truncated prefix changed
                # (This is rare, usually user won't edit the middle of a 1000-char string in a summary)
                summary_prefix = new["text"].replace("...", "")
                current_text = elem.get("text") or ""
                if not current_text.startswith(summary_prefix):
                    # User likely replaced the whole thing with something else
                    elem["text"] = new["text"]
                    changed = True

            if changed:
                total_updates += 1

    with REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Sync complete. Updated {total_updates} elements.")

if __name__ == "__main__":
    main()
