# Quick-Start Guide: HTML → NKG Extraction

## 🎯 Goal
Transform cleaned HTML pages into Navigational Knowledge Graph (NKG) JSON that maps UI elements, interactions, and page transitions for graph insertion.

---

## 📋 Prerequisites

- **Ollama running** with `gemma4:31b` model available (0.4+ recommended for JSON mode)
  ```bash
  ollama serve
  # In another terminal:
  ollama pull gemma4:31b
  ```
- **Python 3.10+** with `httpx` installed (should already work)
- **Cleaned HTML files** in `data/cleaned_html/` (you have these)

Default backend for `chunked_html_to_nkg.py` is `local` (`http://localhost:11434`). Use `--backend remote` only when calling the remote FastAPI proxy.

---

## 🚀 Quick Start (5 minutes)

### Step 1: Inspect Prompts (No Ollama Needed)

See what the LLM will receive without actually calling it:

```bash
# Run from prompting_chunk/ directory:
cd prompting_chunk/

python chunked_html_to_nkg.py --html ../data/cleaned_html/customer_employee.html --out ../data/nkg_chunked_output/customer_employee.dryrun.json --dry-run
```

**Or from repo root:**
```bash
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/customer_employee.dryrun.json --dry-run
```

**Output:**
```
DRY-RUN: 32 chunks, 911 DOM ids
First chunk prompt chars: 18848
```

File saved: `../data/nkg_chunked_output/customer_employee.dryrun.json`

Inside this file, you can see all 32 prompts that will be sent to gemma4:31b. ✓

---

### Step 2: Extract First Page (Establishes Style)

Once Ollama is running:

```bash
# From prompting_chunk/:
python chunked_html_to_nkg.py --html ../data/cleaned_html/customer_employee.html --out ../data/nkg_chunked_output/customer_employee.nkg.json --model gemma4:31b --temperature 0.1 --timeout 240 --stream
```

**Or from repo root:**
```bash
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/customer_employee.nkg.json --model gemma4:31b --temperature 0.1 --timeout 240 --stream
```

**Local mode with thinking stream (repo root):**
```bash
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/customer_employee.nkg.json --model gemma4:31b --timeout 240 --stream --show-thinking
```

**Remote mode (repo root):**
```bash
python prompting_chunk/chunked_html_to_nkg.py --backend remote --remote-server-url https://youtube.com --remote-api-token some-secret-token --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/customer_employee.nkg.json --model deepseek-r1:70b --timeout 240
```

Note: `--stream` and `--show-thinking` are local-backend features.

**Output:**
```
Saved: data/nkg_chunked_output/customer_employee.nkg.json
DOM ID coverage: 875/911 (96.05%)
```

File contains:
- `nkg` → Elements, triggers, page structure
- `verification` → Coverage stats + missing IDs
- `cypher_payload` → Ready for Neo4j insertion
- `chunk_reports` → Status per chunk

---

### Step 3: Analyze Result

```bash
# From prompting_chunk/:
python nkg_verify.py show ../data/nkg_chunked_output/customer_employee.nkg.json
```

**Or from repo root:**
```bash
python prompting_chunk/nkg_verify.py show data/nkg_chunked_output/customer_employee.nkg.json
```

**Shows:**
- Breakdown by element type (button, modal, input, etc.)
- Element ID sources (DOM vs generated)
- Trigger analysis
- Selector specificity
- Missing DOM IDs with line numbers

---

### Step 4: Extract Next Pages (With One-Shot Prompting)

Use the first result as a guide for improved consistency:

```bash
# From prompting_chunk/:
python chunked_html_to_nkg.py --html ../data/cleaned_html/customer_attendance_leave.html --out ../data/nkg_chunked_output/customer_attendance_leave.nkg.json --one-shot-example ../data/nkg_chunked_output/customer_employee.nkg.json --model gemma4:31b --temperature 0.1 --timeout 240
```

**Or from repo root:**
```bash
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_attendance_leave.html --out data/nkg_chunked_output/customer_attendance_leave.nkg.json --one-shot-example data/nkg_chunked_output/customer_employee.nkg.json --model gemma4:31b --temperature 0.1 --timeout 240
```

The LLM now sees the first page's extraction style as an example. ✓

---

### Step 5: Batch Process All Pages

Process multiple pages with one-shot prompting:

```bash
# From prompting_chunk/:
python batch_process_nkg.py --input-dir ../data/cleaned_html --output-dir ../data/nkg_chunked_output --model gemma4:31b --limit 5
```

**Or from repo root:**
```bash
python prompting_chunk/batch_process_nkg.py --input-dir data/cleaned_html --output-dir data/nkg_chunked_output --model gemma4:31b --limit 5
```

**Shows progress:**
```
Processing: customer_employee.html
✓ customer_employee.html             | 875/911 IDs (96.1%) | 32 chunks |  245.2s | ✓
✓ customer_attendance_leave.html     | 923/945 IDs (97.7%) | 28 chunks |  198.5s | ✓
...
```

**Generates:** `data/nkg_chunked_output/batch_report_20260411_143022.json`

---

## 📊 Output Structure

Each page generates a JSON with:

