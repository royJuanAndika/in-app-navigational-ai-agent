# HTML → NKG Extraction Toolkit

Complete system for transforming cleaned HTML pages into Navigational Knowledge Graph (NKG) JSON optimized for Neo4j insertion.

Default backend for `chunked_html_to_nkg.py` is `local` (`http://localhost:11434`). Use `--backend remote` only when calling the remote FastAPI proxy.

## 📦 What You Have

### Core Script
- **`prompting_chunk/chunked_html_to_nkg.py`** — Main extraction script
  - Chunks large HTML into ~18KB segments for improved accuracy
  - Uses `gemma4:31b` LLM via Ollama
  - Supports one-shot prompting for consistency
  - Verifies all DOM ids are covered
  - Outputs Cypher-ready JSON
  - **Dry-run mode** for prompt inspection without Ollama

### Utilities
- **`batch_process_nkg.py`** — Batch processor for all 47 pages
  - Automatic one-shot example propagation
  - Progress tracking and summary reports
  - CSV-ready verification stats

- **`nkg_verify.py`** — Analysis & comparison tool
  - Show detailed element/trigger breakdown
  - Compare two NKG outputs
  - Export Cypher statements
  - Selector specificity analysis

### Documentation
- **`QUICKSTART.md`** — 5-minute getting started guide
- **`CHUNKED_EXTRACTION_GUIDE.md`** — Comprehensive usage reference
- **`NKG_SCHEMA.md`** — Complete JSON schema documentation

### Example Outputs
- **`data/nkg_chunked_output/customer_employee.dryrun.json`** — Dry-run example (all prompts visible)

---

## 🚀 Getting Started (3 Steps)

### Step 1: Start Ollama
```bash
ollama serve
# In another terminal, if needed:
ollama pull gemma4:31b
```

### Step 2: Preview Prompts (No Ollama Needed!)

From prompting_chunk/:
```bash
python chunked_html_to_nkg.py --html ../data/cleaned_html/customer_employee.html --out ../data/nkg_chunked_output/customer_employee.dryrun.json --dry-run
```

Or from repo root:
```bash
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/customer_employee.dryrun.json --dry-run
```

**Output:** "DRY-RUN: 32 chunks, 911 DOM ids"
File contains all prompts for inspection

### Step 3: Extract First Page

From prompting_chunk/:
```bash
python chunked_html_to_nkg.py --html ../data/cleaned_html/customer_employee.html --out ../data/nkg_chunked_output/customer_employee.nkg.json --model gemma4:31b --temperature 0.1 --timeout 240 --stream --global-reconcile-pass
```

Or from repo root:
```bash
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/customer_employee.nkg.json --model gemma4:31b --temperature 0.1 --timeout 240 --stream --global-reconcile-pass
```

Local mode with thinking stream (repo root):
```bash
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/customer_employee.nkg.json --model gemma4:31b --timeout 240 --stream --show-thinking --global-reconcile-pass
```

Remote mode (repo root):
```bash
python prompting_chunk/chunked_html_to_nkg.py --backend remote --remote-server-url https://youtube.com --remote-api-token some-secret-token-2026 --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/customer_employee.nkg.json --model deepseek-r1:70b --timeout 240 --global-reconcile-pass
```

Note: `--stream` and `--show-thinking` are local-backend features.

**Output:** Full JSON with NKG, verification, and Cypher payload

### Step 4: Analyze Result

From prompting_chunk/:
```bash
python nkg_verify.py show ../data/nkg_chunked_output/customer_employee.nkg.json
```

Or from repo root:
```bash
python prompting_chunk/nkg_verify.py show data/nkg_chunked_output/customer_employee.nkg.json
```

---

## 🔄 One-Shot Workflow

Extract remaining pages with the first result as a guide:

From prompting_chunk/:
```bash
python chunked_html_to_nkg.py --html ../data/cleaned_html/customer_attendance_leave.html --out ../data/nkg_chunked_output/customer_attendance_leave.nkg.json --one-shot-example ../data/nkg_chunked_output/customer_employee.nkg.json --model gemma4:31b
```

