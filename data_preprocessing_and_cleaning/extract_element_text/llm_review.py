"""
llm_review.py
=============
LLM-powered review of element text labels.

Supports two modes:
  --mode local   : Direct Ollama (default, http://localhost:11434)
  --mode remote  : GPU proxy server (same as chunked_html_to_nkg.py)

USAGE:
  cd data_preprocessing_and_cleaning/extract_element_text

  # Local Ollama
  python llm_review.py
  python llm_review.py --model qwen3:8b --only customer_attendance_leave.nkg.json

  # Remote GPU server
  python llm_review.py --mode remote --server-url https://youtube.com --token some-secret-token --model gemma4:27b
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib import error, request

try:
    from dotenv import load_dotenv
    if not load_dotenv(".env") and not load_dotenv("../.env"):
        pass
except ImportError:
    # Manual fallback for simple .env files if python-dotenv is missing
    for env_file in [".env", "../.env"]:
        p = Path(env_file)
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip().strip("'\"")

# -----------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------
DEFAULT_OLLAMA_URL  = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_SERVER_URL  = os.getenv("OLLAMA_PROXY_URL", "https://youtube.com")
DEFAULT_TOKEN       = os.getenv("OLLAMA_PROXY_TOKEN", "some-secret-token")

# Strip quotes if they were loaded from .env literally
if DEFAULT_TOKEN:
    DEFAULT_TOKEN = DEFAULT_TOKEN.strip("'\"")
if DEFAULT_SERVER_URL:
    DEFAULT_SERVER_URL = DEFAULT_SERVER_URL.strip("'\"")

DEFAULT_LOCAL_MODEL = "gemma4:31b"
DEFAULT_REMOTE_MODEL = "gemma4:31b"
DEFAULT_TIMEOUT     = 600  # Increased to 10 minutes

REPORT_PATH   = Path("../data/element_text_review/review_report.json")
SUMMARY_PATH  = Path("../data/element_text_review/review_summary.txt")
PROGRESS_PATH = Path("../data/element_text_review/llm_review_progress.json")

# -----------------------------------------------------------------------
# SYSTEM PROMPT
# -----------------------------------------------------------------------
SYSTEM_PROMPT = """You are reviewing extracted UI element text labels for a web-based HR SaaS application.
Your task is to decide whether each element's text should be INCLUDE or SKIP.

CONTEXT:
- This is a snapshot of the app. The demo account uses "Dummy" as the company/tenant name.
  Any occurrence of "Dummy" in text is a placeholder, NOT real employee or company data.
- Employee names like "Mr. Dummy Dummy", "agus", "Veleroy Andika" are snapshot demo data.

INCLUDE — include if ANY of these apply:
1. INFORMATIONAL: The text EXPLAINS a feature, field, setting, or workflow.
   Helps a user understand what something does, conditions, or how it works.
   Examples: tooltips, help notes, feature descriptions, approval workflow explanations,
   section intros, notes about midnight calculation, etc.
2. LEXICAL SEARCHABLE: A user might search for this element by its exact visible label.
   Includes: button labels, input placeholders, tab names, dropdown option labels, 
   field labels, select placeholder text ("Pilih Kantor", "Pilih Jadwal", etc.).
3. NAVIGATIONAL LABEL: Clear menu item, breadcrumb, or page title text.
4. TABLE HEADERS / GLIMPSE: Text that represents the column headers of a data table.
   Even if the text is from a table or section element, if it contains ONLY or MOSTLY
   column header names (e.g. "ID / NIK Nama Karyawan Jabatan Kantor Lama Bekerja"),
   it is INCLUDE — this tells the agent what data the table displays.

SKIP — skip if the text matches these patterns:
1. DYNAMIC RECORD DATA: Real employee names (non-Dummy), specific dates as records,
   numeric IDs from real records, specific real company names, JSON blobs.
2. AGGREGATED NOISE: A wall of text that is clearly a concatenation of many unrelated
   child elements — mixing labels, data rows, navigation, buttons, all at once.
   (A short column-header-only string from a table is NOT this — see rule 4 above.)
3. ERROR TEMPLATES: Contains the exact string "Warning Change a few things up and try
   submitting again." — this is a UI error placeholder, not a real label.
4. EMPTY OR PURELY STRUCTURAL: text=None, purely numeric (calendar day numbers only).
5. CONTAINER SUPERSET (deduplication): The element is a section/modal/container whose
   text is clearly the concatenation of smaller, more specific child elements that are
   ALSO present in this list (either as candidates or already INCLUDE).
   Example: a modal element has text "Simpan Reset Pilih Kantor Tulis Deskripsi..." —
   these are all individually listed buttons/inputs already. SKIP the modal.
   INCLUDE the individual children instead.
   Rationale: duplicating the same text on both a container and its children pollutes
   both the embedding vector index and the Levenshtein lexical search.

Respond with ONLY valid JSON. No explanation. Format:
{
  "decisions": {
    "<nkg_id>": "INCLUDE",
    "<nkg_id>": "SKIP"
  }
}
"""

# -----------------------------------------------------------------------
# LLM backends
# -----------------------------------------------------------------------
def ollama_chat(ollama_url: str, model: str, system_prompt: str, user_prompt: str, timeout: int) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 8192},
        "format": "json",
    }
    req = request.Request(
        f"{ollama_url.rstrip('/')}/api/chat",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["message"]["content"]
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Cannot connect to Ollama at {ollama_url}: {exc}") from exc


def remote_chat(server_url: str, token: str, model: str, system_prompt: str, user_prompt: str, timeout: int) -> str:
    """
    Transparent Ollama proxy — POST to /api/chat with X-API-Token header.
    (Same pattern as 1_try_embedding.ipynb)
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 8192},
        "format": "json",
    }
    req = request.Request(
        f"{server_url.rstrip('/')}/api/chat",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-API-Token": token,
        },
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["message"]["content"]
    except error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} from remote: {body_text[:500]}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Cannot connect to remote server at {server_url}: {exc}") from exc


