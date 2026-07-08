# AGENTS.md

## Project

In-App Navigational AI Agent — guides users through an HR SaaS admin panel (47 pages, 400+ elements) using a Navigational Knowledge Graph (NKG) in Neo4j. Thesis project.

## Two Main Areas

- **`llm_based_agent/`** — the LangGraph ReAct agent, API server, and FAQ pipeline. This is the primary code area.
- **`data_preprocessing_and_cleaning/`** — NKG data prep: scraping, element extraction, embedding, Neo4j insertion. Scripts, not a runnable app.

## Environment & Setup

- **Conda env:** `in-app-navigational-agent` (Python 3.11+, lives in `.conda/`)
- **`.env` files:** `llm_based_agent/.env` (primary) and root `.env` (data pipeline). Both are gitignored.
- **`llm_based_agent/.env.example`** has all required vars. Key ones:
  - `LLM_BACKEND`: `proxy` | `local` | `openrouter` (default in example: `openrouter`)
  - `NEO4J_URI`: `bolt://localhost:7688` (non-standard port)
  - `OPENROUTER_API_KEY`, `OLLAMA_PROXY_URL`, `OLLAMA_PROXY_TOKEN` — all required depending on backend

## Run Commands

```bash
# Activate env
conda activate in-app-navigational-agent

# Run API server (from llm_based_agent/src/)
uvicorn nkg_agent.api.server:app --reload --port 8001

# Or use the scripts
llm_based_agent/src/run_api.sh   # Linux
llm_based_agent/src/run_api.bat  # Windows
```

No test suite exists yet (`tests/` directory is planned but empty). No lint/typecheck config.

## Architecture (llm_based_agent/src/nkg_agent/)

```
core/       → config.py (Pydantic Settings), llm.py (Ollama/OpenRouter), graph_db.py (Neo4j driver)
tools/      → 12 agent tools (semantic search, page content, element details, fuzzy text, cypher, etc.)
agent/      → graph.py (LangGraph ReAct agent), prompts.py (system prompt)
api/        → server.py (FastAPI: /api/chatbot/message, /chat, /health)
```

Dependency flow: `api → agent → tools → core`. No circular imports.

## Key Conventions

- Project name: **"In-App Navigational Agent"**, not "NKG Agent"
- LLM model: `gemma4:31b` via Ollama proxy or `google/gemini-3-flash-preview` via OpenRouter
- Embedding: `qwen3-embedding:8b` (4096 dimensions)
- After every work session, update docs in `llm_based_agent/docs/` — docs must tell the full story without reading code
- Refer to `llm_based_agent/docs/implementation_plan/` for architecture decisions

## Neo4j Schema

- **Nodes:** `Page` (60), `Element` (4365, all with embeddings), `Intent` (not yet implemented)
- **Relationships:** `CONTAINS` (Page→Element), `TRIGGERS` (Element→Element/Page), `HAS_STEP` (Intent→Element, ordered), `HAS_INTENT` (Page→Intent)

## Data Pipeline (data_preprocessing_and_cleaning/)

Sequential: `scrape_faq/` → `cleaning/` → `prompting_chunk/` → `extract_element_text/` → `embed/` → `insert_neo4j/` → `validate/`. Each dir has its own scripts and READMEs.

### Pipeline Phases

| Phase | Dir | Input | Output | What it does |
|-------|-----|-------|--------|--------------|
| 0 | `scrape_faq/` | Web FAQ pages | `help_center_faq.json` | Scrapes help center FAQ content |
| 1 | `data/scraped_html/` | 47 scraped HTML pages | Same (raw) | ~25K lines, ~1.4MB per page |
| 2 | `cleaning/` | `actual_raw_html/*.html` | `cleaned_html_2/*.html` | Removes nav, sidebar, chat, scripts, styles. ~89% reduction (25K→8.5K lines avg). Uses `2_clean_html.ipynb` (CANDIDATES CSS selectors for chrome) + `4_clean_html_filter.ipynb` (PRESTRIP tag removal: `<script>`, `<style>`, `<link>`) |
| 3 | `prompting_chunk/` | `cleaned_html_2/*.html` | `nkg_gpu3/*.nkg.json` | Core script: `chunked_html_to_nkg.py`. Splits HTML into ~18KB chunks, sends each to LLM (gemma4:31b) with NKG schema prompt, merges results, validates selectors. ~83% DOM ID coverage avg |
| 4 | `fix_orphans.py` | `nkg_gpu3/*.nkg.json` | `nkg_gpu3_fix_orphans/*.nkg.json` | LLM-powered repair of orphan parent_element_ids and bad trigger targets |
| 5 | `extract_element_text/` | nkg + cleaned HTML | `nkg_gpu3_fix_orphans_with_text/*.nkg.json` | Extracts visible text from HTML for each NKG element via CSS selector, injects `"text"` field |
| 6 | `embed/` | nkg with text | `embeddings_neo4j.jsonl` | qwen3-embedding:8b (4096-dim) on Indo-language passages |
| 7 | `insert_neo4j/` | nkg JSON | Neo4j graph | MERGE Page/Element/CONTAINS/TRIGGERS via cypher_payload |

### Key files

- `cleaning/lib/clean_html_utils.py` (853 lines) — BeautifulSoup-based HTML cleaning utilities
- `prompting_chunk/chunked_html_to_nkg.py` (2045 lines) — the core HTML→NKG LLM extraction pipeline
- `prompting_chunk/batch_process_nkg.py` (233 lines) — batch runner with one-shot example propagation

### Script tag testing

`script_tag_testing_pak_adi/` — tests whether keeping `<script>` tags (which contain function definitions referenced by `onclick` attributes) improves the LLM's trigger identification accuracy. Compares a "with-script" cleaned variant against the existing no-script cleaned HTML on the `scan.html` page.

## Gotchas

- `.conda/` is a portable conda env committed to the repo (unusual) — don't delete or modify it
- `requirements.txt` is a pip freeze snapshot, not the source of truth (pyproject.toml is)
- No CI workflows, no pre-commit hooks
- FAQ pipeline (`llm_based_agent/faq_pipeline/`) is a separate multi-phase LLM pipeline for generating intents from FAQ data
