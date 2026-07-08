"""
fix_orphans.py — NKG Orphan & Bad-Trigger Repair

Purpose
-------
Scans all .nkg.json files in a given directory and finds two classes of problems:

1. ORPHAN PARENT REFERENCES: Elements whose `parent_element_id` references an ID
   that does NOT exist in the same page's element list.

2. BAD TRIGGER TARGETS: Triggers with `to_type: "element"` whose `to` field
   references an ID that does NOT exist in the same page's element list.
   These are caused by LLM hallucinations such as:
     - "to": "element"          (schema placeholder copied verbatim)
     - "to": "#infoStep2"       (CSS selector leaked into ID field)
     - "to": "save_edit()"      (JavaScript function call)
     - "to": "element_id_or_/page/path"  (schema example copied literally)

For each problem, the LLM is asked to decide the correct fix:
  - Parent orphans  → assign a real parent or null (direct page child)
  - Bad triggers    → assign a real target element or null (remove the trigger)

Fixes are applied in-place to both `nkg` and `cypher_payload.params` sections.

Usage
-----
# Dry-run (detect only, no LLM, no writes):
python prompting_chunk/fix_orphans.py --data-dir data/nkg_gpu3 --dry-run

# Live fix:
python prompting_chunk/fix_orphans.py --data-dir data/nkg_gpu3 --model gemma4:31b

# Single file:
python prompting_chunk/fix_orphans.py --data-dir data/nkg_gpu3 --file customer_employee.nkg.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Re-use helpers from the sibling extraction script so we stay DRY
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPT_DIR))

from chunked_html_to_nkg import (  # noqa: E402
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    DEFAULT_TIMEOUT,
    build_cypher_payload,
    extract_json_from_text,
    ollama_chat,
)

# ---------------------------------------------------------------------------
# LLM system prompts
# ---------------------------------------------------------------------------

PARENT_REPAIR_SYSTEM_PROMPT = """\
You are repairing parent-child (CONTAINS) relationships in a Navigational Knowledge Graph (NKG).

Some elements have a `parent_element_id` that references an element which does NOT exist in the page's element list. Your task is to decide the correct fix for each orphan.

Rules:
1. You MUST choose a parent ONLY from the EXISTING_ELEMENT_IDS list, OR set parent_element_id to null.
2. Set parent_element_id to null when no suitable parent exists — this makes the element a direct page child.
3. Use element IDs, types, and descriptions to reason about the correct hierarchy (e.g. a "button" inside a "modal" should have the modal as parent).
4. Never create new element IDs.
5. Every orphan in ORPHAN_ELEMENTS must appear in your fixes[] list.

Return ONLY valid JSON, no markdown, no explanation:
{
  "fixes": [
    {"id": "orphan_element_id", "parent_element_id": "existing_parent_id_or_null"}
  ]
}
"""

TRIGGER_REPAIR_SYSTEM_PROMPT = """\
You are repairing broken TRIGGERS in a Navigational Knowledge Graph (NKG).

Some triggers have a `to` field that references an element which does NOT exist in the page's element list. The `to` value may be a schema placeholder ("element"), a CSS selector ("#id"), a JS function call ("save_edit()"), or a hallucinated ID.

Your task is to decide the correct fix for each bad trigger.

Rules:
1. You MUST choose a `corrected_to` value ONLY from the EXISTING_ELEMENT_IDS list, OR set it to null.
2. Set corrected_to to null when:
   - The bad `to` value is clearly a placeholder or schema example (e.g. "element", "element_id_or_/page/path")
   - No semantically correct target exists in the element list
3. If the bad `to` looks like it references a real element (e.g. "leave__modal_add_leave" when "modal_add_leave" exists), correct it to the best matching existing ID.
4. Use the `from` element's ID, type, and description to reason about what it should trigger.
5. Never create new element IDs.
6. Every bad trigger in BAD_TRIGGERS must appear in your fixes[] list.

