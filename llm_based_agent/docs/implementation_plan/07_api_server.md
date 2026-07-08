# 07 — API Server

## File: `server.py`

FastAPI application that exposes the NKG agent as an HTTP API.

---

## Endpoints

### `POST /chat`

Main chat endpoint. Sends a user message to the agent and returns the response.

#### Request Schema
```python
class ChatRequest(BaseModel):
    message: str                          # User's natural language message
    current_page: str | None = None       # Current page path (e.g. "/customer/employee")
    session_id: str | None = None         # Future: for multi-turn memory
```

#### Response Schema
```python
class Action(BaseModel):
    type: str          # "navigate" | "highlight" | "scroll"
    selector: str | None = None    # CSS selector (e.g. "#btn_add")
    page: str | None = None        # Page path (e.g. "/customer/employee")
    label: str | None = None       # UI label for the action

class ChatResponse(BaseModel):
    message: str                   # Agent's natural language response
    actions: list[Action] = []     # DOM manipulation instructions (future)
    tools_used: list[str] = []     # Which tools the agent called
    duration_ms: int               # Processing time
```

#### Example Request
```json
POST /chat
{
    "message": "Bagaimana cara menambah karyawan baru?",
    "current_page": "/customer/dashboard"
}
```

#### Example Response
```json
{
    "message": "Untuk menambah karyawan baru:\n1. Buka halaman **Karyawan** (`/customer/employee`)\n2. Klik tombol **Tambah Karyawan** `[selector: #btn_add]`\n3. Akan muncul form...",
    "actions": [],
    "tools_used": ["search_elements_by_intent", "get_element_details"],
    "duration_ms": 4523
}
```

> **Note on `actions[]`:** In v1, actions are embedded in the text response (the frontend parses `[selector: ...]` patterns). Structured `actions[]` extraction is a v2 enhancement that would require output parsing from the LLM response.

---

### `GET /health`

Health check endpoint for monitoring.

```json
GET /health
→ {"status": "ok", "neo4j": "connected", "model": "gemma4:31b"}
```

---

## Server Implementation

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agent import create_agent
from .graph_db import get_driver, close_driver

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify connections. Shutdown: close connections."""
    # Startup
    get_driver()           # Verify Neo4j is reachable
    app.state.agent = create_agent()
    yield
    # Shutdown
    close_driver()

app = FastAPI(
    title="NKG Navigational Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     # Tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## CORS Configuration

The SaaS admin panel is on a different origin than the agent API. CORS must be enabled.

For development: `allow_origins=["*"]`  
For production: restrict to the SaaS domain.

---

## Error Handling

| Error | HTTP Status | Response |
|:------|:------------|:---------|
| Invalid request body | 422 | Pydantic validation error |
| Neo4j connection failure | 503 | `{"detail": "Database unavailable"}` |
| Ollama proxy timeout | 504 | `{"detail": "LLM service timeout"}` |
| Agent internal error | 500 | `{"detail": "Agent processing error"}` |

---

## Running the Server

```bash
# Development
cd llm_based_agent
uvicorn src.nkg_agent.server:app --reload --port 8000

# Or via Python
python -m src.nkg_agent.server
```

The server will be available at `http://localhost:8000` with Swagger docs at `http://localhost:8000/docs`.
