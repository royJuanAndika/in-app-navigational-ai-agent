# Session A — Data Layer

> **Your only job this session:** Implement the data layer for the FAQ ingestion pipeline.
> Stop after completing all tasks below. Do not touch `phases/` or `prompts/` yet.

---

## Context Files to Read First (in this order)

1. `llm_based_agent/docs/implementation_plan/09_faq_ingestion_pipeline.md` — full design spec
2. `llm_based_agent/src/nkg_agent/core/config.py` — how settings are loaded
3. `llm_based_agent/src/nkg_agent/core/graph_db.py` — read-only query pattern to mirror
4. `llm_based_agent/docs/neo4j_schema.md` — existing NKG schema

---

## Tasks

### Task 1 — Create `faq_pipeline/__init__.py`
Empty file. Marks `faq_pipeline/` as a Python package.

### Task 2 — Create `faq_pipeline/models.py`
Pydantic v2 models for all inter-phase data structures:

- `FAQEntry` — mirrors one JSON object from `help_center_faq.json`
- `Phase1Result` — output of Phase 1 LLM call:
  - `intent_type: Literal["procedural", "informational"]`
  - `intent_id: str`
  - `label: str`
  - `page_ids: list[str]`
  - `page_notes: dict[str, str]` — `{page_id: note about what happens on this page}`
- `StepDraft` — one step from Phase 2:
  - `order: int`
  - `page_id: str`
  - `action: Literal["click", "input", "select", "upload", "navigate", "check"]`
  - `description: str`
  - `element_hint: str`
- `Phase2Result` — `steps: list[StepDraft]`
- `ResolvedStep` — output of Phase 3 per step:
  - `order: int`
  - `nkg_id: str`
  - `action: str`
  - `confidence: Literal["high", "medium", "low"]`
  - `note: str`
- `Phase3Result` — `resolved_steps: list[ResolvedStep]`
- `IntentWrite` — final assembled object ready for Neo4j write:
  - all `Phase1Result` fields
  - `faq_id: str`
  - `category: str`
  - `subcategory: str`
  - `content: str` — cleaned answer text
  - `resolved_steps: list[ResolvedStep]` — empty for informational
  - `possible_questions: list[str]` — populated in Phase 4
  - `embedding: list[float]` — populated in Phase 4

### Task 3 — Create `faq_pipeline/html_cleaner.py`
Single function `clean_html(raw: str) -> str`:
- Strip all HTML tags (use `re` or `html.parser`)
- Remove inline `<img ...>` tags entirely
- Collapse multiple whitespace/newlines to single newlines
- Strip leading/trailing whitespace

### Task 4 — Create `faq_pipeline/review_log.py`
Single function `append_review(log_path: Path, faq_id: str, step: ResolvedStep, reason: str) -> None`:
- Appends one JSON object per line to `review_log.jsonl` (newline-delimited JSON)
- Object shape: `{faq_id, order, nkg_id, action, confidence, note, reason, timestamp_utc}`
- Creates the file if it doesn't exist

### Task 5 — Create `faq_pipeline/graph_db_write.py`
Write-only Neo4j functions. Import `get_driver` from `nkg_agent.core.graph_db`.

Functions needed:

```python
def ensure_schema() -> None:
    """Create Intent unique constraint + vector index if not exists."""

def write_intent(intent: IntentWrite) -> None:
    """
    Atomic transaction per Intent:
    1. MERGE (:Intent {id}) SET all properties (excluding embedding + resolved_steps)
    2. DELETE existing HAS_STEP relationships, then recreate from resolved_steps
    3. DELETE existing ABOUT_PAGE relationships, then recreate from page_ids
    Raises ValueError if any nkg_id in resolved_steps does not resolve to a real Element.
    """

def write_intent_embedding(intent_id: str, embedding: list[float]) -> None:
    """SET i.embedding on an already-written Intent node."""
```

Cypher patterns to use — see Section 5.5 of `09_faq_ingestion_pipeline.md`.

> **Import rule:** `faq_pipeline/` may only import from `nkg_agent.core`. Never from `nkg_agent.agent` or `nkg_agent.tools`.

---

## Verification

After completing all tasks, verify:
- `python -c "from faq_pipeline.models import IntentWrite; print('ok')"` (run from `llm_based_agent/`)
- `python -c "from faq_pipeline.graph_db_write import ensure_schema; ensure_schema(); print('schema ok')"` — confirm constraint + index appear in Neo4j browser under `SHOW CONSTRAINTS` and `SHOW INDEXES`
- `python -c "from faq_pipeline.html_cleaner import clean_html; print(clean_html('<b>Hello</b> <img src=x> World'))"` → should print `Hello World`