Return ONLY valid JSON, no markdown, no explanation:
{
  "fixes": [
    {"from": "from_element_id", "bad_to": "bad_target_id", "corrected_to": "existing_element_id_or_null"}
  ]
}
"""


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_parent_repair_prompt(
    page_url: str,
    orphans: list[dict[str, Any]],
    existing_elements: list[dict[str, Any]],
) -> str:
    compact_existing = [
        {"id": e.get("id"), "type": e.get("type"), "desc": (e.get("desc") or "")[:120]}
        for e in existing_elements
        if isinstance(e, dict) and e.get("id")
    ]
    compact_orphans = [
        {"id": e.get("id"), "type": e.get("type"), "desc": (e.get("desc") or "")[:120],
         "broken_parent_element_id": e.get("parent_element_id")}
        for e in orphans
    ]
    existing_ids = [e.get("id") for e in existing_elements if isinstance(e, dict) and e.get("id")]

    return (
        f"PAGE_URL: {page_url}\n\n"
        "ORPHAN_ELEMENTS (parent_element_id references a missing element):\n"
        f"{json.dumps(compact_orphans, ensure_ascii=False, indent=2)}\n\n"
        "EXISTING_ELEMENT_IDS (choose parents from this list only):\n"
        f"{json.dumps(existing_ids, ensure_ascii=False)}\n\n"
        "EXISTING_ELEMENTS_COMPACT (for context):\n"
        f"{json.dumps(compact_existing, ensure_ascii=False, indent=2)}\n\n"
        "Task: For each orphan, assign parent_element_id to a real existing ID, or null.\n"
    )


def build_trigger_repair_prompt(
    page_url: str,
    bad_triggers: list[dict[str, Any]],
    existing_elements: list[dict[str, Any]],
) -> str:
    compact_existing = [
        {"id": e.get("id"), "type": e.get("type"), "desc": (e.get("desc") or "")[:120]}
        for e in existing_elements
        if isinstance(e, dict) and e.get("id")
    ]
    existing_ids = [e.get("id") for e in existing_elements if isinstance(e, dict) and e.get("id")]

    # Include the from-element's description for richer context
    id_to_desc = {e.get("id"): e for e in existing_elements if isinstance(e, dict) and e.get("id")}
    compact_bad = []
    for t in bad_triggers:
        from_el = id_to_desc.get(t.get("from"), {})
        compact_bad.append({
            "from":          t.get("from"),
            "from_type":     from_el.get("type", ""),
            "from_desc":     (from_el.get("desc") or "")[:100],
            "bad_to":        t.get("to"),
        })

    return (
        f"PAGE_URL: {page_url}\n\n"
        "BAD_TRIGGERS (to field references a non-existent element):\n"
        f"{json.dumps(compact_bad, ensure_ascii=False, indent=2)}\n\n"
        "EXISTING_ELEMENT_IDS (choose corrected_to from this list only):\n"
        f"{json.dumps(existing_ids, ensure_ascii=False)}\n\n"
        "EXISTING_ELEMENTS_COMPACT (for context):\n"
        f"{json.dumps(compact_existing, ensure_ascii=False, indent=2)}\n\n"
        "Task: For each bad trigger, set corrected_to to the correct existing element ID, or null to remove it.\n"
    )


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def find_orphan_parents(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Elements whose parent_element_id points to a non-existent element."""
    existing_ids = {e.get("id") for e in elements if isinstance(e, dict) and e.get("id")}
    return [
        e for e in elements
        if isinstance(e, dict)
        and e.get("parent_element_id")
        and e["parent_element_id"] not in existing_ids
    ]


def find_bad_triggers(
    triggers: list[dict[str, Any]],
    existing_ids: set[str],
) -> list[dict[str, Any]]:
    """Triggers with to_type='element' whose `to` doesn't exist in existing_ids."""
    return [
        t for t in triggers
        if isinstance(t, dict)
        and t.get("to_type") == "element"
        and t.get("to") not in existing_ids
    ]


# ---------------------------------------------------------------------------
# Apply LLM fixes
# ---------------------------------------------------------------------------

def apply_parent_fixes(elements: list[dict[str, Any]], fixes: list[dict[str, Any]]) -> int:
    fix_map: dict[str, str | None] = {}
    for fix in fixes:
        elem_id = str(fix.get("id", "")).strip()
        parent = fix.get("parent_element_id")
        if isinstance(parent, str):
            parent = parent.strip() or None
        if elem_id:
            fix_map[elem_id] = parent

    applied = 0
    for elem in elements:
        if not isinstance(elem, dict):
            continue
        elem_id = elem.get("id")
        if elem_id in fix_map:
            new_parent = fix_map[elem_id]
            if new_parent is None:
                elem.pop("parent_element_id", None)
            else:
                elem["parent_element_id"] = new_parent
            applied += 1
    return applied


