from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from chunked_html_to_nkg import (
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    DEFAULT_REMOTE_API_TOKEN,
    DEFAULT_REMOTE_SERVER_URL,
    DEFAULT_TIMEOUT,
    SELECTOR_REPAIR_SYSTEM_PROMPT,
    build_cypher_payload,
    build_selector_repair_prompt,
    compute_verification,
    extract_json_from_text,
    ollama_chat,
    parse_dom_ids,
    parse_dom_ids_with_lines,
    remote_repair_selectors,
    validate_selector_targets,
)


def load_result(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("nkg"), dict):
        return payload, payload["nkg"]
    if isinstance(payload, dict):
        return {"nkg": payload}, payload
    raise ValueError("Input result must be a JSON object")


def run_selector_repair_only(args: argparse.Namespace) -> dict[str, Any]:
    started = time.time()

    input_path = Path(args.input_result)
    html_path = Path(args.html)

    if not input_path.exists():
        raise FileNotFoundError(f"Input result not found: {input_path}")
    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    result_payload, nkg = load_result(input_path)
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    dom_ids = parse_dom_ids(html)
    dom_id_lines = parse_dom_ids_with_lines(html)

    selector_validation = validate_selector_targets(nkg, html, dom_ids)
    if not selector_validation.get("available"):
        raise RuntimeError("Selector validation unavailable (BeautifulSoup missing)")

    failed_items = list(selector_validation.get("failed", []))
    print(f"[SELECTOR] initial failed: {len(failed_items)}")

    selector_repair: dict[str, Any] = {
        "attempted": bool(failed_items),
        "applied_updates": 0,
        "requested_ids": min(len(failed_items), max(1, args.selector_repair_max)),
        "error": None,
        "batches": [],
    }

    if failed_items:
        to_fix = failed_items[: max(1, args.selector_repair_max)]
        batch_size = max(1, args.repair_batch_size)

        by_id = {
            e.get("id"): e
            for e in nkg.get("elements", [])
            if isinstance(e, dict) and e.get("id")
        }

        for i in range(0, len(to_fix), batch_size):
            batch = to_fix[i : i + batch_size]
            batch_no = (i // batch_size) + 1
            print(f"[SELECTOR] repairing batch {batch_no} ({len(batch)} items)")

            try:
                if args.backend == "remote":
                    repair_data = remote_repair_selectors(
                        server_url=args.remote_server_url,
                        api_token=args.remote_api_token,
                        filename=html_path.name,
                        html_content=html,
                        page_url=args.page_url,
                        page_title=args.page_title,
                        elements_to_fix=batch,
                        preferred_model=args.model,
                        timeout_seconds=args.timeout,
                        use_fallback=args.remote_use_fallback,
                    )
                else:
                    repair_prompt = build_selector_repair_prompt(
                        page_url=args.page_url,
                        page_title=args.page_title,
                        page_slug=args.page_slug,
                        failed_elements=batch,
                        existing_nkg=nkg,
                        html=html,
                    )
                    repair_raw = ollama_chat(
                        ollama_url=args.ollama_url,
                        model=args.model,
                        system_prompt=SELECTOR_REPAIR_SYSTEM_PROMPT,
                        user_prompt=repair_prompt,
                        timeout_seconds=args.timeout,
                        temperature=args.temperature,
                        num_predict=args.num_predict,
                        use_json_mode=True,
                        stream=False,
                        think=False,
                        print_stream=False,
                    )
                    repair_data = extract_json_from_text(repair_raw)

                repairs = repair_data.get("elements", []) if isinstance(repair_data, dict) else []
                if not isinstance(repairs, list):
                    raise ValueError("Selector repair must return elements[] list")

                applied = 0
                for item in repairs:
                    if not isinstance(item, dict):
                        continue
                    element_id = str(item.get("id", "")).strip()
                    selector = str(item.get("selector", "")).strip()
                    if not element_id or not selector or element_id not in by_id:
                        continue
                    by_id[element_id]["selector"] = selector
                    applied += 1

                selector_repair["applied_updates"] += applied
                selector_repair["batches"].append(
                    {"batch": batch_no, "requested": len(batch), "applied": applied, "error": None}
                )
            except Exception as exc:  # noqa: BLE001
                selector_repair["error"] = str(exc)
                selector_repair["batches"].append(
                    {"batch": batch_no, "requested": len(batch), "applied": 0, "error": str(exc)}
                )
                print(f"[SELECTOR] batch {batch_no} error: {exc}")
                if not args.continue_on_error:
                    break

        selector_validation = validate_selector_targets(nkg, html, dom_ids)
        print(f"[SELECTOR] final failed: {selector_validation.get('summary', {}).get('failed_total', 0)}")

    verification = compute_verification(nkg, dom_ids, dom_id_lines)
    cypher_payload = build_cypher_payload(nkg)

    result_payload["nkg"] = nkg
    result_payload["selector_validation"] = selector_validation
    result_payload["selector_repair"] = selector_repair
    result_payload["verification"] = verification
    result_payload["cypher_payload"] = cypher_payload

    meta = result_payload.setdefault("meta", {})
    if isinstance(meta, dict):
        meta["selector_repair_only_runtime_seconds"] = round(time.time() - started, 2)

    return result_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run selector validation + repair only on existing NKG result JSON")
    parser.add_argument("--input-result", required=True, help="Path to existing .nkg.json result")
    parser.add_argument("--html", required=True, help="Path to source HTML used for validation")
    parser.add_argument("--out", required=True, help="Output path for repaired result JSON")

    parser.add_argument("--backend", choices=["local", "remote"], default="local")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--num-predict", type=int, default=4096)

    parser.add_argument("--selector-repair-max", type=int, default=120)
    parser.add_argument("--repair-batch-size", type=int, default=25)
    parser.add_argument("--continue-on-error", action="store_true")

    parser.add_argument("--page-url", default="/customer/employee")
    parser.add_argument("--page-title", default="Employee")
    parser.add_argument("--page-slug", default="employee")

    parser.add_argument("--remote-server-url", default=DEFAULT_REMOTE_SERVER_URL)
    parser.add_argument("--remote-api-token", default=DEFAULT_REMOTE_API_TOKEN)
    parser.add_argument("--remote-use-fallback", action="store_true")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = run_selector_repair_only(args)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
