# 09 — FAQ Ingestion Pipeline: Intent Node Generation

> **Status:** Design complete — ready for implementation
> **Scope:** This document covers the offline pipeline only. Runtime agent tool integration (`get_workflow_by_intent`) is a **separate subsequent task** — implement the pipeline and verify NKG writes before touching the runtime agent.

---

## 0. Before You Start — Read These

To understand the codebase before implementing:

| What to read | Why |
|:---|:---|
| `docs/neo4j_schema.md` | Live Neo4j schema: existing node labels, properties, indexes, Cypher patterns |
| `docs/implementation_plan/03_project_structure.md` | Package layout, import rules, dependency direction |
| `docs/implementation_plan/05_agent_tools.md` | How existing tools wrap `graph_db.py` queries |
| `src/nkg_agent/core/config.py` | Settings loaded from `.env` — LLM model, embedding model, Neo4j creds |
| `src/nkg_agent/core/llm.py` | How to get a `ChatOllama` instance and call the embedding API |
| `src/nkg_agent/core/graph_db.py` | All read-only Cypher helpers (reuse `get_page_elements`, `find_pages`) |
| `data_preprocessing_and_cleaning/scrape_faq/help_center_faq.json` | The 121 FAQ entries to process |

---

## 1. Purpose & Motivation

The FAQ ingestion pipeline is an **offline, one-shot data preparation step**. Without it, the runtime agent has no pre-computed workflow knowledge — it is forced to call `get_page_content` repeatedly at runtime to reconstruct navigation paths from scratch for every user query. This is slow and non-deterministic.

The pipeline encodes FAQ knowledge into the NKG as `Intent` nodes + `HAS_STEP` relationships, so the runtime agent can answer "how do I do X?" with a single `get_workflow_by_intent` lookup instead of a multi-step reasoning chain.

**Correctness over speed.** A wrong `HAS_STEP` edge (pointing to the wrong element) causes the agent to highlight the wrong UI element at runtime. That is a silent, hard-to-detect failure. Thoroughness and accuracy of the extracted steps are the primary success criteria.

---

## 2. Input Data: FAQ Structure

**File:** `data_preprocessing_and_cleaning/scrape_faq/help_center_faq.json`

Each FAQ entry has:
```json
{
  "faq_id": "tambah_karyawan_1",
  "question": "Menambahkan Karyawan per-Karyawan",
  "answer": "...HTML string with numbered steps...",
  "category": "karyawan",
  "subcategory": "daftar_karyawan",
  "subsubcategory": "menambahkan_karyawan_baru",
  "source": "inline_js"
}
```

### Using `category` / `subcategory` / `subsubcategory`

These are **first-class signals**, not metadata to ignore. They serve two purposes:

1. **Page resolution assist (Phase 1):** The category hierarchy often directly maps to a menu path. `category: "karyawan"`, `subcategory: "daftar_karyawan"` → very likely `/customer/employee`. Feed this to the Phase 1 LLM alongside the answer text to give it a stronger prior.

2. **`possible_questions` generation (Phase 4):** The category path reveals domain context. Generating paraphrases for `"Menambahkan Karyawan per-Karyawan"` under `karyawan > daftar_karyawan > menambahkan_karyawan_baru` will be richer than generating blindly from the label alone.

3. **`ABOUT_PAGE` ambiguity resolution:** For informational FAQs that don't name a page explicitly, the subcategory is the best proxy for page resolution.

---

## 3. NKG Schema Extensions

### 3.1 New Node: `:Intent`

```cypher
(:Intent {
  id:                 STRING,    -- snake_case key e.g. "tambah_karyawan_per_karyawan"
  label:              STRING,    -- Human-readable e.g. "Menambahkan Karyawan per-Karyawan"
  type:               STRING,    -- "procedural" | "informational"
  faq_id:             STRING,    -- Source traceability e.g. "tambah_karyawan_1"
  category:           STRING,    -- From FAQ: e.g. "karyawan"
  subcategory:        STRING,    -- From FAQ: e.g. "daftar_karyawan"
  possible_questions: STRING[],  -- Paraphrase variations for semantic matching
  content:            STRING,    -- Cleaned answer text (informational intents)
  embedding:          FLOAT[]    -- 1024-d Qwen3 vector
})
```

