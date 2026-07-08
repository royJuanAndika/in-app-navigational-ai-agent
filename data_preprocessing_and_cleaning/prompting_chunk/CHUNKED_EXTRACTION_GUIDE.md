# Chunked HTML → NKG JSON Extraction Guide

## Overview

This script (`chunked_html_to_nkg.py`) transforms cleaned HTML pages into Navigational Knowledge Graph (NKG) JSON optimized for Cypher graph insertion.

**Key features:**
- **Chunking**: Splits large HTML into ~18KB chunks to improve LLM accuracy
- **One-shot prompting**: Supports learning from prior page extractions
- **DOM ID verification**: Ensures extracted elements cover all DOM ids
- **Cypher-ready output**: Includes parameterized queries for Neo4j insertion
- **Dry-run mode**: Inspect prompts without calling Ollama

---

## Output JSON Structure

### Full Output (Normal Mode)

```json
{
  "meta": {
    "schema_version": "nkg_chunked_v1",
    "source_html": "data/cleaned_html/customer_employee.html",
    "filename": "customer_employee.html",
    "model": "gemma4:31b",
    "ollama_url": "http://localhost:11434",
    "page_url": "/customer/employee",
    "page_title": "Employee Management",
    "chunk_config": {
      "chunk_chars": 18000,
      "overlap_chars": 1200,
      "total_chunks": 32
    },
    "runtime_seconds": 245.67
  },
  
  "nkg": {
    "page": {
      "id": "/customer/employee",
      "title": "Employee Management",
      "desc": "Halaman untuk mengelola data karyawan perusahaan..."
    },
    "elements": [
      {
        "id": "btn_favorite",
        "desc": "Tombol untuk menandai karyawan favorit",
        "type": "button",
        "selector": "#btn_favorite",
        "parent_element_id": null
      },
      {
        "id": "employee__modal_add",
        "desc": "Modal form untuk menambah karyawan baru",
        "type": "modal",
        "selector": ".modal-add.fade"
      }
    ],
    "triggers": [
      {
        "from": "btn_favorite",
        "to": "/customer/employee",
        "to_type": "page"
      },
      {
        "from": "employee__btn_add",
        "to": "employee__modal_add",
        "to_type": "element"
      }
    ]
  },

  "verification": {
    "dom_ids_total": 911,
    "dom_ids_in_nkg_total": 875,
    "coverage_percent": 96.05,
    "missing_dom_ids": ["select2-data-12", "hidden_backup_id"],
    "missing_dom_ids_with_line": [
      {"id": "select2-data-12", "line": 456}
    ],
    "generated_non_dom_ids": ["employee__modal_add", "employee__btn_add"],
    "selector_mismatches": [],
    "is_complete": false
  },

  "chunk_reports": [
    {
      "chunk_index": 1,
      "line_range": [1, 334],
      "char_count": 17706,
      "dom_ids_in_chunk": 29,
      "new_ids_added": 24,
      "missing_dom_ids_after_chunk": [],
      "patch_added": 0,
      "patch_error": null
    }
  ],

  "cypher_payload": {
    "params": {
      "page": {
        "id": "/customer/employee",
        "title": "Employee Management",
        "desc": "..."
      },
      "elements": [...],
      "contains": [
        {"page_id": "/customer/employee", "element_id": "btn_favorite"}
      ],
      "element_contains": [
        {"parent_id": "employee__modal_add", "child_id": "employee__input_nama"}
      ],
      "triggers": [...]
    },
    "cypher_templates": {
      "upsert_nodes_and_edges": "MERGE (p:Page {id: $page.id}) ...",
      "upsert_element_contains": "UNWIND $element_contains AS c ...",
      "upsert_triggers": "UNWIND $triggers AS t ..."
    }
  }
}
```

### Key Fields Explained

**`nkg.elements[].id` generation rules:**
- **DOM id exists**: Use verbatim as NKG id. Selector: `#<id>`
- **No DOM id**: Generate `<page_slug>__<description>`. Selector: CSS selector

**`nkg.elements[].type`**: button, input, select, textarea, modal, table, link, tab, section

**`nkg.elements[].parent_element_id` (optional):**
- `null` / tidak ada: elemen top-level di halaman
- berisi id element parent: elemen nested (mis. field di dalam modal/form)

**`nkg.triggers[].to_type`**: 
- `"page"`: Navigation to another URL
- `"element"`: Reveal/show interaction on same page

