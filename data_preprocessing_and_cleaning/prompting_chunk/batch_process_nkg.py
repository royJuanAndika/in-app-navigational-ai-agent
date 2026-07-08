#!/usr/bin/env python3
"""
Batch processor for HTML → NKG extraction with one-shot prompting.

Workflow:
1. Extract first page (establishes extraction style)
2. Use result as one-shot example for remaining pages
3. Track each page's verification status
4. Generate comprehensive report
"""

import argparse
import json
from pathlib import Path
from datetime import datetime
import subprocess
import sys


def extract_page(
    html_file: str,
    output_file: str,
    one_shot_example: str | None = None,
    model: str = "gemma4:31b",
    patch_missing: bool = False,
    verbose: bool = True,
) -> dict:
    """Extract one HTML page to NKG JSON."""
    cmd = [
        "python",
        "prompting_chunk/chunked_html_to_nkg.py",
        "--html", html_file,
        "--out", output_file,
        "--model", model,
    ]
    
    if one_shot_example:
        cmd.extend(["--one-shot-example", one_shot_example])
    
    if patch_missing:
        cmd.append("--patch-missing")
    
    if verbose:
        print(f"\n{'='*80}")
        print(f"Processing: {Path(html_file).name}")
        print(f"Command: {' '.join(cmd)}")
        print(f"{'='*80}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        return {
            "status": "error",
            "file": html_file,
            "error": result.stderr[-500:] if result.stderr else "Unknown error",
        }
    
    # Load the generated NKG JSON
    try:
        with open(output_file) as f:
            nkg_data = json.load(f)
        
        verification = nkg_data.get("verification", {})
        return {
            "status": "success",
            "file": html_file,
            "output": output_file,
            "page_url": nkg_data["meta"]["page_url"],
            "chunks": nkg_data["meta"]["chunk_config"]["total_chunks"],
            "dom_ids_total": verification.get("dom_ids_total", 0),
            "dom_ids_covered": verification.get("dom_ids_in_nkg_total", 0),
            "coverage_percent": verification.get("coverage_percent", 0),
            "missing_ids": len(verification.get("missing_dom_ids", [])),
            "is_complete": verification.get("is_complete", False),
            "runtime_seconds": nkg_data["meta"].get("runtime_seconds", 0),
        }
    except Exception as e:
        return {
            "status": "error",
            "file": html_file,
            "error": str(e),
        }


def find_html_files(input_dir: str, limit: int | None = None) -> list[str]:
    """Find all cleaned HTML files."""
    p = Path(input_dir)
    files = sorted(p.glob("customer_*.html"))
    if limit:
        files = files[:limit]
    return [str(f) for f in files]


def format_report_line(result: dict) -> str:
    """Format one result line for table."""
    if result["status"] == "error":
        return f"❌ {Path(result['file']).name:<40} ERROR: {result['error'][:50]}"
    
    coverage = result["coverage_percent"]
    complete = "✓" if result["is_complete"] else "✗"
    return (
        f"✓ {Path(result['file']).name:<40} "
        f"| {result['dom_ids_covered']:3d}/{result['dom_ids_total']:3d} IDs ({coverage:5.1f}%) "
        f"| {result['chunks']:2d} chunks | {result['runtime_seconds']:6.1f}s | {complete}"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Batch process cleaned HTML to NKG with one-shot prompting"
    )
    parser.add_argument(
        "--input-dir",
        default="data/cleaned_html",
        help="Directory with cleaned HTML files"
    )
    parser.add_argument(
        "--output-dir",
        default="data/nkg_chunked_output",
        help="Output directory for NKG JSON files"
    )
    parser.add_argument(
        "--start", type=int, default=0,
        help="Start from page N (0-indexed)"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Process only N pages (e.g., 5 for testing)"
    )
    parser.add_argument(
        "--model", default="gemma4:31b",
        help="Ollama model to use"
    )
    parser.add_argument(
        "--patch-missing", action="store_true",
        help="Run patching pass for missing DOM ids"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be processed without running"
    )
    
    args = parser.parse_args()
    
    # Find files
    html_files = find_html_files(args.input_dir, args.limit)
    if args.start > 0:
        html_files = html_files[args.start:]
    
    if not html_files:
        print("No HTML files found!")
        return 1
    
    print(f"\nFound {len(html_files)} HTML files")
    if args.dry_run:
        print("\nDRY-RUN MODE (no extraction will run)")
        for i, f in enumerate(html_files, args.start + 1):
            print(f"  {i}. {Path(f).name}")
        return 0
    
    # Create output directory
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    
    # Process first page (establishes one-shot example)
    one_shot_example = None
    results = []
    
    for idx, html_file in enumerate(html_files, args.start + 1):
        output_file = Path(args.output_dir) / (Path(html_file).stem + ".nkg.json")
        
        result = extract_page(
            html_file,
            str(output_file),
            one_shot_example=one_shot_example,
            model=args.model,
            patch_missing=args.patch_missing,
        )
        results.append(result)
        
        print(format_report_line(result))
        
        # Use first successful result as one-shot example
        if one_shot_example is None and result["status"] == "success":
            one_shot_example = str(output_file)
            print(f"  → Saved as one-shot example for next pages\n")
    
    # Summary
    print("\n" + "=" * 100)
    print("BATCH PROCESSING SUMMARY")
    print("=" * 100)
    
    successes = [r for r in results if r["status"] == "success"]
    failures = [r for r in results if r["status"] == "error"]
    
    print(f"\nProcessed: {len(successes)}/{len(results)} pages")
    
    if successes:
        avg_coverage = sum(r["coverage_percent"] for r in successes) / len(successes)
        complete = sum(1 for r in successes if r["is_complete"])
        total_runtime = sum(r["runtime_seconds"] for r in successes)
        
        print(f"Success: {len(successes)} pages")
        print(f"  - Avg DOM ID coverage: {avg_coverage:.1f}%")
        print(f"  - Complete (100% coverage): {complete}/{len(successes)}")
        print(f"  - Total runtime: {total_runtime:.1f}s")
    
    if failures:
        print(f"\nFailed: {len(failures)} pages")
        for r in failures:
            print(f"  - {Path(r['file']).name}: {r['error'][:60]}")
    
    # Write detailed report
    report_path = Path(args.output_dir) / f"batch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_data = {
        "timestamp": datetime.now().isoformat(),
        "start_index": args.start,
        "total_pages": len(results),
        "successes": len(successes),
        "failures": len(failures),
        "one_shot_model": "first page result",
        "results": results,
    }
    
    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    
    print(f"\nDetailed report: {report_path}")
    
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
