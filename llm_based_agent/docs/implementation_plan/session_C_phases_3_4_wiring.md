# Session C — Phase 3, Phase 4, and End-to-End Wiring

> **Prerequisite:** Sessions A and B must be complete and verified before starting this session.
> **Your job this session:** Implement Phase 3 (element matching), Phase 4 (paraphrases + embeddings), and wire everything into a complete working pipeline.

---

## Context Files to Read First (in this order)

1. `llm_based_agent/docs/implementation_plan/09_faq_ingestion_pipeline.md` — full design spec. **Read Section 5.3 very carefully** — Phase 3 has specific requirements around completeness, sequential page processing, and element list rendering.
2. `llm_based_agent/docs/implementation_plan/session_A_data_layer.md`
3. `llm_based_agent/docs/implementation_plan/session_B_phases_1_2.md`
4. `llm_based_agent/src/nkg_agent/core/graph_db.py` — You will need to create a new `get_page_elements_with_hierarchy()` function here for Phase 3.
5. `llm_based_agent/src/nkg_agent/core/llm.py` — `get_llm()` and embedding API call pattern
6. `llm_based_agent/faq_pipeline/models.py` — all Pydantic models
7. `llm_based_agent/faq_pipeline/output/phase2_results.json` — real Phase 2 output to test against

---

## Tasks

### Task 1 — Create `faq_pipeline/prompts/element_match.py`

The system prompt must instruct the LLM to:
- Read the provided page element list carefully
- Match each step draft to the single best `nkg_id` from the list
- **CRITICAL**: The LLM must "fix" incomplete FAQs. If the FAQ says to fill a field, but that field is inside a tab or a modal, the LLM must **insert intermediate steps** (like `click` on the tab/modal trigger) before the field's step.
- To do this, the LLM must rely on the `parent_id` and `triggers` information provided in the element list rendering.
- Assign `confidence: "high"` only when the `element_hint` directly matches an element's `text` field. Use `"medium"` for description matches. Use `"low"` when uncertain.
- Output **only valid JSON** matching `Phase3Result` schema

User prompt template must include:
- The rendered page element list (see rendering format below)
- The step drafts assigned to this page (from `Phase2Result`)
- Accumulated resolved steps from previous pages (for context on step ordering)

**Element list rendering format** (implement as `render_page_elements(elements: list[dict]) -> str`):

You must write a new query `get_page_elements_with_hierarchy(page_id)` in `graph_db.py` because the existing `get_page_elements` lacks `parent_element_id` and `[:TRIGGERS]` relations, making it impossible for the LLM to know which inputs belong to which tabs/modals.

The new query should return `nkg_id`, `type`, `text`, `desc`, `selector`, `parent_nkg_id` (from incoming `[:CONTAINS]`), and `triggers_nkg_id` (from outgoing `[:TRIGGERS]`).

Render the list hierarchically or explicitly mention parents:
```
Page: {page_id} — {title}
Total elements: {count}

[tab]     {id:<30} (Triggers: {triggers_nkg_id}) "{text}" — {desc}
[modal]   {id:<30} (Parent: {parent_nkg_id}) "{text}" — {desc}
[button]  {id:<30} (Parent: {parent_nkg_id}) "{text}" — {desc}
[input]   {id:<30} (Parent: {parent_nkg_id}) "{text}" — {desc}
```

Sort order within the rendered list: group elements by their `parent_nkg_id` or logical container, so the LLM clearly sees which inputs are grouped under which tab or modal.

### Task 2 — Create `faq_pipeline/phases/phase3_match.py`

```python
def match_elements(
    faq: FAQEntry,
    phase1: Phase1Result,
    phase2: Phase2Result,
) -> Phase3Result:
    """
    For each page_id in phase1.page_ids (in order):
      1. Fetch elements: get_page_elements_with_hierarchy(page_id) from graph_db
      2. Render element list as structured text
      3. Filter phase2.steps to only those assigned to this page_id
      4. Call LLM with rendered elements + filtered steps + accumulated_steps (context)
      5. Parse Phase3Result, accumulate resolved_steps
      6. For any step with confidence != "high": call append_review()
    Return combined Phase3Result with all steps from all pages, order preserved.
    """
```

