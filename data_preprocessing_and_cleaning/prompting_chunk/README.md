# NKG Extraction Module

This directory contains all scripts and documentation for **HTML → NKG (Navigational Knowledge Graph) extraction**.

## 📁 Directory Structure

```
prompting_chunk/
├── Core Scripts
│   ├── chunked_html_to_nkg.py        [Main extractor]
│   ├── server.py                     [Optional FastAPI wrapper]
│   ├── batch_process_nkg.py          [Batch processor]
│   ├── nkg_verify.py                 [Analysis tool]
│   └── inspect_dryrun.py             [Dry-run inspector]
│
└── Documentation
    ├── QUICKSTART.md                 [Start here - 5-minute guide]
    ├── IMPLEMENTATION_SUMMARY.md     [What's been built]
    ├── CHUNKED_EXTRACTION_GUIDE.md   [Detailed reference]
    ├── NKG_SCHEMA.md                 [JSON schema spec]
    ├── JSON_MODE_UPDATE.md           [JSON mode enhancement]
    └── README_NKG_EXTRACTION.md      [Comprehensive guide]
```

---

## 🚀 Quick Start

Default backend for `chunked_html_to_nkg.py` is `local` (`http://localhost:11434`). Use `--backend remote` only when calling the remote FastAPI proxy.

### Start here - from prompting_chunk/:
```bash
# 1. Inspect prompts (no Ollama needed)
python chunked_html_to_nkg.py --html ../data/cleaned_html/customer_employee.html --out ../data/nkg_chunked_output/test.dryrun.json --dry-run

# 2. Read the first 1500 chars of prompts
python inspect_dryrun.py

# 3. Extract with Ollama (requires `ollama serve`)
python chunked_html_to_nkg.py --html ../data/cleaned_html/customer_employee.html --out ../data/nkg_chunked_output/customer_employee.nkg.json --model gemma4:31b --stream

# 4. Analyze result
python nkg_verify.py show ../data/nkg_chunked_output/customer_employee.nkg.json

# 5. Batch all pages
python batch_process_nkg.py --input-dir ../data/cleaned_html --output-dir ../data/nkg_chunked_output --limit 5
```

### Or from repo root:
```bash
# 1. Inspect prompts (no Ollama needed)
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/test.dryrun.json --dry-run

# 2. Read the first 1500 chars of prompts
python prompting_chunk/inspect_dryrun.py

# 3. Extract with Ollama (requires `ollama serve`)
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/customer_employee.nkg.json --model gemma4:31b --stream

# 4. Analyze result
python prompting_chunk/nkg_verify.py show data/nkg_chunked_output/customer_employee.nkg.json

# 5. Batch all pages
python prompting_chunk/batch_process_nkg.py --input-dir data/cleaned_html --output-dir data/nkg_chunked_output --limit 5
```

---

## 📖 Documentation Tips

| Need | File |
|------|------|
| **Getting started in 5 min** | [`QUICKSTART.md`](QUICKSTART.md) |
| **How chunking works** | [`CHUNKED_EXTRACTION_GUIDE.md`](CHUNKED_EXTRACTION_GUIDE.md) |
| **JSON output schema** | [`NKG_SCHEMA.md`](NKG_SCHEMA.md) |
| **What's implemented** | [`IMPLEMENTATION_SUMMARY.md`](IMPLEMENTATION_SUMMARY.md) |
| **JSON mode feature** | [`JSON_MODE_UPDATE.md`](JSON_MODE_UPDATE.md) |
| **Full reference** | [`README_NKG_EXTRACTION.md`](README_NKG_EXTRACTION.md) |

---

## 🔧 Script Reference

### `chunked_html_to_nkg.py` — Main Extractor
**Purpose:** Transform one HTML page into NKG JSON with chunking, verification, and Cypher payload.

From prompting_chunk/:
```bash
python chunked_html_to_nkg.py --html ../data/cleaned_html/customer_employee.html --out ../data/nkg_chunked_output/customer_employee.nkg.json --model gemma4:31b --stream
# Optional flags (append as needed): --dry-run --one-shot-example ../previous.nkg.json --patch-missing
```

Or from repo root:
```bash
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/customer_employee.nkg.json --model gemma4:31b --stream
```

Local with model thinking output (repo root):
```bash
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/customer_employee.nkg.json --model gemma4:31b --stream --show-thinking
```

Remote server mode (from repo root):
```bash
python prompting_chunk/chunked_html_to_nkg.py --backend remote --remote-server-url https://youtube.com --remote-api-token some-secret-token-2026 --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/customer_employee.nkg.json --model deepseek-r1:70b
```