Or from repo root:
```bash
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_attendance_leave.html --out data/nkg_chunked_output/customer_attendance_leave.nkg.json --one-shot-example data/nkg_chunked_output/customer_employee.nkg.json --model gemma4:31b
```

---

## 📊 Output Structure

Each page generates a JSON with:

```json
{
  "meta": { /* processing info: model, runtime, chunks */ },
  "nkg": {
    "page": { "id": "/customer/employee", "title": "...", "desc": "..." },
    "elements": [ /* UI components with ids, types, selectors */ ],
    "triggers": [ /* user interactions & page transitions */ ]
  },
  "verification": {
    "dom_ids_total": 911,
    "dom_ids_in_nkg_total": 875,
    "coverage_percent": 96.05,
    "is_complete": false
  },
  "cypher_payload": { /* ready-to-use Neo4j parameters */ }
}
```

**Key features:**
- Every extracted element id is **verifiable** against HTML DOM ids
- Selectors are **specific enough** for JavaScript targeting
- Descriptions are **Indonesian and action-oriented**
- Cypher is **parameterized** for safe insertion

---

## 🎯 Element ID Verification

### Rule 1: DOM IDs (Verifiable)
```html
<button id="btn_favorite">⭐</button>
```
→ NKG id: `"btn_favorite"` (verbatim from HTML)
→ Can be verified: `grep id="btn_favorite"` ✓

### Rule 2: Generated IDs (Globally Unique)
```html
<div class="modal-add fade">Add Employee</div>
```
On page `/customer/employee` (slug: `employee`):
→ NKG id: `"employee__modal_add"` (prefixed with page slug)
→ Format ensures no collisions across all 47 pages
→ Selector: `.modal-add.fade` (CSS-based verification)

---

## 📈 Chunking Strategy

The system intelligently chunks HTML to balance context and accuracy:

```
Page: customer_employee.html (~491KB)
     ↓
     Chunk 1: [lines 1-334, 17.7KB]
     Chunk 2: [lines 320-680, 18.2KB]  ← overlaps with Chunk 1
     Chunk 3: [lines 670-..., ...]
     ...
     Chunk 32: [tail]
```

**Features:**
- Each chunk ≈18KB HTML
- 1.2KB overlap between chunks (prevents losing edge elements)
- Smart boundary detection (splits at div/section/form tags)
- All DOM ids in chunk are explicitly listed in prompt

---

## ✅ Quality Assurance

### Before Processing

From prompting_chunk/:
```bash
python chunked_html_to_nkg.py --html ../data/cleaned_html/customer_employee.html --out ../test.dryrun.json --dry-run
```

Or from repo root:
```bash
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_employee.html --out test.dryrun.json --dry-run
```

Examine the prompts to verify:
- [ ] Page slug is correct
- [ ] DOM ids are listed
- [ ] HTML chunking makes sense
- [ ] One-shot example (if provided) looks good

### After Processing

From prompting_chunk/:
```bash
python nkg_verify.py show ../data/nkg_chunked_output/customer_employee.nkg.json
```

Or from repo root:
```bash
python prompting_chunk/nkg_verify.py show data/nkg_chunked_output/customer_employee.nkg.json
```

**Expected output shows:**
- Elements by type: 45 buttons, 8 modals, 120 inputs, ...
- ID sources: 875 from DOM, 5 generated
- Triggers: 342 total (298 to page, 44 to element)
- Coverage: 96% (875/911 DOM ids)
- Missing: select2-* (decorative dropdown clones)

### If Coverage < 100%

**Option 1: Run patching pass for second LLM attempt**

From prompting_chunk/:
```bash
python chunked_html_to_nkg.py --html ../data/cleaned_html/customer_employee.html --out ../data/nkg_chunked_output/customer_employee.nkg.json --patch-missing
```