The function processes pages **one at a time**, in the order they appear in `phase1.page_ids`. Steps from earlier pages are passed as `accumulated_steps` context to later pages — this preserves sequence awareness without feeding two pages' element lists simultaneously.

### Task 3 — Create `faq_pipeline/prompts/paraphrase.py`
Prompt for Phase 4 paraphrase generation.

System prompt: generate 4–6 question paraphrases in Bahasa Indonesia for the given intent. Cover formal and informal registers. Output JSON: `{"possible_questions": [...]}`.

User prompt template includes: `label`, `type`, `category`, `subcategory`, `content` (first 300 chars of cleaned answer).

### Task 4 — Create `faq_pipeline/phases/phase4_embed.py`

```python
def generate_questions_and_embed(intent: IntentWrite) -> IntentWrite:
    """
    1. Call LLM to generate possible_questions → update intent.possible_questions
    2. Build embedding document string (see format in Section 5.4 of the main plan)
    3. POST to /api/embeddings with qwen3-embedding:8b
    4. Update intent.embedding
    5. Return updated intent
    """
```

Embedding document format:
```
Instruct: Represent a user's navigation intent or knowledge query in a HR SaaS platform
so that it can be retrieved when a user asks a related question.
Document: Intent: {label}
Kategori: {category} > {subcategory}
Tipe: {type}
Pertanyaan: {possible_questions joined by " | "}
Konten: {content[:200] or step summary}
```

For `--mode local`: use `OLLAMA_BASE_URL` for the embedding POST, skip auth header.

### Task 5 — Wire Phase 3, Phase 4, Phase 5 into `faq_pipeline/pipeline.py`

Replace the `NotImplementedError` stubs in `pipeline.py` with real calls:
- Phase 3: `match_elements(faq, phase1, phase2)` → `Phase3Result`
- Phase 4: `generate_questions_and_embed(intent)` → updated `IntentWrite`
- Phase 5: `write_intent(intent)` + `write_intent_embedding(intent.id, intent.embedding)`

Add `faq_pipeline/output/phase3_results.json` and `final_intents.json` intermediate saves.

Handle errors gracefully: if any phase fails for one FAQ, log the error and continue to the next FAQ. Never crash the whole pipeline on a single FAQ failure.

### Task 6 — Create `faq_pipeline/phases/phase5_write.py`
Thin wrapper that calls `graph_db_write.write_intent()` and `graph_db_write.write_intent_embedding()` with appropriate logging. No logic here — logic lives in `graph_db_write.py`.

---

## Verification

Full end-to-end test on a single procedural FAQ:
```bash
python -m faq_pipeline.pipeline --faq-id tambah_karyawan_1 --mode proxy
```

Expected:
1. Console shows all 5 phases completing with step counts
2. `faq_pipeline/output/final_intents.json` contains the `IntentWrite` object with `resolved_steps`, `possible_questions`, and `embedding` (non-empty list)
3. In Neo4j browser: `MATCH (i:Intent {id: 'tambah_karyawan_per_karyawan'})-[r:HAS_STEP]->(e:Element) RETURN i,r,e ORDER BY r.order` — returns ordered steps pointing to real Element nodes
4. `MATCH (i:Intent)-[:ABOUT_PAGE]->(p:Page) RETURN i.id, p.id` — shows the page link

Then run on informational FAQ:
```bash
python -m faq_pipeline.pipeline --faq-id pengaturan_umum_1 --mode proxy
```
Expected: Intent node created, no HAS_STEP relationships, ABOUT_PAGE present.

Once single-FAQ tests pass, run full pipeline:
```bash
python -m faq_pipeline.pipeline --mode proxy
```
