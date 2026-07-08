# Session B Summary — FAQ Ingestion Pipeline (Phases 1 & 2)

## Status
- **Completed:** Phase 1 (Classify + Page Resolution)
- **Completed:** Phase 2 (Step Draft Extraction)
- **Completed:** Core Utility Updates (Local Mode + Token Limits)
- **Verified:** Dry-run successful for both procedural and informational FAQs.

## Implementation Details

### 1. Prompt Engineering
- **`faq_pipeline/prompts/classify.py`**: Instructs the LLM to categorize FAQs as `procedural` or `informational` and resolve them to specific `page_ids` using the 60-page NKG catalog and category hints.
- **`faq_pipeline/prompts/step_draft.py`**: Extracts high-granularity navigational steps. It enforces a "no-gap" policy, ensuring form fields, buttons, and transitions are captured as discrete steps.

### 2. Phase Logic
- **Phase 1 (`phase1_classify.py`)**: Implements `classify_faq` with a robust JSON extraction and validation loop. It includes a 2-retry mechanism to handle non-compliant LLM outputs.
- **Phase 2 (`phase2_steps.py`)**: Implements `extract_steps` which processes procedural FAQs to generate an ordered list of `StepDraft` objects.

### 3. Pipeline Orchestration
- **`faq_pipeline/pipeline.py`**: The CLI entry point. It handles:
  - Argument parsing (`--mode`, `--dry-run`, `--faq-id`).
  - Loading FAQs from `help_center_faq.json`.
  - Batch processing through the implemented phases.
  - Intermediate result persistence to `faq_pipeline/output/`.

### 4. Core Infrastructure Updates
- **`src/nkg_agent/core/config.py`**: 
  - Added `ollama_base_url` (default: `http://localhost:11434`) to support local inference.
  - Increased `llm_max_tokens` from 2048 to **4096** to accommodate large step-by-step JSON outputs for complex FAQs.
- **`src/nkg_agent/core/llm.py`**:
  - Added `set_llm_mode(mode)` to toggle between `proxy` and `local`.
  - Updated `get_query_embedding` to respect the selected mode.

## Verification Run Results

### Procedural Test (`tambah_karyawan_1`)
- **Result:** Success (after token limit increase).
- **Steps Extracted:** 17 steps.
- **Coverage:** Correctly identified the transition from the listing page to the form fields and captured every input (Nama Kantor, Nama Depan, etc.) from the HTML table.

### Informational Test (`pengaturan_umum_1`)
- **Result:** Success.
- **Classification:** `informational`.
- **Page Resolution:** Correctly mapped to `/customer/setting/profile`.

## Intermediate Artifacts
The following files were generated/updated in `faq_pipeline/output/`:
- `phase1_results.json`
- `phase2_results.json`

## Next Steps (Session C)
- Implement **Phase 3 (Element Matching)**: Resolving `element_hint` to actual `nkg_id` by reading the page element structure.
- Implement **Phase 4 (Paraphrase + Embedding)**: Generating semantic variations for better retrieval.
- Implement **Phase 5 (Neo4j Write)**: Atomic transactions to populate the NKG.
