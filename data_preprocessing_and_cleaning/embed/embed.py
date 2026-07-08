"""
embed.py — NKG Element Embedding Generator (qwen3-embedding optimised)

PURPOSE
-------
Generates vector embeddings for every Element node in the NKG JSON files so that
the navigational agent can find the right element via semantic similarity at runtime.

RETRIEVAL SCENARIO (how the agent uses these embeddings at runtime)
-------------------------------------------------------------------
1. User says something like: "I want to add a new holiday" or "find the button to delete employee"
2. Agent constructs a short intent string.
3. Agent embeds the intent using the SAME model + QUERY_INSTRUCTION (see constant below).
4. Agent does cosine / dot-product similarity against stored element embeddings.
5. Agent gets the top-k (nkg_id, page_id, selector) → navigates to the right element.

WHAT WE EMBED PER ELEMENT
--------------------------
We build a rich natural-language passage that a retriever can match against a
user's navigational intent. It combines:

  • Page context  — page title + URL path (locates the element in the app)
  • Element type  — "button", "input", "modal", "table", etc. (interaction kind)
  • Element ID    — often descriptive, e.g. "btn_modal_add", "add_description"
  • Description   — the LLM-extracted natural-language description of what the
                    element does and how to interact with it

Format:
    "Halaman: {page_title} ({page_id})
     Elemen: {type} [{id}]
     Fungsi: {desc}"

WHY THIS FORMAT
---------------
• The model sees *semantic intent* (desc) alongside *structural signal* (type + id).
• Including the page title means the embedding differentiates elements that share
  the same DOM id across pages (e.g. a generic #content div).
• The Bahasa Indonesia phrasing matches the language of the descriptions and the
  likely user queries.

QWEN3-EMBEDDING INSTRUCTION PROMPTING
--------------------------------------
qwen3-embedding supports task-instruction prompting in the format:
    "Instruct: <task>\nQuery: <text>"

We use an ASYMMETRIC setup:
  • DOCUMENT_INSTRUCTION — describes the stored passages (UI elements).
  • QUERY_INSTRUCTION    — describes the runtime queries (user navigation intents).
    *** The agent MUST use QUERY_INSTRUCTION when embedding user queries. ***

Both constants are exported at the bottom of this file for import by the agent.

OUTPUT FILES
-----------
1. embeddings_neo4j.jsonl   — one line per element: {"nkg_id": "...", "embedding": [...]}
   → fed into insert.ipynb to set el.embedding on each Element node

2. embeddings_full.json     — full records: {nkg_id, page_id, id, type, desc, text, embedding}
   → used for similarity search, FAISS indexing, offline analysis

USAGE
-----
# Dry-run (shows text that will be embedded, no API calls):
python embed/embed.py --dry-run

# Full run with defaults:
python embed/embed.py

# Custom data dir / outputs:
python embed/embed.py \\
    --data-dir data/nkg_gpu3_fix_orphans \\
    --output-neo4j embed/embeddings_neo4j.jsonl \\
    --output-json  embed/embeddings_full.json

# Resume after a crash (skips already-embedded nkg_ids):
python embed/embed.py --resume

# Different server:
python embed/embed.py --ollama-url http://gpu-server:11434
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib import error, request

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_OLLAMA_URL  = "http://localhost:11434"
DEFAULT_EMBED_MODEL = "qwen3-embedding:8b"
DEFAULT_DATA_DIR    = "data/nkg_gpu3_fix_orphans_with text"
DEFAULT_OUT_NEO4J   = "data/neo4j-query/embeddings_neo4j.jsonl"
DEFAULT_OUT_JSON    = "data/full-json/embeddings_full.json"

# ---------------------------------------------------------------------------
# Instruction prompts for qwen3-embedding (asymmetric retrieval)
#
# IMPORTANT: The AGENT must use QUERY_INSTRUCTION when embedding user queries
#            at runtime so the embedding space is aligned correctly.
# ---------------------------------------------------------------------------

DOCUMENT_INSTRUCTION = (
    "Represent a UI element in a web application so that it can be retrieved "
    "when a user describes their navigation intent or the action they want to perform."
)

QUERY_INSTRUCTION = (
    "Given a user's navigation intent or action description, find the most relevant "
    "UI element in the web application that the user wants to interact with."
)


# ---------------------------------------------------------------------------
# Embedding text builder
# ---------------------------------------------------------------------------

def build_embed_text(
    page_id: str,
    page_title: str,
    element: dict[str, Any],
) -> str:
    """
    Build the document text that will be embedded for one element.

    Format (Indonesian, matching the description language):
        Halaman: {page_title} ({page_id})
        Elemen: {type} [{id}]
        Fungsi: {desc}
        Teks UI: {text}  <- only if text exists (from element text review)

    The page title + id context ensures that elements sharing the same DOM id
    across different pages (e.g. a generic #content section) produce meaningfully
    different embeddings.

    'Teks UI' is the actual visible text extracted from the HTML, which helps
    the embedding model align user queries with the real on-screen label.
    It is only included when the text review confirmed the element as INCLUDE
    (i.e., the text field was injected by apply_text_to_nkg.py).
    """
    elem_id   = element.get("id", "")
    elem_type = element.get("type", "element")
    desc      = (element.get("desc") or "").strip()
    ui_text   = (element.get("text") or "").strip()

    lines = [
        f"Halaman: {page_title} ({page_id})",
        f"Elemen: {elem_type} [{elem_id}]",
        f"Fungsi: {desc}",
    ]
    if ui_text:
        lines.append(f"Teks UI: {ui_text}")
    return "\n".join(lines)


def build_instruction_prompt(instruction: str, text: str) -> str:
    """Wrap text in qwen3-embedding instruction format."""
    return f"Instruct: {instruction}\nQuery: {text}"


# ---------------------------------------------------------------------------
# Ollama embedding call
# ---------------------------------------------------------------------------

def ollama_embed(
    ollama_url: str,
    model: str,
    text: str,
    timeout: int = 120,
) -> list[float]:
    """
    Call Ollama /api/embeddings and return the embedding vector.
    The text should already include the instruction prefix if needed.
    """
    payload = json.dumps({"model": model, "prompt": text}).encode("utf-8")
    req = request.Request(
        f"{ollama_url.rstrip('/')}/api/embeddings",
        method="POST",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["embedding"]
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} from Ollama: {body[:500]}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Cannot reach Ollama at {ollama_url}: {exc}") from exc


# ---------------------------------------------------------------------------
# Resume helpers
# ---------------------------------------------------------------------------

def load_done_nkg_ids(neo4j_path: Path) -> set[str]:
    done: set[str] = set()
    if not neo4j_path.exists():
        return done
    with neo4j_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                nkg_id = json.loads(line).get("nkg_id")
                if nkg_id:
                    done.add(nkg_id)
            except json.JSONDecodeError:
                pass
    return done


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate qwen3-embedding vectors for all NKG elements."
    )
    parser.add_argument("--data-dir",     default=DEFAULT_DATA_DIR,
                        help=f"Directory with .nkg.json files (default: {DEFAULT_DATA_DIR})")
    parser.add_argument("--output-neo4j", default=DEFAULT_OUT_NEO4J,
                        help=f"JSONL output for Neo4j SET (default: {DEFAULT_OUT_NEO4J})")
    parser.add_argument("--output-json",  default=DEFAULT_OUT_JSON,
                        help=f"Full JSON output (default: {DEFAULT_OUT_JSON})")
    parser.add_argument("--model",        default=DEFAULT_EMBED_MODEL,
                        help=f"Ollama embedding model (default: {DEFAULT_EMBED_MODEL})")
    parser.add_argument("--ollama-url",   default=DEFAULT_OLLAMA_URL,
                        help=f"Ollama base URL (default: {DEFAULT_OLLAMA_URL})")
    parser.add_argument("--timeout",      type=int, default=120,
                        help="Per-request timeout in seconds (default: 120)")
    parser.add_argument("--dry-run",      action="store_true",
                        help="Show embedding texts without making API calls or writing files")
    parser.add_argument("--resume",       action="store_true",
                        help="Skip nkg_ids already present in the output JSONL (crash recovery)")
    args = parser.parse_args()

    data_dir  = Path(args.data_dir)
    out_neo4j = Path(args.output_neo4j)
    out_json  = Path(args.output_json)

    if not data_dir.exists():
        print(f"[ERROR] Data dir not found: {data_dir}")
        sys.exit(1)

    json_files = sorted(data_dir.glob("*.json"))
    if not json_files:
        print(f"[ERROR] No .json files in {data_dir}")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Collect all elements
    # -----------------------------------------------------------------------
    records: list[dict[str, Any]] = []

    for filepath in json_files:
        try:
            with filepath.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            print(f"[WARN] Cannot read {filepath.name}: {exc}")
            continue

        nkg        = data.get("nkg", {})
        page       = nkg.get("page", {})
        page_id    = page.get("id", "")
        page_title = page.get("title", "")
        elements   = nkg.get("elements", [])

        for elem in elements:
            if not isinstance(elem, dict) or not elem.get("id"):
                continue

            elem_id = elem["id"]
            nkg_id  = f"{page_id}/{elem_id}"
            text    = build_embed_text(page_id, page_title, elem)
            # The full prompt sent to Ollama includes the document instruction
            prompt  = build_instruction_prompt(DOCUMENT_INSTRUCTION, text)

            records.append({
                "nkg_id":    nkg_id,
                "page_id":   page_id,
                "id":        elem_id,
                "type":      elem.get("type", ""),
                "desc":      elem.get("desc", ""),
                "text":      text,    # clean text (for inspection / FAISS)
                "prompt":    prompt,  # what actually goes to Ollama
            })

    # -----------------------------------------------------------------------
    # Header
    # -----------------------------------------------------------------------
    print(f"Mode        : {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print(f"Model       : {args.model}")
    print(f"Server      : {args.ollama_url}")
    print(f"Files       : {len(json_files)}")
    print(f"Elements    : {len(records)}")
    print(f"Doc instr.  : {DOCUMENT_INSTRUCTION[:80]}...")
    print(f"Query instr.: {QUERY_INSTRUCTION[:80]}...")

    if args.dry_run:
        print("\nSample embedding prompts (first 3 elements):\n")
        for r in records[:3]:
            print(f"  nkg_id : {r['nkg_id']}")
            print(f"  PROMPT :\n{r['prompt']}")
            print()
        print(f"  ... and {max(0, len(records) - 3)} more elements.\n")
        print("QUERY_INSTRUCTION the agent should use at runtime:")
        print(f"  Instruct: {QUERY_INSTRUCTION}")
        print(f"  Query: <user intent here>")
        return

    # -----------------------------------------------------------------------
    # Resume: skip already-done nkg_ids
    # -----------------------------------------------------------------------
    already_done: set[str] = set()
    if args.resume:
        already_done = load_done_nkg_ids(out_neo4j)
        print(f"Resume      : {len(already_done)} already done, skipping")

    todo = [r for r in records if r["nkg_id"] not in already_done]
    print(f"To embed    : {len(todo)}")
    print(f"Out neo4j   : {out_neo4j}")
    print(f"Out full    : {out_json}")
    print("-" * 60)

    if not todo:
        print("Nothing to embed. Use --resume to add new elements, or remove output files to re-embed all.")
        return

    # Ensure output dirs exist
    out_neo4j.parent.mkdir(parents=True, exist_ok=True)
    out_json.parent.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # Embed and write
    # -----------------------------------------------------------------------
    neo4j_fp = out_neo4j.open("a" if args.resume else "w", encoding="utf-8")

    # For --resume, preload existing full records
    full_records: list[dict[str, Any]] = []
    if args.resume and out_json.exists():
        try:
            with out_json.open("r", encoding="utf-8") as f:
                full_records = json.load(f)
        except Exception:
            full_records = []

    ok     = 0
    errors: list[tuple[str, str]] = []
    t_start = time.time()

    try:
        for i, rec in enumerate(todo, start=1):
            nkg_id = rec["nkg_id"]
            try:
                embedding = ollama_embed(
                    ollama_url=args.ollama_url,
                    model=args.model,
                    text=rec["prompt"],   # instruction-wrapped prompt
                    timeout=args.timeout,
                )

                # Neo4j JSONL — one line, flush immediately for crash safety
                neo4j_obj = {"nkg_id": nkg_id, "embedding": embedding}
                neo4j_fp.write(json.dumps(neo4j_obj, ensure_ascii=False) + "\n")
                neo4j_fp.flush()

                # Full record (drop the prompt field; keep clean text)
                full_records.append({
                    "nkg_id":    nkg_id,
                    "page_id":   rec["page_id"],
                    "id":        rec["id"],
                    "type":      rec["type"],
                    "desc":      rec["desc"],
                    "text":      rec["text"],
                    "embedding": embedding,
                })

                elapsed = time.time() - t_start
                rate    = i / elapsed
                eta     = (len(todo) - i) / rate if rate > 0 else 0
                dim     = len(embedding)
                print(f"  [{i:>5}/{len(todo)}]  {nkg_id:<65}  dim={dim}  ETA={eta:.0f}s")
                ok += 1

            except Exception as exc:
                print(f"  [ERR] {nkg_id}: {exc}")
                errors.append((nkg_id, str(exc)))

    finally:
        neo4j_fp.close()

    # Write full JSON at the end
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(full_records, f, ensure_ascii=False, indent=2)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    elapsed = time.time() - t_start
    print("\n" + "=" * 60)
    print(f"DONE in {elapsed:.1f}s  ({elapsed / max(ok, 1):.2f}s per element)")
    print(f"Embedded : {ok}")
    print(f"Errors   : {len(errors)}")
    if errors:
        print("\nFailed nkg_ids:")
        for nkg_id, msg in errors[:20]:
            print(f"  {nkg_id}: {msg}")

    if out_neo4j.exists():
        print(f"\nOutputs:")
        print(f"  Neo4j JSONL : {out_neo4j}  ({out_neo4j.stat().st_size // 1024} KB)")
        print(f"  Full JSON   : {out_json}  ({out_json.stat().st_size // 1024} KB)")

    print(f"\n--- AGENT USAGE REMINDER ---")
    print(f"When embedding a user query at runtime, use:")
    print(f"  prompt = f'Instruct: {QUERY_INSTRUCTION}\\nQuery: {{user_intent}}'")
    print(f"  embedding = ollama_embed(model='{args.model}', text=prompt)")


if __name__ == "__main__":
    main()
