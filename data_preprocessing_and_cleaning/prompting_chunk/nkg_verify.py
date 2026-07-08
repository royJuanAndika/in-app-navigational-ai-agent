#!/usr/bin/env python3
"""
NKG verification and comparison tool.

Utilities:
1. Show detailed element/trigger breakdown
2. Compare two NKG outputs
3. Export Cypher statements
4. Analyze selector specificity
"""

import argparse
import json
from pathlib import Path
from typing import Any


def show_nkg_summary(nkg_path: str) -> None:
    """Display comprehensive NKG summary."""
    with open(nkg_path) as f:
        data = json.load(f)
    
    meta = data.get("meta", {})
    nkg = data.get("nkg", {})
    verify = data.get("verification", {})
    
    print(f"\n{'='*80}")
    print(f"NKG FILE: {Path(nkg_path).name}")
    print(f"{'='*80}")
    
    # Metadata
    print(f"\nPAGE: {meta.get('page_url', 'N/A')} ({meta.get('page_title', 'N/A')})")
    print(f"Model: {meta.get('model', 'N/A')}")
    print(f"Runtime: {meta.get('runtime_seconds', 'N/A')}s")
    print(f"Chunks: {meta.get('chunk_config', {}).get('total_chunks', 'N/A')}")
    
    # Elements by type
    elements = nkg.get("elements", [])
    type_count = {}
    for el in elements:
        t = el.get("type", "unknown")
        type_count[t] = type_count.get(t, 0) + 1
    
    print(f"\nELEMENTS: {len(elements)} total")
    for t in sorted(type_count.keys()):
        print(f"  - {t}: {type_count[t]}")
    
    # ID types
    dom_ids = sum(1 for el in elements if el.get("id") in verify.get("dom_ids_in_nkg_total", []))
    gen_ids = len(verify.get("generated_non_dom_ids", []))
    print(f"\nID TYPES:")
    print(f"  - From DOM: {verify.get('dom_ids_in_nkg_total', 0)}")
    print(f"  - Generated: {gen_ids}")
    
    # Triggers
    triggers = nkg.get("triggers", [])
    page_triggers = sum(1 for t in triggers if t.get("to_type") == "page")
    elem_triggers = sum(1 for t in triggers if t.get("to_type") == "element")
    print(f"\nTRIGGERS: {len(triggers)} total")
    print(f"  - To page: {page_triggers}")
    print(f"  - To element: {elem_triggers}")
    
    # Verification
    print(f"\nVERIFICATION:")
    print(f"  - Coverage: {verify.get('coverage_percent', 0):.1f}% ({verify.get('dom_ids_in_nkg_total', 0)}/{verify.get('dom_ids_total', 0)})")
    print(f"  - Missing IDs: {len(verify.get('missing_dom_ids', []))}")
    print(f"  - Complete: {verify.get('is_complete', False)}")
    
    if verify.get("missing_dom_ids"):
        print(f"\n  Missing DOM IDs (first 10):")
        for mid in verify.get("missing_dom_ids", [])[:10]:
            line_info = next(
                (m["line"] for m in verify.get("missing_dom_ids_with_line", []) if m["id"] == mid),
                "?"
            )
            print(f"    - {mid} (line {line_info})")
    
    if verify.get("selector_mismatches"):
        print(f"\n  Selector Mismatches: {len(verify.get('selector_mismatches', []))}")
        for mismatch in verify.get("selector_mismatches", [])[:5]:
            print(f"    - {mismatch['id']}: expected {mismatch['expected']}, got {mismatch['actual']}")
    
    # Selector analysis
    selectors = [el.get("selector", "") for el in elements]
    selector_types = {
        "id_based": sum(1 for s in selectors if s.startswith("#")),
        "class_based": sum(1 for s in selectors if "." in s and not s.startswith("#")),
        "attribute": sum(1 for s in selectors if "[" in s),
        "other": sum(1 for s in selectors if not any(x in s for x in ["#", ".", "["])),
    }
    
    print(f"\nSELECTOR TYPES:")
    for st in sorted(selector_types.keys()):
        if selector_types[st] > 0:
            pct = selector_types[st] / len(selectors) * 100
            print(f"  - {st}: {selector_types[st]} ({pct:.1f}%)")