def extract_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}



# -----------------------------------------------------------------------
# Summary writer
# -----------------------------------------------------------------------
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
    print(f"Summary written -> {summary_path}")


# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="LLM-powered review of element text labels.")
    parser.add_argument("--mode",       choices=["local", "remote"], default="local",
                        help="'local' = direct Ollama, 'remote' = GPU proxy server")
    # Local args
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL,
                        help="Ollama base URL (local mode)")
    # Remote args
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL,
                        help="GPU proxy server URL (remote mode)")
    parser.add_argument("--token",      default=DEFAULT_TOKEN,
                        help="API token for the remote server")
    # Shared
    parser.add_argument("--model",      default=None,
                        help="Model name (default: qwen3:8b local, gemma4:27b remote)")
    parser.add_argument("--timeout",    type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--only",       default=None,
                        help="Process only filename(s) matching this substring")
    parser.add_argument("--force",      action="store_true",
                        help="Re-review pages already marked done in progress file")
    parser.add_argument("--dump-prompt", action="store_true",
                        help="Dump the exact prompt to a file instead of sending it to the LLM")
    args = parser.parse_args()

    model = args.model or (DEFAULT_LOCAL_MODEL if args.mode == "local" else DEFAULT_REMOTE_MODEL)

    if args.mode == "remote":
        masked_token = f"{args.token[:8]}...{args.token[-4:]}" if args.token else "None"
        print(f"Using Token: {masked_token}")

    if not REPORT_PATH.exists():
        print(f"Error: {REPORT_PATH} not found. Run extract_element_text.py first.")
        sys.exit(1)

    with REPORT_PATH.open("r", encoding="utf-8") as f:
        report: dict = json.load(f)

    progress: dict = {}
    if PROGRESS_PATH.exists():
        with PROGRESS_PATH.open("r", encoding="utf-8") as f:
            progress = json.load(f)

    filenames = list(report.keys())
    if args.only:
        filenames = [fn for fn in filenames if args.only in fn]
        if not filenames:
            print(f"No file matching '{args.only}' found in report.")
            sys.exit(1)

    print(f"Mode: {args.mode}  |  Model: {model}  |  Pages: {len(filenames)}\n")

    total_updated = 0

    for filename in filenames:
        if not args.force and progress.get(filename) == "done":
            print(f"  [skip — already done]     {filename}")
            continue

        elements = report[filename]

        # Only candidates that have text (skip text=None — LLM can't decide on nothing)
        candidates = [
            e for e in elements
            if e.get("status") in ("REVIEW", "SKIP") and e.get("text") is not None
        ]
        already_included = [
            e for e in elements
            if e.get("status") == "INCLUDE" and e.get("text") is not None
        ]

        if not candidates:
            print(f"  [no candidates]           {filename}")
            progress[filename] = "done"
            continue

        def md_table(rows: list, label: str) -> str:
            lines = [f"\n### {label}\n", "| nkg_id | type | text |", "| --- | --- | --- |"]
            for e in rows:
                text_val = (e.get("text") or "").replace("|", "\\|")
                if len(text_val) > 300:
                    text_val = text_val[:297] + "..."
                lines.append(f"| {e['nkg_id']} | {e['type']} | {text_val} |")
            return "\n".join(lines)

        user_prompt = (
            f"Page: **{filename}**\n"
            + md_table(already_included, "Already INCLUDE (for context, no decision needed)")
            + "\n"
            + md_table(candidates, f"Candidates — decide INCLUDE or SKIP for each ({len(candidates)} items)")
        )

        print(f"  [{filename}]  {len(candidates)} candidates + {len(already_included)} context ... ", end="", flush=True)
        t0 = time.time()

        try:
            if args.dump_prompt:
                dump_file = f"prompt_{filename}.txt"
                with open(dump_file, "w", encoding="utf-8") as f:
                    f.write(SYSTEM_PROMPT + "\n\n" + "-"*80 + "\n\n" + user_prompt)
                print(f"Prompt dumped to {dump_file}")
                continue

            if args.mode == "local":
                raw = ollama_chat(args.ollama_url, model, SYSTEM_PROMPT, user_prompt, args.timeout)
            else:
                raw = remote_chat(args.server_url, args.token, model, SYSTEM_PROMPT, user_prompt, args.timeout)

            result = extract_json(raw)
            decisions = result.get("decisions", {})
            if len(decisions) == 0:
                print(f"\n[DEBUG] LLM output could not be parsed as JSON. Raw output snippet:\n{raw[:500]}\n")
        except Exception as exc:
            print(f"\n  [ERROR] {filename}: {exc}")
            continue

        elapsed = time.time() - t0

        # Apply decisions
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
        print(f"done ({elapsed:.0f}s)  {page_updated} changed")

        progress[filename] = "done"

        # Save after every page (safe resume)
        with REPORT_PATH.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        with PROGRESS_PATH.open("w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)

        # Regenerate summary after every page so user can see progress in real time
        write_summary(report, SUMMARY_PATH)

    print(f"\nTotal elements updated: {total_updated}")
    print("Done.")


if __name__ == "__main__":
    main()
