# In-App Navigational AI Agent (NKG Agent)

An AI agent named **Anya** that guides Indonesian HR administrators through the **Fingerspot.io** SaaS admin panel. Users ask natural-language questions in Bahasa Indonesia (e.g. *"cara tambah karyawan baru"*) and the agent returns step-by-step navigation instructions with CSS selectors and page URLs so the frontend can visually highlight the correct UI elements.

The agent does **not** perform actions — it teaches users where to click.

## Tech Stack

- **Python** >= 3.11
- **LangGraph** (ReAct agent via `create_react_agent`)
- **LangChain** (`langchain-core`, `langchain-ollama`, `langchain-openai`)
- **Neo4j 5+** (graph database for the Navigational Knowledge Graph)
- **Ollama** embeddings (`qwen3-embedding:8b`, 4096 dims)
- **RapidFuzz** (Levenshtein fuzzy matching)
- **FastAPI** + Uvicorn
- **Pydantic Settings** (env-based config)
- **LLM backends:** Ollama proxy, local Ollama, or OpenRouter (`gemma4:latest`, `google/gemini-2.5-flash-preview`, etc.)

## Project Structure

```
├── README.md
├── requirements.txt                  # Full pip freeze (pinned)
└── llm_based_agent/                  # Main application package
    ├── pyproject.toml                # Package metadata + dependencies
    ├── .env.example                  # Config template (Neo4j, LLM, models)
    └── src/
        ├── run_api.sh                # Linux startup
        ├── run_api.bat               # Windows startup (conda)
        └── nkg_agent/
            ├── core/
            │   ├── config.py         # Pydantic Settings (all env vars)
            │   ├── graph_db.py       # Neo4j data-access layer
            │   └── llm.py            # LLM + embedding clients
            ├── agent/
            │   ├── prompts.py        # System prompt (Bahasa Indonesia) + reformat
            │   └── graph.py          # LangGraph ReAct agent, chat(), streaming
            ├── api/
            │   └── server.py         # FastAPI endpoints
            └── tools/                # 12 LangChain tools
                ├── workflow_by_intent.py
                ├── semantic_search.py
                ├── intents_by_page.py
                ├── page_content.py
                ├── element_details.py
                ├── find_page.py
                ├── text_search.py
                ├── find_trigger_prerequisites.py
                ├── container_content.py
                ├── form_fields.py
                └── cypher_query.py
```

## Knowledge Graph Schema (Neo4j)

**Nodes:**
- `Page` — `id` (URL path), `title`, `desc`
- `Element` — `nkg_id`, `id` (DOM id), `page_id`, `type`, `text`, `selector`, `embedding`
- `Intent` — `id`, `label`, `type`, `content`, `embedding`

**Relationships:**
- `(Page)-[:CONTAINS]->(Element)`
- `(Element)-[:TRIGGERS]->(Element|Page)`
- `(Intent)-[:HAS_STEP {order, action}]->(Element)`
- `(Intent)-[:ABOUT_PAGE]->(Page)`

## Tools (12)

| Priority | Tool | Purpose |
|----------|------|---------|
| 1 | `search_intents` | Vector search on Intent embeddings |
| 2 | `get_steps_for_intent` | Expand intent into ordered workflow steps |
| 3 | `search_elements_by_intent` | Vector search on Element embeddings |
| 4 | `get_intents_by_page` | List intents for a known page |
| 5 | `find_page` | Fuzzy search pages by title/URL |
| 6 | `get_element_details` | Element properties + forward triggers |
| 7 | `find_trigger_prerequisites` | Backward trigger lookup |
| 8 | `get_form_fields_on_page` | Form controls on a page |
| 9 | `get_container_content` | Elements inside a container/modal/tab |
| 10 | `get_page_content` | All elements on a page |
| 11 | `search_elements_by_text` | Fuzzy text search (Levenshtein) |
| 12 | `execute_cypher_read_query` | Last-resort raw Cypher (read-only) |

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/chatbot/message` | POST | Primary chat |
| `/api/chatbot/stream` | POST | SSE streaming (thinking/tool events) |
| `/api/chatbot/enrich` | POST | Batch-resolve NKG IDs |
| `/api/chatbot/log` | POST | Frontend debug log ingestion |
| `/health` | GET | Health check (Neo4j + model info) |
| `/api/review/intents` | GET | Review dashboard |
| `/api/review/status` | GET/POST | Review status |
| `/api/review/note` | POST | Save review notes |
| `/api/review/rerun` | POST | Re-run Phase 3 with feedback |
| `/api/review/revert` | POST | Revert intent steps |
| `/api/review/node/update` | POST | Update element selector/id |
| `/api/review/jobs` | GET | Background job status |

## Setup

### Prerequisites

- Python >= 3.11
- Neo4j 5+ with the NKG loaded (including HNSW vector indexes)
- Ollama (local or remote proxy) with `gemma4:latest` and `qwen3-embedding:8b`
- OR an OpenRouter API key

### 1. Create conda environment

```bash
conda create -n in-app-navigational-agent python=3.11
conda activate in-app-navigational-agent
```

### 2. Install dependencies

```bash
cd llm_based_agent
pip install -e .
```

### 3. Configure environment

```bash
cp llm_based_agent/.env.example llm_based_agent/.env
```

Fill in the `.env` file:

| Variable | Description |
|----------|-------------|
| `NEO4J_URI` | Neo4j Bolt URI (default: `bolt://localhost:7687`) |
| `NEO4J_USER` | Neo4j username |
| `NEO4J_PASSWORD` | Neo4j password |
| `LLM_BACKEND` | `proxy` / `local` / `openrouter` |
| `OLLAMA_PROXY_URL` | Remote Ollama proxy URL (if using proxy) |
| `OLLAMA_PROXY_TOKEN` | Auth token for proxy (if using proxy) |
| `OPENROUTER_API_KEY` | OpenRouter API key (if using openrouter) |
| `LLM_MODEL` | Ollama model (default: `gemma4:latest`) |
| `OPENROUTER_MODEL` | OpenRouter model (default: `google/gemini-2.5-flash-preview`) |
| `EMBEDDING_MODEL` | Ollama embedding model (default: `qwen3-embedding:8b`) |

### 4. Run the server

```bash
# Windows
cd llm_based_agent/src
run_api.bat

# Linux/macOS
cd llm_based_agent/src
bash run_api.sh

# Manual
cd llm_based_agent/src
uvicorn nkg_agent.api.server:app --reload --port 8001
```

Server starts on **port 8001**.

## Response Format

The agent returns structured JSON:

```json
{
  "message": "Penjelasan untuk pengguna",
  "type": "guidance",
  "guidance": [
    {
      "step": 1,
      "instruction": "Klik tombol 'Karyawan' di sidebar",
      "nkg_id": "/hr/employee/btn-employee"
    }
  ]
}
```

After the agent produces `nkg_id` values, `enrich_guidance_steps()` resolves `page_url`, `selector`, and `element_id` from Neo4j so the frontend can highlight the correct UI elements.