### 3.2 New Relationship: `[:HAS_STEP]`

```cypher
(:Intent)-[:HAS_STEP {order: INT, action: STRING}]->(:Element)
```

- `order`: 1-indexed. Every step must be present — no gaps allowed (see Section 5.3).
- `action`: `"click"` | `"input"` | `"select"` | `"upload"` | `"navigate"` | `"check"`

### 3.3 New Relationship: `[:ABOUT_PAGE]`

```cypher
(:Intent)-[:ABOUT_PAGE]->(:Page)
```

All intents (both types) link to their page(s). Enables a future `get_intents_by_page` runtime tool.

### 3.4 Indexes to Create Before Writes

```cypher
CREATE CONSTRAINT intent_id IF NOT EXISTS
    FOR (i:Intent) REQUIRE i.id IS UNIQUE;

CREATE VECTOR INDEX intent_embedding_idx IF NOT EXISTS
    FOR (i:Intent) ON (i.embedding)
    OPTIONS { indexConfig: {
        `vector.dimensions`: 1024,
        `vector.similarity_function`: 'cosine'
    }};
```

---

## 4. FAQ Taxonomy

| Type | Criteria | NKG Output |
|:---|:---|:---|
| `procedural` | Contains numbered steps with explicit UI actions ("Tekan tombol X", "Isi form Y") | `:Intent` + `[:HAS_STEP]` + `[:ABOUT_PAGE]` |
| `informational` | Describes a feature or rule — no step-by-step UI navigation | `:Intent` + `[:ABOUT_PAGE]` only |

---

## 5. Pipeline Phases

```
help_center_faq.json
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  Phase 1: Classify + Page Resolution                │
│  (batch, one LLM call per FAQ)                      │
│  Uses: category/subcategory + answer text           │
└──────────┬──────────────────────────────────────────┘
           │
           ├─── informational ──────────────────────────►┐
           │                                             │
           ▼                                             │
┌──────────────────────────────────────────────────┐    │
│  Phase 2: Step Draft Extraction                  │    │
│  (batch, one LLM call per procedural FAQ)        │    │
└──────────┬───────────────────────────────────────┘    │
           │                                             │
           ▼                                             │
┌──────────────────────────────────────────────────┐    │
│  Phase 3: Element Matching (page-scoped)         │    │
│  (per FAQ, one sub-pass per involved page)       │    │
└──────────┬───────────────────────────────────────┘    │
           │                                             │
           ▼                                             ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 4: Possible Questions + Embedding                    │
│  (batch, one LLM call per Intent + one embed call per Intent)│
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
              ┌───────────────────────┐
              │  Phase 5: Write Neo4j │
              │  (atomic per Intent)  │
              └───────────────────────┘
```

---

## 5.1 Phase 1 — Classify + Resolve Page IDs

**Input:** One FAQ (all fields including `category`, `subcategory`, `subsubcategory`, `question`, `answer` HTML-stripped).
**Also provided:** Full list of 60 `Page` nodes: `{page_id, title, desc}`.

**LLM output (structured JSON):**
```json
{
  "intent_type": "procedural",
  "intent_id": "tambah_karyawan_per_karyawan",
  "label": "Menambahkan Karyawan per-Karyawan",
  "page_ids": ["/customer/employee", "/customer/employee/add"],
  "page_notes": {
    "/customer/employee": "User navigates here first and clicks the add button",
    "/customer/employee/add": "Multi-tab form page where employee data is filled"
  }
}
```

The `page_notes` field is a structured annotation the Phase 1 LLM writes to itself — it carries context about **which steps happen on which page**. Phase 3 reads this to know the page sequence without guessing.

**Why category helps here:** `category: "karyawan"`, `subcategory: "daftar_karyawan"` is a strong prior that `/customer/employee` is involved. The LLM should use this to disambiguate when page title matching is ambiguous.

