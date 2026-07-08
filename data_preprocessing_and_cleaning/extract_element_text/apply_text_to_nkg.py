import argparse
import json
import sys
from pathlib import Path

DEFAULT_INPUT_DIR = "../data/nkg_gpu3_fix_orphans"
DEFAULT_OUTPUT_DIR = "../data/nkg_gpu3_fix_orphans_with text"
DEFAULT_REPORT = "../data/element_text_review/review_report.json"

def main():
    parser = argparse.ArgumentParser(description="Apply INCLUDE/SKIP decisions and text from review_report.json into NKG JSON files.")
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report", default=DEFAULT_REPORT)
    args = parser.parse_args()

    in_dir = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    report_path = Path(args.report)

    if not in_dir.exists():
        print(f"Error: Input directory {in_dir} not found.")
        sys.exit(1)
    if not report_path.exists():
        print(f"Error: Report file {report_path} not found.")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    with report_path.open("r", encoding="utf-8") as f:
        report = json.load(f)

    total_files = 0
    total_elements_kept = 0
    total_elements_removed = 0
    total_triggers_removed = 0

    for filename, reviewed_elements in report.items():
        nkg_file = in_dir / filename
        if not nkg_file.exists():
            print(f"  [WARN] Missing NKG file: {filename}")
            continue

        # Build a lookup map by local element ID
        # e.g. "office__btn_pindah_device" -> {"status": "INCLUDE", "text": "Pindah"}
        element_map = {}
        for r in reviewed_elements:
            element_map[r["id"]] = {
                "status": r["status"],
                "text": r["text"]
            }

        with nkg_file.open("r", encoding="utf-8") as f:
            nkg_data = json.load(f)

        if "nkg" not in nkg_data or "elements" not in nkg_data["nkg"]:
            print(f"  [WARN] Invalid NKG format: {filename}")
            continue

        original_elements = nkg_data["nkg"]["elements"]
        original_triggers = nkg_data["nkg"].get("triggers", [])

        kept_elements = []
        kept_element_ids = set()

        for elem in original_elements:
            elem_id = elem["id"]
            rev = element_map.get(elem_id)
            
            if rev:
                if rev["status"] == "INCLUDE":
                    elem["text"] = rev["text"]
                elif rev["status"] == "SKIP":
                    elem["skipped"] = True
            else:
                # If it's not explicitly reviewed, we can also default to skipped=True
                # as the pipeline considered them un-extracted noise.
                elem["skipped"] = True
                
            kept_elements.append(elem)
            total_elements_kept += 1

        # Keep all triggers since we no longer delete elements
        kept_triggers = original_triggers

        nkg_data["nkg"]["elements"] = kept_elements
        nkg_data["nkg"]["triggers"] = kept_triggers

        # Write applied output
        out_file = out_dir / filename
        with out_file.open("w", encoding="utf-8") as f:
            json.dump(nkg_data, f, ensure_ascii=False, indent=2)
            
        total_files += 1

    print(f"\n{'='*60}")
    print(f"Successfully processed {total_files} files.")
    print(f"Elements Processed      : {total_elements_kept}")
    print(f"Applied JSONs saved to  : {out_dir}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
