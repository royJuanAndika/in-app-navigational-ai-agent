# Pipeline Phases: Technical Breakdown

The pipeline operates in five distinct phases to ensure maximum data quality.

## Phase 1: Classification & Page Resolution
*   **Goal:** Determine if an FAQ is `procedural` or `informational` and identify which UI pages are relevant.
*   **Logic:** The LLM receives a list of all 60+ application pages (ID, Title, Description).
*   **Safety:** The LLM uses the FAQ's `category/subcategory` as a hint but performs semantic matching to find the correct `page_id`. It outputs "Page Notes" explaining why each page was selected.

## Phase 2: Step Draft Extraction
*   **Goal:** Extract a raw sequence of user actions from the FAQ answer.
*   **Enforcement:** Strictly enforces **Bahasa Indonesia** for descriptions to match the NKG's language.
*   **Context:** Uses the "Page Notes" from Phase 1 to assign every step to a specific `page_id`.

## Phase 3: Element Matching (Hierarchy Aware)
*   **Goal:** Match text-based drafts (e.g., "Klik tombol tambah") to unique technical NKG IDs (e.g., `/customer/employee/btn_add`).
*   **The "Hierarchy Tool":** The LLM is provided with a hierarchical rendering of elements on the target page:
    *   Sorted by **Tab > Modal > Button > Input**.
    *   Includes `parent_nkg_id` and `triggers_nkg_id` metadata.
*   **Automatic Correction:** If a draft refers to a field hidden inside a Modal, and that Modal is not open, the LLM is instructed to **insert a new 'click' step** for the button that `TRIGGERS` that Modal.

## Phase 4: Paraphrasing & Embedding
*   **Goal:** Prepare the Intent for semantic retrieval.
*   **Paraphrasing:** Generates 4-6 variations of the FAQ question in formal and informal registers (e.g., "Gimana cara...", "Langkah atur...").
*   **Embedding:** Uses asymmetric instructions (`INTENT_DOC_INSTRUCTION`) to create a high-dimensional vector. 
*   **Signal Optimization:** Captures only the first 200 chars of text or 5 steps to maintain a high signal-to-noise ratio.

## Phase 5: Neo4j Persistence
*   **Goal:** Idempotent write to the database.
*   **Strategy:** 
    1. `MERGE` the Intent node by ID.
    2. `DELETE` all existing `HAS_STEP` and `ABOUT_PAGE` relationships for that ID.
    3. `UNWIND` and recreate the relationships from the new data.
*   **Benefit:** This allows the pipeline to be re-run indefinitely without polluting the graph with duplicate or stale connections.