def compare_nkg_files(nkg1_path: str, nkg2_path: str) -> None:
    """Compare two NKG outputs."""
    with open(nkg1_path) as f:
        nkg1 = json.load(f)
    with open(nkg2_path) as f:
        nkg2 = json.load(f)
    
    print(f"\n{'='*80}")
    print(f"COMPARING NKG FILES")
    print(f"{'='*80}")
    
    el1 = {e.get("id") for e in nkg1.get("nkg", {}).get("elements", [])}
    el2 = {e.get("id") for e in nkg2.get("nkg", {}).get("elements", [])}
    
    print(f"\n{Path(nkg1_path).name}:")
    print(f"  Elements: {len(el1)}")
    print(f"  Coverage: {nkg1.get('verification', {}).get('coverage_percent', 0):.1f}%")
    
    print(f"\n{Path(nkg2_path).name}:")
    print(f"  Elements: {len(el2)}")
    print(f"  Coverage: {nkg2.get('verification', {}).get('coverage_percent', 0):.1f}%")
    
    only_1 = el1 - el2
    only_2 = el2 - el1
    common = el1 & el2
    
    print(f"\nDIFFERENCES:")
    print(f"  - Only in file 1: {len(only_1)}")
    if only_1:
        print(f"    Sample: {list(only_1)[:3]}")
    print(f"  - Only in file 2: {len(only_2)}")
    if only_2:
        print(f"    Sample: {list(only_2)[:3]}")
    print(f"  - Common: {len(common)}")


def export_cypher(nkg_path: str, output_path: str) -> None:
    """Export Cypher statements from NKG."""
    with open(nkg_path) as f:
        data = json.load(f)
    
    cypher = data.get("cypher_payload", {})
    params = cypher.get("params", {})
    templates = cypher.get("cypher_templates", {})
    
    with open(output_path, "w") as f:
        f.write("// AUTO-GENERATED CYPHER STATEMENTS\n")
        f.write(f"// Source: {Path(nkg_path).name}\n")
        f.write(f"// Page: {params.get('page', {}).get('id', 'N/A')}\n\n")
        
        for name, template in templates.items():
            f.write(f"// {name}\n")
            f.write(f"{template}\n\n")
        
        f.write("\n// PARAMETERS (as JSON)\n")
        f.write(json.dumps(params, indent=2, ensure_ascii=False))
    
    print(f"Exported Cypher to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="NKG verification and analysis tool")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Subcommand: show
    show_parser = subparsers.add_parser("show", help="Show NKG summary")
    show_parser.add_argument("nkg_file", help="Path to NKG JSON file")
    
    # Subcommand: compare
    compare_parser = subparsers.add_parser("compare", help="Compare two NKG files")
    compare_parser.add_argument("nkg1", help="First NKG JSON file")
    compare_parser.add_argument("nkg2", help="Second NKG JSON file")
    
    # Subcommand: export-cypher
    export_parser = subparsers.add_parser("export-cypher", help="Export Cypher statements")
    export_parser.add_argument("nkg_file", help="Path to NKG JSON file")
    export_parser.add_argument("--output", "-o", default="", help="Output Cypher file (default: nkg_file.cypher)")
    
    args = parser.parse_args()
    
    if args.command == "show":
        show_nkg_summary(args.nkg_file)
    elif args.command == "compare":
        compare_nkg_files(args.nkg1, args.nkg2)
    elif args.command == "export-cypher":
        output_file = args.output or (args.nkg_file.replace(".json", ".cypher"))
        export_cypher(args.nkg_file, output_file)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