Or from repo root:
```bash
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/customer_employee.nkg.json --patch-missing
```

**Option 2: Manually review missing ids (might be decorative)**

From prompting_chunk/:
```bash
python nkg_verify.py show ../data/nkg_chunked_output/customer_employee.nkg.json | grep "Missing"
```

Or from repo root:
```bash
python prompting_chunk/nkg_verify.py show data/nkg_chunked_output/customer_employee.nkg.json | grep "Missing"
```

**Option 3: Adjust chunk size for better context**

From prompting_chunk/:
```bash
python chunked_html_to_nkg.py --html ../data/cleaned_html/customer_employee.html --out ../data/nkg_chunked_output/customer_employee.nkg.json --chunk-chars 20000 --overlap-chars 2000
```

Or from repo root:
```bash
python prompting_chunk/chunked_html_to_nkg.py --html data/cleaned_html/customer_employee.html --out data/nkg_chunked_output/customer_employee.nkg.json --chunk-chars 20000 --overlap-chars 2000
```

---

## 🔄 Batch Processing All 47 Pages

**Test with first 5 pages:**

From prompting_chunk/:
```bash
python batch_process_nkg.py --input-dir ../data/cleaned_html --output-dir ../data/nkg_chunked_output --limit 5 --model gemma4:31b
```

Or from repo root:
```bash
python prompting_chunk/batch_process_nkg.py --input-dir data/cleaned_html --output-dir data/nkg_chunked_output --limit 5 --model gemma4:31b
```

**Process all 47 pages (production):**

From prompting_chunk/:
```bash
python batch_process_nkg.py --input-dir ../data/cleaned_html --output-dir ../data/nkg_chunked_output --model gemma4:31b
```

Or from repo root:
```bash
python prompting_chunk/batch_process_nkg.py --input-dir data/cleaned_html --output-dir data/nkg_chunked_output --model gemma4:31b
```

**Resume from page 10:**

From prompting_chunk/:
```bash
python batch_process_nkg.py --input-dir ../data/cleaned_html --output-dir ../data/nkg_chunked_output --start 9 --model gemma4:31b
```

**Output:**
```
Processing: customer_employee.html
✓ customer_employee.html             | 875/911 IDs (96.1%) | 32 chunks |  245.2s | ✓
✓ customer_attendance_leave.html     | 923/945 IDs (97.7%) | 28 chunks |  198.5s | ✓
...
═══════════════════════════════════════════════════════════════════════════════════════════════
BATCH PROCESSING SUMMARY
═══════════════════════════════════════════════════════════════════════════════════════════════
Processed: 47/47 pages
Success: 47 pages
  - Avg DOM ID coverage: 96.2%
  - Complete (100% coverage): 11/47
  - Total runtime: 9847.3s (≈2.7 hours)

Detailed report: data/nkg_chunked_output/batch_report_20260411_143022.json
```

---

## 🗄️ Neo4j Insertion

Once all pages are extracted:

```python
import json
from neo4j import GraphDatabase

# Connect to Neo4j
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))

# Process batch result
with driver.session() as session:
    for nkg_file in sorted(Path("data/nkg_chunked_output").glob("*.nkg.json")):
        result = json.load(open(nkg_file))
        cypher_payload = result["cypher_payload"]
        params = cypher_payload["params"]
        templates = cypher_payload["cypher_templates"]
        
        # Insert page + elements
        session.run(templates["upsert_nodes_and_edges"], **params)
        # Insert triggers
        session.run(templates["upsert_triggers"], **params)
        
        print(f"✓ Inserted {nkg_file.name}")

print("✓ All pages inserted to Neo4j")
```

---

## 🆘 Troubleshooting

| Problem | Solution |
|---------|----------|
| `ConnectionRefusedError` | Start Ollama: `ollama serve` |
| `model not found: gemma4:31b` | Run `ollama pull gemma4:31b` |
| `coverage < 90%` | Run `--patch-missing` for second pass |
| `timeout: 240s` not enough | Increase with `--timeout 360` |
| Dry-run hangs | Press Ctrl+C; likely prompt formatting issue |
| Batch processor slow | Use smaller `--limit` to test first |