def apply_trigger_fixes(
    triggers: list[dict[str, Any]],
    fixes: list[dict[str, Any]],
    existing_ids: set[str],
) -> tuple[list[dict[str, Any]], int]:
    """
    Returns the repaired triggers list and number of changes made.
    Triggers where corrected_to is null are removed.
    Triggers where corrected_to is a valid ID are updated.
    """
    # Build a lookup: (from, bad_to) -> corrected_to
    fix_map: dict[tuple[str, str], str | None] = {}
    for fix in fixes:
        from_id  = str(fix.get("from", "")).strip()
        bad_to   = str(fix.get("bad_to", "")).strip()
        corrected = fix.get("corrected_to")
        if isinstance(corrected, str):
            corrected = corrected.strip() or None
        if from_id and bad_to:
            fix_map[(from_id, bad_to)] = corrected

    repaired: list[dict[str, Any]] = []
    changed = 0
    for t in triggers:
        if not isinstance(t, dict):
            continue
        from_id = t.get("from", "")
        to_id   = t.get("to", "")
        to_type = t.get("to_type", "")

        key = (from_id, to_id)
        if to_type == "element" and to_id not in existing_ids and key in fix_map:
            corrected = fix_map[key]
            if corrected is None:
                # Remove this trigger entirely
                changed += 1
                continue
            if corrected in existing_ids:
                t = {**t, "to": corrected}
                changed += 1
            # else: LLM gave invalid answer — keep original and let insertion filter it
        repaired.append(t)

    return repaired, changed


# ---------------------------------------------------------------------------
# Main per-file processing
# ---------------------------------------------------------------------------