**No peeking inside pages at this phase.** The FAQ answers name pages literally ("Di menu Karyawan pilih Daftar Karyawan"). Providing 4,365 elements as context is impossible token-budget-wise and unnecessary.

---

## 5.2 Phase 2 — Step Draft Extraction

**Only for `procedural` FAQs.** Input: HTML-stripped answer + `page_notes` from Phase 1.

**LLM output:**
```json
{
  "steps": [
    {
      "order": 1,
      "page_id": "/customer/employee",
      "action": "click",
      "description": "Klik tombol Tambah Karyawan",
      "element_hint": "Tambah Karyawan"
    },
    {
      "order": 2,
      "page_id": "/customer/employee/add",
      "action": "input",
      "description": "Isi input Nama Depan karyawan",
      "element_hint": "Nama Depan"
    }
  ]
}
```

Each step carries its `page_id`. This allows Phase 3 to know exactly which page's element list to query for each step.

**No `element_hint` is stored in the NKG.** It is a Phase 2→3 intermediate artifact only, used to guide element matching. The final NKG only stores `nkg_id`, `order`, and `action` on `HAS_STEP`. The resolved element's `text` and `desc` are already on the Element node.

---

## 5.3 Phase 3 — Element Matching (Critical Phase)

This is the most important and most careful phase.

### Completeness Requirement

**All steps must be captured — no gaps allowed.** The classic failure scenario:

> FAQ describes: go to employee page → click Add → fill tab 1 inputs A, B, C → fill tab 2 inputs D, E → click Save.

If the extracted steps only include {click Add, click Save}, the runtime agent will highlight Save without telling the user to fill the form. This breaks guidance.

Specifically:
- Every **form input** in a multi-step form must be a separate `HAS_STEP`.
- Every **tab switch** (if a tab must be clicked to reveal inputs) must be a step.
- Every **modal trigger** (if a button must be clicked to open a modal before its fields are visible) must be a step — the modal-triggering button is a step *before* the modal's fields.
- The pipeline must detect and include **intermediate container triggers** (buttons/tabs that reveal hidden sections) as steps, even if the FAQ doesn't mention them explicitly.

This means: if the FAQ says "fill in Nama Depan, Nama Belakang" but on the real page those fields are inside a tab that must be clicked first, the LLM must insert the tab-click step by reading the actual page element structure.

### Multi-Page Resolution Strategy

Phase 3 processes one page at a time, in the sequence determined by `page_notes` from Phase 1. The LLM carries accumulated step context across pages.

**Per-page sub-pass:**
1. Fetch elements for the current page: you MUST write and use a new `get_page_elements_with_hierarchy(page_id)` from `graph_db.py`. Do NOT use the standard `get_page_elements` because it lacks `parent_element_id` (`[:CONTAINS]`) and `[:TRIGGERS]` relations, which are absolutely critical for the LLM to infer the hierarchy (e.g. knowing which inputs belong inside which tabs or modals).
2. Render elements as a flat structured text (see Section 5.3.1 below) that explicitly shows parent/trigger relationships.
3. LLM receives: the rendered page elements + the step drafts assigned to this page + accumulated steps from previous pages.
4. LLM resolves step drafts to `nkg_id`s, and **crucially**, inserts missing steps (like clicking tabs/modals) using the hierarchy context.
5. Accumulated steps carry over to the next page sub-pass.

This avoids feeding two pages at once (which would mix up element lists). The LLM sees one page at a time but maintains step sequence awareness.

### 5.3.1 — How to Render Page Elements for the LLM

**Do not use the `get_page_content` tool's output format.** That format is grouped by type (BUTTON, INPUT, etc.) and truncated at 50 elements — both are wrong for this use case.

Instead, render a **hierarchical list** that exposes the DOM structure (parents and triggers):