---

## 📚 Documentation Map

| Document | Purpose |
|----------|---------|
| **QUICKSTART.md** | 5-minute getting started |
| **CHUNKED_EXTRACTION_GUIDE.md** | Detailed feature reference |
| **NKG_SCHEMA.md** | Complete JSON specification |
| **prompting_chunk/chunked_html_to_nkg.py** | Source code with inline docs |

---

## 🎓 Key Concepts

### Chunking
Breaking large HTML into smaller pieces (≈18KB) sent separately to LLM. Improves accuracy by maintaining context within each chunk while allowing the LLM to focus.

### One-Shot Prompting
Using the first extracted page as an example/reference in prompts for subsequent pages. Ensures consistency in extraction style and reduces variance between pages.

### Verification
Proving that every extracted element id can be traced back to the HTML source (either DOM id or CSS selector), ensuring no hallucinated elements.

### Cypher Payload
Pre-formatted Neo4j parameters and queries ready for immediate insertion, eliminating manual query construction.

---

## 🔒 Important: ID Verification

**Every extracted element must be verifiable:**

- **DOM ids**: Can be grepped from HTML → `grep id="btn_favorite"`
- **Generated ids**: Must have CSS selector matching element → `.modal-add.fade`
- **Verification report**: Shows coverage % and missing/mismatched ids

This prevents "hallucinated" elements that don't actually exist in the HTML.

---

## 📊 Metrics to Track

After extraction, review:

1. **Coverage %** — Should be > 90% normally
2. **Missing IDs** — Usually select2 dropdowns or other decorative elements
3. **Runtime** — ~5-10s per chunk typically
4. **Selector mismatches** — Should be 0 (indicates selector error)

---

## 🚀 Recommended Workflow

1. ✅ **Start Ollama** → `ollama serve`
2. ✅ **Dry-run first page** → inspect prompts
3. ✅ **Extract first page** → review quality
4. ✅ **Analyze result** → `nkg_verify.py show`
5. ✅ **Batch process all 47 pages** → with one-shot
6. ✅ **Review batch report** → check for failures
7. ✅ **Insert to Neo4j** → use cypher_payload
8. ✅ **Query graph** → verify structure

---

## 📞 Quick Reference

```bash
# Dry-run (free, no Ollama)
python prompting_chunk/chunked_html_to_nkg.py --html <file> --out <out.json> --dry-run

# Extract one page
python prompting_chunk/chunked_html_to_nkg.py --html <file> --out <out.json> --model gemma4:31b --stream

# Extract one page with model thinking output
python prompting_chunk/chunked_html_to_nkg.py --html <file> --out <out.json> --model gemma4:31b --stream --show-thinking

# Extract with one-shot
python prompting_chunk/chunked_html_to_nkg.py --html <file> --out <out.json> --one-shot-example <example.json> --model gemma4:31b

# Analyze
python nkg_verify.py show <out.json>

# Compare two
python nkg_verify.py compare <file1.json> <file2.json>

# Batch all pages
python batch_process_nkg.py --input-dir data/cleaned_html --output-dir data/nkg_chunked_output

# Export Cypher
python nkg_verify.py export-cypher <out.json> --output <out.cypher>
```

---

## ✅ Checklist for Success

- [ ] Ollama running with `gemma4:31b`
- [ ] Can run dry-run (shows chunks and prompts)
- [ ] First page extracts successfully
- [ ] Coverage > 90% (or use --patch-missing)
- [ ] nkg_verify.py shows element/trigger breakdown
- [ ] Batch processor runs without errors
- [ ] Cypher inserts to Neo4j without issues
- [ ] Neo4j query returns expected nodes/relationships

---

**Next Step:** Read [QUICKSTART.md](QUICKSTART.md) for your first extraction! 🚀