Note: `--stream` and `--show-thinking` are local-backend features.

### `batch_process_nkg.py` — Batch Processor
**Purpose:** Process multiple pages with automatic one-shot prompting.

From prompting_chunk/:
```bash
python batch_process_nkg.py --input-dir ../data/cleaned_html --output-dir ../data/nkg_chunked_output --limit 10 --model gemma4:31b
```

Or from repo root:
```bash
python prompting_chunk/batch_process_nkg.py --input-dir data/cleaned_html --output-dir data/nkg_chunked_output --limit 10
```

### `nkg_verify.py` — Analysis Tool
**Purpose:** Inspect, compare, and export NKG results.

From prompting_chunk/:
```bash
# Show detailed breakdown
python nkg_verify.py show ../data/nkg_chunked_output/page.nkg.json

# Compare two extractions
python nkg_verify.py compare ../data/nkg_chunked_output/page1.nkg.json ../data/nkg_chunked_output/page2.nkg.json

# Export Cypher statements
python nkg_verify.py export-cypher ../data/nkg_chunked_output/page.nkg.json --output ../page.cypher
```

Or from repo root:
```bash
# Show detailed breakdown
python prompting_chunk/nkg_verify.py show data/nkg_chunked_output/page.nkg.json

# Compare two extractions
python prompting_chunk/nkg_verify.py compare data/nkg_chunked_output/page1.nkg.json data/nkg_chunked_output/page2.nkg.json

# Export Cypher statements
python prompting_chunk/nkg_verify.py export-cypher data/nkg_chunked_output/page.nkg.json --output page.cypher
```

### `inspect_dryrun.py` — Dry-Run Inspector
**Purpose:** Peek at prompts before running expensive LLM calls.

From prompting_chunk/:
```bash
python inspect_dryrun.py
```

Or from repo root:
```bash
python prompting_chunk/inspect_dryrun.py
```

### `server.py` — Optional FastAPI Wrapper
**Purpose:** Expose extraction logic via REST API (optional infrastructure).

```bash
uvicorn prompting_chunk.server:app --host 0.0.0.0 --port 8000 --reload
```

---

## ✨ Key Features

- ✅ **Chunking** — Smart HTML segmentation (~18KB chunks, 1.2KB overlap)
- ✅ **One-shot prompting** — Learn from first page for consistency
- ✅ **JSON mode** — Ollama's `format: "json"` for cleaner output
- ✅ **DOM verification** — Ensure extracted IDs match HTML
- ✅ **Dry-run mode** — Preview prompts without Ollama
- ✅ **Live progress logs** — Chunk-by-chunk status in terminal
- ✅ **Streaming output** — Optional real-time token stream via `--stream`
- ✅ **Thinking output** — Optional model thoughts via `--show-thinking` (local + stream)
- ✅ **Patching** — Optional second pass for missing IDs
- ✅ **Cypher-ready** — Direct Neo4j insertion parameters
- ✅ **Batch processing** — Handle all 47 pages automatically

---

## 📊 Output Structure

Each page generates JSON with:

```json
{
  "meta": { ... },           // Processing info
  "nkg": {
    "page": { ... },
    "elements": [ ... ],     // UI components
    "triggers": [ ... ]      // User interactions
  },
  "verification": { ... },   // Coverage metrics
  "chunk_reports": [ ... ],  // Per-chunk stats
  "cypher_payload": { ... }  // Neo4j insertion params
}
```

---

## 🔗 Workflow

```
1. Dry-run first page (inspect prompts)
   ↓
2. Extract first page (establishes one-shot example)
   ↓
3. Analyze with nkg_verify.py
   ↓
4. Batch process remaining pages (with one-shot for consistency)
   ↓
5. Review batch report
   ↓
6. Insert to Neo4j via cypher_payload
```

---

## 🎯 Next Steps

1. **Read** [`QUICKSTART.md`](QUICKSTART.md) — 5-minute guide
2. **Run** `--dry-run` on a page to inspect prompts
3. **Extract** first page with `gemma4:31b`
4. **Verify** result with `nkg_verify.py show`
5. **Batch** remaining pages

---

## 📝 Notes

- All scripts use `gemma4:31b` by default (recommended for accuracy)
- Scripts require Ollama 0.4+ for JSON mode support (graceful fallback to older versions)
- One-shot prompting significantly improves consistency across pages
- DOM ID verification prevents hallucinated elements

---

**Status: Ready to extract** ✅