```json
{
  "meta": {
    "page_url": "/customer/employee",
    "page_title": "Employee Management",
    "total_chunks": 32,
    "runtime_seconds": 245.2
  },
  
  "nkg": {
    "page": { "id": "...", "title": "...", "desc": "..." },
    "elements": [
      {
        "id": "btn_favorite",          // DOM id or generated <slug>__<desc>
        "type": "button",              // button|input|modal|table|link|...
        "selector": "#btn_favorite",   // CSS selector for JS targeting
        "desc": "Tandai karyawan favorit"  // Indonesian, action-oriented
      }
    ],
    "triggers": [
      {
        "from": "btn_favorite",
        "to": "/customer/employee",    // Page URL or element id
        "to_type": "page|element"
      }
    ]
  },
  
  "verification": {
    "dom_ids_total": 911,
    "dom_ids_in_nkg_total": 875,
    "coverage_percent": 96.05,
    "missing_dom_ids": ["select2-data-12"],      // IDs not extracted (check if decorative)
    "is_complete": false
  },
  
  "cypher_payload": {
    "params": { ... },                // Ready for Neo4j
    "cypher_templates": { ... }       // MERGE/UNWIND statements
  }
}
```

---

## 🔧 Common Commands

| Goal | Command |
|------|---------|
| **Dry-run inspect** (verify prompts) | `python prompting_chunk/chunked_html_to_nkg.py --html ... --out ... --dry-run` |
| **Extract one page (live progress)** | `python prompting_chunk/chunked_html_to_nkg.py --html ... --out ... --model gemma4:31b --stream` |
| **Extract with thinking output** | `python prompting_chunk/chunked_html_to_nkg.py --html ... --out ... --model gemma4:31b --stream --show-thinking` |
| **Extract with one-shot** | Add `--one-shot-example data/nkg_chunked_output/first_page.nkg.json` |
| **Show summary** | `python nkg_verify.py show data/nkg_chunked_output/page.nkg.json` |
| **Compare two results** | `python nkg_verify.py compare page1.nkg.json page2.nkg.json` |
| **Export Cypher** | `python nkg_verify.py export-cypher page.nkg.json --output page.cypher` |
| **Batch all 47 pages** | `python batch_process_nkg.py --input-dir data/cleaned_html --output-dir data/nkg_chunked_output` |

---

## ⚠️ If DOM Coverage is < 100%

Some DOM IDs might be missing. Options:

**1. Automatic patch (recommended first try):**
```bash
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/customer_employee.nkg.json --patch-missing
```
This runs a second LLM pass to specifically cover missing IDs.

**2. Manual inspection:**
```bash
python nkg_verify.py show data/nkg_chunked_output/customer_employee.nkg.json
```
Look for missing IDs with line numbers. They might be decorative (select2 dropdowns, etc.).

**3. Adjust chunking:**
If many IDs are missed in the same area, a smaller chunk might miss context:
```bash
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/customer_employee.nkg.json --chunk-chars 20000 --overlap-chars 2000
```

---

## 🔐 ID Generation Rules (Critical for Verification)

The script ensures every extracted ID can be verified:

### Rule 1: Elements with DOM `id` attribute
```html
<button id="btn_favorite">⭐</button>
```
→ NKG id: `"btn_favorite"` (verbatim)
→ Selector: `"#btn_favorite"` (exact match)

### Rule 2: Elements without DOM `id`
```html
<div class="modal-add fade" onclick="...">
```
→ NKG id: `"employee__modal_add"` (slug_prefix + descriptor)
→ Selector: `.modal-add.fade` (CSS class selector)

### Rule 3: Selector Priority
1. If element has DOM id → use `#id`
2. If element has unique onclick → use `[onclick*="func_name"]`
3. Otherwise → combine tag + classes + attributes

---

## 📈 Performance Tips

| Setting | Impact | Value |
|---------|--------|-------|
| `--chunk-chars` | Larger = fewer chunks, risk less accuracy | 18000 (default) |
| `--overlap-chars` | Larger = prevents lost boundary elements | 1200 (default) |
| `--temperature` | Lower = more consistent, higher = more variation | 0.1 (recommended) |
| `--num-predict` | Max tokens per response | 4096 (fine) |
| `--timeout` | Max seconds per chunk call | 240+ for gemma4:31b |

---

## 🔗 Neo4j Insertion

Once you have NKG JSON files:

```python
import json
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=(...))

with driver.session() as session:
    result_data = json.load(open("customer_employee.nkg.json"))
    cypher_payload = result_data["cypher_payload"]
    params = cypher_payload["params"]
    templates = cypher_payload["cypher_templates"]
    
    # Insert page + elements + relationships
    session.run(templates["upsert_nodes_and_edges"], **params)
    # Insert triggers
    session.run(templates["upsert_triggers"], **params)
```

---

## 📚 Detailed Docs

- **Comprehensive guide:** [`CHUNKED_EXTRACTION_GUIDE.md`](CHUNKED_EXTRACTION_GUIDE.md)
- **Script usage:** `python prompting_chunk/chunked_html_to_nkg.py --help`
- **Batch processor:** `python batch_process_nkg.py --help`
- **Verification tool:** `python nkg_verify.py --help`

---

## 🎓 Workflow Summary

```
1. Dry-run first page (preview prompts without Ollama)
   ↓
2. Extract first page with Ollama (establishes one-shot example)
   ↓
3. Analyze result with nkg_verify.py
   ↓
4. Extract remaining 46 pages with --one-shot-example for consistency
   ↓
5. Batch process or insert to Neo4j via Cypher payload
```

---

## ✅ Checklist

- [ ] Ollama running with `gemma4:31b`
- [ ] Dry-run works (no Ollama needed)
- [ ] First page extraction successful
- [ ] Coverage report shows > 90% (or use --patch-missing)
- [ ] nkg_verify.py shows reasonable element/trigger breakdown
- [ ] Batch process All 47 pages
- [ ] Review batch report for any failures
- [ ] Export Cypher and insert to Neo4j

---

**Next:** Start with `--dry-run` to preview prompts! 🚀