**`verification.is_complete`**: `true` only when all DOM ids are covered

---

## Usage Examples

### 1. Dry-run: Inspect prompts (no Ollama needed)

From prompting_chunk/:
```bash
python chunked_html_to_nkg.py \
  --html ../data/cleaned_html/customer_employee.html \
  --out ../data/nkg_chunked_output/customer_employee.dryrun.json \
  --dry-run
```

Or from repo root:
```bash
python prompting_chunk/chunked_html_to_nkg.py \
  --html data/cleaned_html/customer_employee.html \
  --out data/nkg_chunked_output/customer_employee.dryrun.json \
  --dry-run
```

**Output includes:**
- Chunk structure (number of chunks, DOM id count)
- Full prompts sent to LLM (for validation)
- DOM id list

---

### 2. Extract single page (requires Ollama running)

Ensure Ollama is running: `ollama serve`

From prompting_chunk/:
```bash
python chunked_html_to_nkg.py \
  --html ../data/cleaned_html/customer_employee.html \
  --out ../data/nkg_chunked_output/customer_employee.nkg.json \
  --model gemma4:31b \
  --temperature 0.1 \
  --num-predict 4096 \
  --timeout 240
```

Or from repo root:
```bash
python prompting_chunk/chunked_html_to_nkg.py \
  --html data/cleaned_html/customer_employee.html \
  --out data/nkg_chunked_output/customer_employee.nkg.json \
  --model gemma4:31b \
  --temperature 0.1 \
  --num-predict 4096 \
  --timeout 240
```

**Output:** Full JSON with NKG, verification, and Cypher payload.

---

### 3. One-shot prompting: Use first result to guide next page

From prompting_chunk/:
```bash
# First page: establishes the extraction style
python chunked_html_to_nkg.py \
  --html ../data/cleaned_html/customer_employee.html \
  --out ../data/nkg_chunked_output/customer_employee.nkg.json \
  --model gemma4:31b

# Second page: use first result as example
python chunked_html_to_nkg.py \
  --html ../data/cleaned_html/customer_attendance_leave.html \
  --out ../data/nkg_chunked_output/customer_attendance_leave.nkg.json \
  --one-shot-example ../data/nkg_chunked_output/customer_employee.nkg.json \
  --model gemma4:31b
```

Or from repo root:
```bash
# First page: establishes the extraction style
python prompting_chunk/chunked_html_to_nkg.py \
  --html data/cleaned_html/customer_employee.html \
  --out data/nkg_chunked_output/customer_employee.nkg.json \
  --model gemma4:31b

# Second page: use first result as example
python prompting_chunk/chunked_html_to_nkg.py \
  --html data/cleaned_html/customer_attendance_leave.html \
  --out data/nkg_chunked_output/customer_attendance_leave.nkg.json \
  --one-shot-example data/nkg_chunked_output/customer_employee.nkg.json \
  --model gemma4:31b
```

---

### 4. Patch missing DOM ids after extraction

From prompting_chunk/:
```bash
python chunked_html_to_nkg.py \
  --html ../data/cleaned_html/customer_employee.html \
  --out ../data/nkg_chunked_output/customer_employee.nkg.json \
  --patch-missing \
  --model gemma4:31b
```

Or from repo root:
```bash
python prompting_chunk/chunked_html_to_nkg.py \
  --html data/cleaned_html/customer_employee.html \
  --out data/nkg_chunked_output/customer_employee.nkg.json \
  --patch-missing \
  --model gemma4:31b
```

This adds a second LLM pass to cover any remaining DOM ids.

---

## Chunking Strategy

The script splits HTML at logical boundaries (div, section, form tags) to maintain context:

- **Target chunk size**: 18,000 chars (~5-10KB HTML + context)
- **Overlap**: 1,200 chars between chunks (prevents losing edge elements)
- **Boundary detection**: Looks for HTML tag boundaries for clean cuts

Example from dry-run:
```
Chunk 1: lines 1-334   (17,706 chars, 29 DOM ids)
Chunk 2: lines 320-680 (18,155 chars, 32 DOM ids)  ← overlap: lines 320-334
Chunk 3: lines 670-... (...)
...
Chunk 32: (tail)
```

---

## Prompt Structure per Chunk

Each chunk prompt includes:

```
[Optional: ONE-SHOT EXAMPLE if --one-shot-example provided]

Task: Extract NKG from this HTML chunk.

PAGE_URL: /customer/employee
PAGE_TITLE: Employee Management  
PAGE_SLUG: employee
CHUNK_INDEX: 1/32
CHUNK_LINES: 1-334
DOM_IDS_IN_THIS_CHUNK: ["abc1_filter", "btn_favorite", ...]
KNOWN_ELEMENT_IDS_FROM_PREVIOUS_CHUNKS: []

IMPORTANT: untuk id yang ada di DOM_IDS_IN_THIS_CHUNK, usahakan semua ter-cover...
IMPORTANT: jangan duplikasi id yang sudah ada di KNOWN_ELEMENT_IDS_FROM_PREVIOUS...

HTML_CHUNK:
[actual HTML]
```

This ensures:
- LLM covers all DOM ids in each chunk
- No duplicate elements across chunks
- Clear context about overall structure

---

## ID Generation Rules (Critical for Verification)

### Rule 1: Elements with DOM id
```html
<button id="btn_favorite">★</button>
```
→ NKG element ID: `"btn_favorite"` (verbatim)
→ Selector: `"#btn_favorite"`

### Rule 2: Generated IDs for elements without DOM id
```html
<modal class="modal-add fade" onclick="...">
```
On page `/customer/employee` (slug: `employee`):
→ NKG element ID: `"employee__modal_add"` 
→ Selector: `.modal-add.fade` or similar

### Rule 3: Selector Priority
1. If element has id → `#<id>`
2. If element has onclick → `[onclick*="function_name"]`
3. Otherwise → Combined tag + class selector

---

## Verification Report

After extraction, inspect `verification`:

```json
{
  "dom_ids_total": 911,
  "dom_ids_in_nkg_total": 875,
  "coverage_percent": 96.05,
  "missing_dom_ids": ["select2-data-12"],
  "is_complete": false
}
```

**If `is_complete: false`**, either:
1. Run with `--patch-missing` to add second LLM pass
2. Manually add missing items to the JSON
3. It's okay if some DOM ids are decorative (not all need extraction)

---

## Cypher Insertion

The output includes ready-to-use Cypher parameters and templates:

```python
# Example: using in Neo4j
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=(...))

with driver.session() as session:
    result = json.load(open("customer_employee.nkg.json"))
    cypher = result["cypher_payload"]
    params = cypher["params"]
    
    # Insert nodes and relationships
    session.run(cypher["cypher_templates"]["upsert_nodes_and_edges"], **params)
    # Insert triggers
    session.run(cypher["cypher_templates"]["upsert_triggers"], **params)
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ConnectionRefusedError` | Start Ollama: `ollama serve` |
| Missing DOM ids in coverage | Run `--patch-missing` for second pass, or manually inspect missed ids in verification report |
| Timeout errors | Increase `--timeout` (in seconds) |
| Duplicate elements | Verify `KNOWN_ELEMENT_IDS_FROM_PREVIOUS_CHUNKS` in prompts |

---

## Performance Notes

- **model**: Recommended `gemma4:31b` for accuracy (tested); can use smaller models (`qwen3:32b`) for speed
- **temperature**: `0.1` (low) for consistency; higher values add variation
- **num_predict**: `4096` tokens is enough for typical chunk output
- **timeout**: 240-360 seconds per chunk (depends on model size)

### JSON Mode (Ollama 0.4+)

The script **automatically enables JSON mode** for compatible models via Ollama's `format: "json"` option.

**Benefits:**
- ✅ **Cleaner output** — Model outputs ONLY valid JSON (no markdown fences, thinking blocks)
- ✅ **Faster extraction** — Direct JSON parse, no regex needed
- ✅ **Better reliability** — Fewer failed/malformed responses
- ✅ **Faster inference** — Model knows output must be valid JSON

**Fallback:** If Ollama doesn't support JSON mode or format fails, the script automatically falls back to text parsing with thinking block removal. Always works, even on older Ollama versions.

---

## Next Steps

1. **Start Ollama**: `ollama serve` (if not already running)
2. **Inspect first page prompts**: `--dry-run` mode
3. **Extract first page**: Use result JSON as one-shot example
4. **Batch other pages**: With one-shot example for consistency
5. **Verify coverage**: Check `verification.is_complete`
6. **Insert to Neo4j**: Use `cypher_payload`
