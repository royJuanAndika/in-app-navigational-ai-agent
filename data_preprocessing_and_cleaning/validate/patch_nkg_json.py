#!/usr/bin/env python

import argparse
import importlib.util
import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_chunked_module(repo_root: Path):
    module_path = repo_root / "prompting_chunk" / "chunked_html_to_nkg.py"
    spec = importlib.util.spec_from_file_location("chunked_html_to_nkg", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def dedupe_triggers(triggers: list[dict]) -> list[dict]:
    seen = set()
    cleaned = []
    for tr in triggers:
        key = (tr.get("from"), tr.get("to"), tr.get("to_type"))
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(tr)
    return cleaned


def apply_ops(nkg_obj: dict, ops: dict) -> tuple[int, int, int, int]:
    nkg = nkg_obj.setdefault("nkg", {})
    elements = nkg.setdefault("elements", [])
    triggers = nkg.setdefault("triggers", [])

    remove_ids = set(ops.get("remove_element_ids", []))
    upsert_elements = ops.get("upsert_elements", [])
    remove_triggers = ops.get("remove_triggers", [])
    upsert_triggers = ops.get("upsert_triggers", [])

    before_elements = len(elements)
    before_triggers = len(triggers)

    if remove_ids:
        elements = [el for el in elements if el.get("id") not in remove_ids]
        triggers = [
            tr
            for tr in triggers
            if tr.get("from") not in remove_ids and not (tr.get("to_type") == "element" and tr.get("to") in remove_ids)
        ]

    by_id = {el.get("id"): el for el in elements if el.get("id")}
    upsert_added = 0
    upsert_updated = 0
    for el in upsert_elements:
        element_id = el.get("id")
        if not element_id:
            continue
        if element_id in by_id:
            by_id[element_id].update(el)
            upsert_updated += 1
        else:
            by_id[element_id] = el
            upsert_added += 1

    elements = sorted(by_id.values(), key=lambda item: item.get("id", ""))

    trigger_set = {(tr.get("from"), tr.get("to"), tr.get("to_type")) for tr in triggers}
    for tr in remove_triggers:
        key = (tr.get("from"), tr.get("to"), tr.get("to_type"))
        if key in trigger_set:
            trigger_set.remove(key)
    triggers = [tr for tr in triggers if (tr.get("from"), tr.get("to"), tr.get("to_type")) in trigger_set]

    for tr in upsert_triggers:
        key = (tr.get("from"), tr.get("to"), tr.get("to_type"))
        if key in trigger_set:
            continue
        trigger_set.add(key)
        triggers.append(tr)

    triggers = dedupe_triggers(triggers)

    nkg["elements"] = elements
    nkg["triggers"] = triggers

    return before_elements, len(elements), before_triggers, len(triggers)


def recompute_derived(nkg_obj: dict, module, repo_root: Path, recompute_verification: bool) -> None:
    nkg_obj["cypher_payload"] = module.build_cypher_payload(nkg_obj["nkg"])

    if not recompute_verification:
        return

    source_html = nkg_obj.get("meta", {}).get("source_html", "")
    if not source_html:
        return

    html_path = (repo_root / source_html).resolve()
    if not html_path.exists():
        print(f"warning: source_html not found for verification: {html_path}")
        return

    html = html_path.read_text(encoding="utf-8", errors="ignore")
    dom_id_lines = module.parse_dom_ids_with_lines(html)
    dom_ids = set(dom_id_lines.keys())
    nkg_obj["verification"] = module.compute_verification(nkg_obj["nkg"], dom_ids, dom_id_lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Patch NKG JSON and regenerate dependent sections")
    parser.add_argument("--input", required=True, help="Input NKG JSON path")
    parser.add_argument("--ops", required=True, help="Patch operations JSON path")
    parser.add_argument("--output", default="", help="Output path (default: overwrite input)")
    parser.add_argument(
        "--skip-verification",
        action="store_true",
        help="Skip recomputing verification section",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    ops_path = Path(args.ops).resolve()
    output_path = Path(args.output).resolve() if args.output else input_path

    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")
    if not ops_path.exists():
        raise FileNotFoundError(f"Ops file not found: {ops_path}")

    repo_root = Path(__file__).resolve().parent.parent
    module = load_chunked_module(repo_root)

    nkg_obj = load_json(input_path)
    ops = load_json(ops_path)

    before_elements, after_elements, before_triggers, after_triggers = apply_ops(nkg_obj, ops)
    recompute_derived(
        nkg_obj=nkg_obj,
        module=module,
        repo_root=repo_root,
        recompute_verification=not args.skip_verification,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(output_path, nkg_obj)

    print(f"saved: {output_path}")
    print(f"elements: {before_elements} -> {after_elements}")
    print(f"triggers: {before_triggers} -> {after_triggers}")
    if "verification" in nkg_obj:
        v = nkg_obj["verification"]
        print(f"coverage: {v.get('dom_ids_in_nkg_total', 0)}/{v.get('dom_ids_total', 0)} ({v.get('coverage_percent', 0)}%)")


if __name__ == "__main__":
    main()