def process_file(
    filepath: Path,
    ollama_url: str,
    model: str,
    timeout: int,
    dry_run: bool,
) -> dict[str, Any]:
    with filepath.open("r", encoding="utf-8") as f:
        data = json.load(f)

    nkg = data.get("nkg", {})
    elements: list[dict[str, Any]] = nkg.get("elements", [])
    triggers: list[dict[str, Any]] = nkg.get("triggers", [])
    page_url: str = nkg.get("page", {}).get("id", str(filepath.stem))
    existing_ids = {e.get("id") for e in elements if isinstance(e, dict) and e.get("id")}

    orphans     = find_orphan_parents(elements)
    bad_trigs   = find_bad_triggers(triggers, existing_ids)

    summary = {
        "file":             filepath.name,
        "page_url":         page_url,
        "total_elements":   len(elements),
        "orphans_found":    len(orphans),
        "orphan_ids":       [e.get("id") for e in orphans],
        "bad_triggers":     len(bad_trigs),
        "bad_trigger_list": [{"from": t.get("from"), "to": t.get("to")} for t in bad_trigs],
        "parent_fixes":     0,
        "trigger_fixes":    0,
        "error":            None,
    }

    has_problems = bool(orphans or bad_trigs)

    if orphans:
        print(f"  {len(orphans)} orphan parent(s): {[e.get('id') for e in orphans]}")
    if bad_trigs:
        print(f"  {len(bad_trigs)} bad trigger(s): {[{'from': t.get('from'), 'to': t.get('to')} for t in bad_trigs]}")

    if not has_problems:
        return summary

    if dry_run:
        return summary

    # -----------------------------------------------------------------------
    # Fix 1: Orphan parents
    # -----------------------------------------------------------------------
    if orphans:
        prompt = build_parent_repair_prompt(page_url, orphans, elements)
        try:
            raw = ollama_chat(
                ollama_url=ollama_url, model=model,
                system_prompt=PARENT_REPAIR_SYSTEM_PROMPT, user_prompt=prompt,
                timeout_seconds=timeout, temperature=0.1, num_predict=2048,
                use_json_mode=True, stream=False,
            )
            result = extract_json_from_text(raw)
            fixes = result.get("fixes", [])
            if isinstance(fixes, list):
                applied = apply_parent_fixes(elements, fixes)
                summary["parent_fixes"] = applied
                print(f"    [PARENT] applied {applied} fix(es)")
            else:
                print("    [PARENT] LLM returned invalid fixes format — skipping")
        except Exception as exc:
            summary["error"] = f"Parent LLM error: {exc}"
            print(f"    [PARENT ERR] {exc}")

        # Fallback: strip any still-broken parent_element_ids
        remaining = find_orphan_parents(elements)
        if remaining:
            for elem in remaining:
                elem.pop("parent_element_id", None)
                summary["parent_fixes"] += 1
            print(f"    [PARENT FALLBACK] Stripped broken parent from {len(remaining)} element(s) → direct page children")

    # -----------------------------------------------------------------------
    # Fix 2: Bad trigger targets
    # -----------------------------------------------------------------------
    if bad_trigs:
        prompt = build_trigger_repair_prompt(page_url, bad_trigs, elements)
        try:
            raw = ollama_chat(
                ollama_url=ollama_url, model=model,
                system_prompt=TRIGGER_REPAIR_SYSTEM_PROMPT, user_prompt=prompt,
                timeout_seconds=timeout, temperature=0.1, num_predict=2048,
                use_json_mode=True, stream=False,
            )
            result = extract_json_from_text(raw)
            fixes = result.get("fixes", [])
            if isinstance(fixes, list):
                triggers, changed = apply_trigger_fixes(triggers, fixes, existing_ids)
                summary["trigger_fixes"] = changed
                print(f"    [TRIGGER] applied {changed} fix(es)")
            else:
                print("    [TRIGGER] LLM returned invalid fixes format — fallback: removing bad triggers")
                triggers = [t for t in triggers if not (t.get("to_type") == "element" and t.get("to") not in existing_ids)]
        except Exception as exc:
            summary["error"] = (summary.get("error") or "") + f" | Trigger LLM error: {exc}"
            print(f"    [TRIGGER ERR] {exc} — fallback: removing bad triggers")
            triggers = [t for t in triggers if not (t.get("to_type") == "element" and t.get("to") not in existing_ids)]

        # Fallback: drop any still-bad triggers
        still_bad = find_bad_triggers(triggers, existing_ids)
        if still_bad:
            triggers = [t for t in triggers if t not in still_bad]
            summary["trigger_fixes"] += len(still_bad)
            print(f"    [TRIGGER FALLBACK] Removed {len(still_bad)} still-bad trigger(s)")

    # -----------------------------------------------------------------------
    # Write repaired data back
    # -----------------------------------------------------------------------
    data["nkg"]["elements"] = elements
    data["nkg"]["triggers"] = triggers
    data["cypher_payload"]  = build_cypher_payload(data["nkg"])

    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    [SAVED] {filepath.name}")

    return summary


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect and LLM-repair orphan parents and bad trigger targets in NKG JSON files."
    )
    parser.add_argument("--data-dir", default="data/nkg_gpu3",
                        help="Directory containing .nkg.json files")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Ollama model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL,
                        help=f"Ollama base URL (default: {DEFAULT_OLLAMA_URL})")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help="Per-request timeout in seconds")
    parser.add_argument("--dry-run", action="store_true",
                        help="Detect problems only — no LLM calls, no writes")
    parser.add_argument("--file", default="",
                        help="Process a single file only (filename, not full path)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"[ERROR] Data directory not found: {data_dir}")
        sys.exit(1)

    files = [data_dir / args.file] if args.file else sorted(data_dir.glob("*.json"))
    if not files:
        print(f"[ERROR] No .json files found in {data_dir}")
        sys.exit(1)

    print(f"Mode   : {'DRY-RUN (no LLM, no writes)' if args.dry_run else 'LIVE'}")
    print(f"Model  : {args.model}")
    print(f"Server : {args.ollama_url}")
    print(f"Files  : {len(files)}")
    print("-" * 60)

    t_start = time.time()
    summaries: list[dict[str, Any]] = []
    total_orphans = total_bad_trigs = total_fixed = 0

    for filepath in files:
        print(f"\n[{filepath.name}]")
        try:
            summary = process_file(
                filepath=filepath,
                ollama_url=args.ollama_url,
                model=args.model,
                timeout=args.timeout,
                dry_run=args.dry_run,
            )
        except Exception as exc:
            summary = {"file": filepath.name, "error": str(exc),
                       "orphans_found": 0, "bad_triggers": 0,
                       "parent_fixes": 0, "trigger_fixes": 0}
            print(f"  [ERR] {exc}")

        summaries.append(summary)
        total_orphans   += summary.get("orphans_found", 0)
        total_bad_trigs += summary.get("bad_triggers", 0)
        total_fixed     += summary.get("parent_fixes", 0) + summary.get("trigger_fixes", 0)

        if not summary.get("orphans_found") and not summary.get("bad_triggers"):
            print("  OK — no problems")

    elapsed = time.time() - t_start
    print("\n" + "=" * 60)
    print(f"DONE in {elapsed:.1f}s")
    print(f"Total orphan parents found  : {total_orphans}")
    print(f"Total bad triggers found    : {total_bad_trigs}")
    print(f"Total fixes applied         : {total_fixed}")

    affected = [s for s in summaries if s.get("orphans_found", 0) or s.get("bad_triggers", 0)]
    if affected:
        print("\nFiles with problems:")
        for s in affected:
            parts = []
            if s.get("orphans_found"):
                parts.append(f"orphans={s['orphans_found']} parent_fixes={s.get('parent_fixes',0)}")
            if s.get("bad_triggers"):
                parts.append(f"bad_triggers={s['bad_triggers']} trigger_fixes={s.get('trigger_fixes',0)}")
            if s.get("error"):
                parts.append(f"ERR={s['error']}")
            print(f"  {s['file']:<55} {' | '.join(parts)}")


if __name__ == "__main__":
    main()