```
Page: /customer/employee/add — Tambah Karyawan
Total elements: 87

[tab]       tab_info_dasar       (Triggers: form_info_dasar)  "Informasi Dasar"
[tab]       tab_jadwal           (Triggers: form_jadwal)      "Jadwal"
[input]     input_nama_depan     (Parent: form_info_dasar)    "Nama Depan" — Input nama depan karyawan
[input]     input_nama_belakang  (Parent: form_info_dasar)    "Nama Belakang" — Input nama belakang
[button]    btn_simpan           (Parent: root)               "Simpan" — Tombol simpan data karyawan
...
```

Format per row: `[type]  id  (Parent/Trigger relation)  "text"  — desc`

Sort order within the rendered list: group elements by their `parent_element_id` or logical container. Tabs and modals appear before their contained fields. This mirrors visual hierarchy — the LLM can infer that an input with `Parent: modal_add` requires clicking the button that `Triggers: modal_add` beforehand.

**No truncation in Phase 3.** If a page has 150 elements, all 150 are fed. The page-scoping already reduced the search space from 4,365; truncating further defeats the purpose.

### 5.3.2 — LLM Output

```json
{
  "resolved_steps": [
    {
      "order": 1,
      "nkg_id": "/customer/employee/btn_add",
      "action": "click",
      "confidence": "high",
      "note": ""
    },
    {
      "order": 2,
      "nkg_id": "/customer/employee/add/tab_info_dasar",
      "action": "click",
      "confidence": "high",
      "note": "Inserted: tab must be active before its inputs are reachable"
    },
    {
      "order": 3,
      "nkg_id": "/customer/employee/add/input_nama_depan",
      "action": "input",
      "confidence": "high",
      "note": ""
    }
  ]
}
```

`confidence` (`high` / `medium` / `low`) is used for **review flagging only** — not for automated gating. All steps are written to Neo4j. Low-confidence steps are logged to `review_log.json` for human inspection.

### 5.3.3 — No Runtime Search Tools Needed

Phase 3 does **not** need `search_elements_by_intent`, `search_elements_by_text`, or any other runtime tool. The LLM receives the full element list for the scoped page and does reading comprehension — matching text labels to element IDs. This is more accurate than vector search for this use case because:
- The search space is 50–150 elements (not 4,365).
- The FAQ's button labels (e.g., "Tambah Karyawan") often exactly match `Element.text`.
- No retrieval ambiguity exists at this scale.

---

## 5.4 Phase 4 — Possible Questions + Embedding

**When to do this:** After Phase 3 is complete for all FAQs and steps are fully resolved. This phase is independent of the step resolution — it only needs the Intent's `label`, `type`, `category`, `subcategory`, and `content`.

**Possible questions generation (one LLM call per Intent):**

Provide: `label`, `type`, `category`, `subcategory`, cleaned answer content.
Ask for: 4–6 paraphrase questions in Bahasa Indonesia covering formal, informal, and abbreviated registers.

Example output for `"Menambahkan Karyawan per-Karyawan"`:
```json
{
  "possible_questions": [
    "Bagaimana cara menambahkan karyawan baru?",
    "Cara tambah karyawan di fingerspot.io",
    "Gimana nambah karyawan?",
    "Langkah daftarkan karyawan baru",
    "Tambah karyawan satu per satu caranya gimana?"
  ]
}
```

**Embedding (one embed call per Intent):**

Uses the same Qwen3 embedding model via `get_settings().embedding_model` and the same proxy via `get_settings().ollama_proxy_url`. Call the `/api/embeddings` endpoint directly (same pattern as `get_query_embedding()` in `llm.py`).

Embedding document format:
```
Instruct: Represent a user's navigation intent or knowledge query in a HR SaaS platform
so that it can be retrieved when a user asks a related question.
Document: Intent: {label}
Kategori: {category} > {subcategory}
Tipe: {type}
Pertanyaan: {possible_questions joined by " | "}
Konten: {content or first 200 chars of step summary}
```

---

## 5.5 Phase 5 — Write to Neo4j

**File:** `faq_pipeline/graph_db_write.py` — write-only functions, separate from the read-only `core/graph_db.py`.

