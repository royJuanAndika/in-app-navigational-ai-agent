# 02 — Tech Stack Decisions

Every technology choice with rationale and alternatives considered.

---

## 1. LLM — `gemma4:31b`

Use **Google Gemma 4 31B** via the Ollama proxy at `youtube.com`.

| Criteria | `gemma4:31b` | `deepseek-r1:70b` | `qwen3:32b` |
|:---------|:-------------|:-------------------|:------------|
| **Tool calling** | ✅ Native | ❌ Not supported | ✅ Supported |
| **Structured output** | ✅ `tool_calls` JSON | N/A | ✅ `tool_calls` JSON |
| **Thinking** | ✅ `thinking` field | ✅ Chain-of-thought | ✅ `thinking` field |
| **Size** | 31B (~20GB) | 70B (~42GB) | 32B (~20GB) |
| **Load time** | ~30s | ~100s+ | ~138s cold |

**DeepSeek-R1 rejected** — returns `400: does not support tools` when tool schemas are passed.

**Verified (2026-05-04):** gemma4:31b returns structured `tool_calls` with `thinking` trace.

---

## 2. Embedding — `qwen3-embedding:8b`

Already used for all 4,365 elements (1024-d, cosine). No re-embedding needed.

**API:** `POST /api/embeddings` with asymmetric `Instruct:/Query:` prompt.

---

## 3. Orchestration — LangGraph (replaces n8n)

| Criteria | LangGraph | n8n |
|:---------|:----------|:----|
| Language | Pure Python | Visual workflow (Node.js) |
| Debugging | Python debugger | Browser-based |
| Tool definition | `@tool` decorator | HTTP Request nodes |
| Thesis docs | Code is self-documenting | Screenshots |
| Testing | pytest | Limited |
| Version control | Git-friendly `.py` | JSON exports |

n8n can be added as a webhook layer on top later if needed.

---

## 4. LLM Binding — `langchain-ollama` (`ChatOllama`)

- Native LangGraph integration via `BaseChatModel`
- `.bind_tools()` for tool schemas
- Proxy auth: `client_kwargs={"headers": {"X-API-Token": "..."}}`
- Supports streaming via `.astream()`

**Why not `ChatOpenAI`?** Works (verified `/v1/chat/completions` returns 200), but `ChatOllama` gives native Ollama features and better error messages.

---

## 5. Knowledge Base — Neo4j (existing, `neo4j` driver)

**Why not `langchain-neo4j` `GraphCypherQAChain`?**
- Risky — LLM-generated Cypher could be destructive
- Unnecessary — our queries are predefined and parameterized
- Slower — extra LLM call to generate Cypher

We use **predefined parameterized Cypher** in `graph_db.py`, exposed via purpose-built tools.

---

## 6. API Server — FastAPI

Async-native, auto OpenAPI docs, Pydantic validation, CORS support.

---

## 7. Config — `pydantic-settings` (`BaseSettings`)

Type-safe `.env` loading with validation at startup.

---

## Dependencies

| Package | Version | Purpose | Status |
|:--------|:--------|:--------|:-------|
| `langgraph` | ≥ 0.4 | Agent orchestration | **NEW** |
| `langchain-ollama` | ≥ 0.3 | LLM binding | **NEW** |
| `langchain-core` | ≥ 0.3 | Base types (`@tool`, messages) | **NEW** |
| `neo4j` | 6.1.0 | Neo4j driver | Installed |
| `requests` | 2.32.5 | HTTP for embeddings | Installed |
| `fastapi` | ≥ 0.115 | API server | **NEW** |
| `uvicorn` | ≥ 0.34 | ASGI server | **NEW** |
| `python-dotenv` | ≥ 1.0 | .env loading | Installed |
| `pydantic-settings` | ≥ 2.0 | Typed settings | **NEW** |

```bash
pip install langgraph langchain-ollama langchain-core fastapi uvicorn pydantic-settings
```
