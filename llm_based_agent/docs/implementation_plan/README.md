# In-App Navigational Agent — Implementation Plan

> **Status:** Approved  
> **Created:** 2026-05-04  
> **LLM Model:** `gemma4:31b` (via Ollama proxy)  
> **Framework:** LangGraph + LangChain-Ollama + FastAPI

---

## Document Index

| # | Document | Description |
|:--|:---------|:------------|
| 01 | [Architecture Overview](./01_architecture.md) | High-level system diagram, data flow, and design rationale |
| 02 | [Tech Stack Decisions](./02_tech_stack.md) | Every technology choice with justification and alternatives considered |
| 03 | [Project Structure](./03_project_structure.md) | File/folder layout, module responsibilities, dependency graph |
| 04 | [Component Specifications](./04_components.md) | Detailed spec for each module: config, LLM, graph_db |
| 05 | [Agent Tools](./05_agent_tools.md) | All 9 tools — signatures, Cypher queries, input/output contracts |
| 06 | [Agent & Prompts](./06_agent_and_prompts.md) | LangGraph agent definition, system prompt design, ReAct loop |
| 07 | [API Server](./07_api_server.md) | FastAPI endpoints, request/response schemas, CORS, error handling |
| 08 | [Verification Plan](./08_verification.md) | CLI chat loop, iterative testing, thesis documentation |

## Related Documentation

| Document | Location |
|:---------|:---------|
| [Neo4j Schema](../neo4j_schema.md) | Full database schema, indexes, sample Cypher queries |
| [Embedding Index](../../../docs/embedding_index.md) | How embeddings are generated and indexed |
| [Generation Workflow](../../../docs/generation_workflow.md) | End-to-end NKG pipeline (HTML → Neo4j) |

---

## Key Decisions Summary

1. **`gemma4:31b`** replaces DeepSeek-R1 70B — DeepSeek-R1 does not support tool calling via Ollama
2. **LangGraph** replaces n8n — pure Python orchestration, better for development and thesis
3. **No `Intent`/`HAS_STEP` yet** — agent works with `Page` + `Element` nodes; Intent support is plug-and-play later
4. **6 agent tools** — semantic search, page content, element details, find page, fuzzy text search, cypher query (last resort)
5. **FastAPI server** — exposes `/chat` endpoint for frontend integration
6. **Fuzzy text search** — uses `rapidfuzz` Levenshtein distance instead of exact `CONTAINS` match
7. **Cypher query tool** — last-resort tool with read-only guardrails
8. **Graph visualization** — `agent.get_graph().draw_mermaid_png()` for thesis diagrams

## What's NOT in Scope (Yet)

- Frontend chat widget (follow-up conversation)
- `Intent` and `HAS_STEP` node insertion into Neo4j
- Streaming responses (can be added later)
- Persistent conversation memory across sessions
- n8n webhook integration

## Development Rules

1. **After every work session**, update or create documentation in `docs/` — the markdown files should tell the full story without needing to read the code
2. **Name**: This project is called **"In-App Navigational Agent"**, not "NKG Agent"
3. **Iterative testing**: Use CLI chat loop first, formal tests later