**Re-run strategy:** Use `MERGE` on the Intent node (idempotent by `id`). For `HAS_STEP` and `ABOUT_PAGE`, delete existing relationships before re-creating. This handles cases where steps change between runs cleanly:

```cypher
-- Write Intent node
MERGE (i:Intent {id: $intent_id})
SET i += $props

-- Clear + rewrite steps (atomic)
MATCH (i:Intent {id: $intent_id})-[r:HAS_STEP]->() DELETE r;
UNWIND $steps AS step
  MATCH (e:Element {nkg_id: step.nkg_id})
  MATCH (i:Intent {id: $intent_id})
  MERGE (i)-[:HAS_STEP {order: step.order, action: step.action}]->(e)

-- Clear + rewrite page links
MATCH (i:Intent {id: $intent_id})-[r:ABOUT_PAGE]->() DELETE r;
UNWIND $page_ids AS pid
  MATCH (p:Page {id: pid})
  MATCH (i:Intent {id: $intent_id})
  MERGE (i)-[:ABOUT_PAGE]->(p)
```

Each Intent is one atomic write transaction. If any step's `nkg_id` doesn't resolve to a real Element, the transaction fails and the error is logged — the pipeline continues to the next FAQ.

---

## 6. LLM Usage

**Model:** `gemma4:31b` via the Ollama proxy — same as the runtime agent.
**Client:** Use `get_llm()` from `src/nkg_agent/core/llm.py`. The `ChatOllama` instance is already configured with the proxy URL, auth token, and model.
**Embedding:** Use `get_settings()` from `src/nkg_agent/core/config.py` — `settings.embedding_model`, `settings.ollama_proxy_url`, `settings.ollama_proxy_token`. Call `/api/embeddings` directly (same as `get_query_embedding()` in `llm.py`).

**Local backend mode:** The pipeline must support running against a local Ollama instance (for cases where the script runs on the same Jupyter Lab server as the LLM). Check for a `--mode local` CLI flag. When local: use `OLLAMA_BASE_URL` from `.env` instead of `OLLAMA_PROXY_URL`, and skip the `X-API-Token` header.

---

## 7. Code Structure

```
llm_based_agent/
├── src/
│   └── nkg_agent/              # Runtime agent — DO NOT MODIFY during pipeline work
│       └── core/               # ← Pipeline imports from here only
│           ├── config.py
│           ├── llm.py
│           └── graph_db.py
│
└── faq_pipeline/               # ← NEW offline pipeline package
    ├── __init__.py
    ├── pipeline.py             # CLI entry point — orchestrates phases, accepts --mode flag
    │
    ├── phases/
    │   ├── __init__.py
    │   ├── phase1_classify.py  # Classify FAQ type + resolve page_ids + page_notes
    │   ├── phase2_steps.py     # Extract ordered step drafts with page_id per step
    │   ├── phase3_match.py     # Page-scoped element matching, one page at a time
    │   ├── phase4_embed.py     # Generate possible_questions + compute embeddings
    │   └── phase5_write.py     # Atomic Neo4j writes (Intent + HAS_STEP + ABOUT_PAGE)
    │
    ├── prompts/
    │   ├── __init__.py
    │   ├── classify.py         # Phase 1 system + user prompt templates
    │   ├── step_draft.py       # Phase 2 prompt templates
    │   ├── element_match.py    # Phase 3 prompt templates (page render + step matching)
    │   └── paraphrase.py       # Phase 4 prompt templates
    │
    ├── models.py               # Pydantic models: IntentDraft, StepDraft, ResolvedStep, etc.
    ├── graph_db_write.py       # Write-only Cypher (MERGE Intent, HAS_STEP, ABOUT_PAGE)
    ├── html_cleaner.py         # Strip HTML tags + inline images from FAQ answers
    └── review_log.py           # Append low-confidence steps to review_log.json
```

**Import rule:** `faq_pipeline/` may import from `src/nkg_agent/core/` only. It must never import from `src/nkg_agent/agent/` or `src/nkg_agent/tools/` — those are runtime concerns.

