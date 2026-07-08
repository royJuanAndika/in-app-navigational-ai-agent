# Session B — LLM Phases 1 & 2 + Prompts

> **Prerequisite:** Session A must be complete and verified before starting this session.
> **Your only job this session:** Implement Phase 1, Phase 2, all prompt templates, and the pipeline CLI skeleton.
> Stop after completing all tasks below. Do not implement Phase 3 or Phase 4 yet.

---

## Context Files to Read First (in this order)

1. `llm_based_agent/docs/implementation_plan/09_faq_ingestion_pipeline.md` — full design spec
2. `llm_based_agent/docs/implementation_plan/session_A_data_layer.md` — what Session A built
3. `llm_based_agent/src/nkg_agent/core/llm.py` — how to use `get_llm()` and the embedding API
4. `llm_based_agent/src/nkg_agent/core/config.py` — settings
5. `llm_based_agent/src/nkg_agent/core/graph_db.py` — `find_pages()` function needed in Phase 1
6. `llm_based_agent/faq_pipeline/models.py` — models from Session A
7. `data_preprocessing_and_cleaning/scrape_faq/help_center_faq.json` — sample to understand FAQ structure

---

## Tasks

### Task 1 — Create `faq_pipeline/prompts/__init__.py`
Empty.

### Task 2 — Create `faq_pipeline/prompts/classify.py`
Prompt templates for Phase 1.

The system prompt must instruct the LLM to:
- Classify the FAQ as `procedural` or `informational`
- Generate a `snake_case` `intent_id` from the question
- Identify which `page_ids` from the provided page list the FAQ operates on (match by title/path literally — the FAQ answers name pages explicitly)
- For each resolved `page_id`, write a short `page_notes` entry describing what happens on that page in this FAQ's flow
- Use `category` + `subcategory` as a **hint** if page matching from answer text is ambiguous — the LLM must still resolve to a real `page_id`, not output the category string directly
- If no page can be confidently resolved, output `page_ids: []`
- Output **only valid JSON** matching `Phase1Result` schema

User prompt template must include:
- The FAQ `question`, cleaned `answer`, `category`, `subcategory`, `subsubcategory`
- The full list of pages as: `{page_id} | {title} | {desc}` (one per line)

### Task 3 — Create `faq_pipeline/prompts/step_draft.py`
Prompt templates for Phase 2.

The system prompt must instruct the LLM to:
- Extract **every** navigational step from the FAQ answer — no gaps allowed
- Each step must have its `page_id` (from the `page_ids` + `page_notes` provided)
- Steps must be complete: if the FAQ mentions filling multiple form fields, each field is a separate step
- The `element_hint` should be the visible button label / field label exactly as the FAQ states it
- Output **only valid JSON** matching `Phase2Result` schema

User prompt template must include:
- The cleaned FAQ answer
- `page_notes` from Phase 1 (so the LLM knows which page each part of the FAQ refers to)

### Task 4 — Create `faq_pipeline/phases/__init__.py`
Empty.

### Task 5 — Create `faq_pipeline/phases/phase1_classify.py`

```python
def classify_faq(faq: FAQEntry, all_pages: list[dict]) -> Phase1Result:
    """
    Calls get_llm() with the classify prompt.
    Parses JSON response into Phase1Result.
    Retries up to 2 times on JSON parse failure.
    """
```

- Load all pages using `find_pages("")` or a direct `get_all_pages()` call (add to `graph_db.py` if missing — simple `MATCH (p:Page) RETURN p.id, p.title, p.desc`).
- Use `ChatOllama.invoke()` with structured prompt.
- Parse response content as JSON → validate with `Phase1Result.model_validate()`.

### Task 6 — Create `faq_pipeline/phases/phase2_steps.py`

```python
def extract_steps(faq: FAQEntry, phase1: Phase1Result) -> Phase2Result:
    """
    Only called for procedural FAQs.
    Calls get_llm() with the step_draft prompt.
    Parses JSON response into Phase2Result.
    Retries up to 2 times on JSON parse failure.
    """
```

### Task 7 — Create `faq_pipeline/pipeline.py` (skeleton only)

CLI entry point. Implement the full orchestration loop but **leave Phase 3 and Phase 4 as stubs** (raise `NotImplementedError`).

```python
"""
Usage:
  python -m faq_pipeline.pipeline --mode proxy   # uses OLLAMA_PROXY_URL + token
  python -m faq_pipeline.pipeline --mode local   # uses OLLAMA_BASE_URL, no auth header
  python -m faq_pipeline.pipeline --dry-run      # phases 1+2 only, no Neo4j writes
  python -m faq_pipeline.pipeline --faq-id <id>  # process a single FAQ by faq_id (for testing)
"""
```

The orchestration loop must:
1. Load all FAQs from `help_center_faq.json`
2. Load all pages from Neo4j
3. For each FAQ: run Phase 1 → if procedural, run Phase 2 → stub Phase 3 → stub Phase 4 → stub Phase 5
4. Print progress: `[1/121] tambah_karyawan_1 → procedural, pages: ['/customer/employee']`
5. Save intermediate results to `faq_pipeline/output/phase1_results.json` and `phase1_results + phase2_results.json` after each phase completes all FAQs — this allows Session C to pick up without re-running Phases 1 and 2.

**Local mode:** When `--mode local`, override `ollama_proxy_url` with `OLLAMA_BASE_URL` from env, and skip the `X-API-Token` header. See `llm.py` for how the ChatOllama client is built — you'll need to pass a modified settings or construct a separate ChatOllama for local mode.

---

## Verification

After completing all tasks:
```bash
# From llm_based_agent/
python -m faq_pipeline.pipeline --dry-run --faq-id tambah_karyawan_1
```
Expected output:
```
[1/1] tambah_karyawan_1 → procedural, pages: ['/customer/employee', ...]
Phase 2 steps extracted: 6 steps
Phase 3: NotImplementedError (stub)
Saved: faq_pipeline/output/phase1_results.json
Saved: faq_pipeline/output/phase2_results.json
```