---

## 8. What's Not Needed

| Rejected approach | Reason |
|:---|:---|
| Confidence-gating writes | Scores are uniformly high in the single-domain NKG. All steps are written; `confidence` field only drives review flagging. |
| Using runtime `search_elements_by_intent` in Phase 3 | Returns 5–10 candidates across 4,365 elements. Phase 3 instead reads all elements from a scoped page — reading comprehension beats retrieval here. |
| Separate `:Rules` node label | Informational `:Intent` nodes with `content` and `possible_questions` serve the same purpose. One node label, one vector index. |
| Confidence-gated MERGE (skip uncertain steps) | A missing step is worse than a slightly wrong step — the runtime agent can reason about uncertainty but cannot reason about absent data. |
| `element_hint` stored in NKG | It's a Phase 2→3 working variable. The resolved element's `text` and `desc` already live on the Element node. |

---

## 9. Decisions Made

| Question | Decision |
|:---|:---|
| LLM for pipeline | `gemma4:31b` — same as runtime. Consistent structured output behavior. |
| Human review scope | Only `confidence: medium/low` steps → logged to `review_log.json`. High-confidence steps are accepted automatically. |
| Re-run strategy | `MERGE` Intent node (idempotent) + `DELETE` then recreate `HAS_STEP` / `ABOUT_PAGE` on re-run. FAQ updates are not expected, but this handles them cleanly. |
| `ABOUT_PAGE` for ambiguous informational FAQs | Phase 1 LLM decides based on answer text first. If unconfident, it uses `category` + `subcategory` as a hint (not a direct mapping — the LLM still resolves to a `page_id`). If the LLM cannot resolve, `ABOUT_PAGE` is left blank and a warning is logged. Manual fix by author if needed. |

---

## 10. Runtime Agent Integration (Subsequent Task)

> **Do not implement this until the pipeline is complete and Neo4j Intent nodes are verified.**

After the pipeline runs successfully, add two tools to `src/nkg_agent/tools/`:

### `get_workflow_by_intent`

Semantic search on `intent_embedding_idx`, then fetch ordered `HAS_STEP` elements. Returns step-by-step `nkg_id` + `selector` + `action` for `procedural` intents; returns `content` for `informational` intents.

This tool should be the **first tool the runtime agent calls** for any "how do I..." query. It bypasses the current multi-step `get_page_content` reasoning loop entirely when a matching Intent exists.

### `get_intents_by_page` (lower priority)

Returns all Intents `ABOUT_PAGE` for a given `page_id`. Enables proactive suggestions when the agent knows the user's current page.

---

## 11. Thesis Documentation

Write the thesis chapter on this pipeline **after implementation, not before**. The implementation plan may shift slightly during coding. The implementation plan itself is a valid appendix/reference document. The thesis narrative should be written against the working code, not against this plan.

Key thesis points this pipeline supports:
- Justification for Intent node design (FAQ as ground truth for navigational intent)
- Rationale for offline vs. runtime extraction (correctness, determinism, performance)
- The completeness requirement for `HAS_STEP` chains (intermediate triggers, multi-tab forms)
- The page-scoped reading comprehension approach vs. global vector search

---

## 12. Estimated Effort

| Task | Est. Time |
|:---|:---|
| Schema + index creation (`phase5_write.py` setup block) | 20 min |
| `models.py` + `html_cleaner.py` + `review_log.py` | 30 min |
| Phase 1 (classify + page_ids + page_notes) | 45 min |
| Phase 2 (step draft with page_id per step) | 30 min |
| Phase 3 (element matching, page-scoped, sequential) | 60 min |
| Phase 4 (paraphrases + embeddings) | 30 min |
| Phase 5 (atomic Neo4j writes) | 30 min |
| `pipeline.py` CLI orchestrator + `--mode local` flag | 20 min |
| Human review of `review_log.json` | 1–2 hours |
| **Total (coding)** | **~4 hours** |
