# 04 — Component Specifications

Detailed specification for each infrastructure module.

---

## 1. `config.py` — Settings

### Purpose
Centralized, type-safe configuration loaded from `.env`.

### Interface
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str

    # Ollama Proxy
    ollama_proxy_url: str
    ollama_proxy_token: str

    # Models
    llm_model: str = "gemma4:31b"
    embedding_model: str = "qwen3-embedding:8b"
    embedding_dimensions: int = 1024

    # Agent
    llm_temperature: float = 0.3
    llm_max_tokens: int = 2048
    search_top_n: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

# Singleton
_settings: Settings | None = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

### `.env` file mapping
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=hellhound
OLLAMA_PROXY_URL=https://youtube.com
OLLAMA_PROXY_TOKEN=sk-ollama-...
```

Pydantic-settings automatically maps `NEO4J_URI` → `neo4j_uri` (case-insensitive).

---

## 2. `llm.py` — LLM & Embedding Client

### Purpose
Initializes and exposes the ChatOllama LLM and embedding function.

### LLM Interface
```python
from langchain_ollama import ChatOllama

def get_llm() -> ChatOllama:
    """Get the configured ChatOllama instance for tool-calling."""
    settings = get_settings()
    return ChatOllama(
        model=settings.llm_model,
        base_url=settings.ollama_proxy_url,
        client_kwargs={
            "headers": {"X-API-Token": settings.ollama_proxy_token}
        },
        temperature=settings.llm_temperature,
        num_predict=settings.llm_max_tokens,
    )
```

### Embedding Interface
```python
import requests

QUERY_INSTRUCTION = (
    "Given a user's navigation intent or action description, "
    "find the most relevant UI element in the web application "
    "that the user wants to interact with."
)

def get_query_embedding(text: str) -> list[float]:
    """Embed a query using asymmetric instruction for retrieval."""
    settings = get_settings()
    prompt = f"Instruct: {QUERY_INSTRUCTION}\nQuery: {text}"
    
    response = requests.post(
        f"{settings.ollama_proxy_url.rstrip('/')}/api/embeddings",
        json={"model": settings.embedding_model, "prompt": prompt},
        headers={"X-API-Token": settings.ollama_proxy_token},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["embedding"]
```

### Design Note
We use `requests` directly for embeddings (not `OllamaEmbeddings` from langchain) because:
- We need the asymmetric `Instruct:/Query:` prompt format
- `OllamaEmbeddings` doesn't support custom prompt prefixes
- Direct HTTP is simpler and has fewer dependencies

---

## 3. `graph_db.py` — Neo4j Data Access

### Purpose
All Neo4j queries live here. Tools call these functions. No Cypher in tool code.

### Connection Management
```python
from neo4j import GraphDatabase

_driver = None

def get_driver():
    global _driver
    if _driver is None:
        settings = get_settings()
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        _driver.verify_connectivity()
    return _driver

def close_driver():
    global _driver
    if _driver:
        _driver.close()
        _driver = None
```

### Query Functions

#### `vector_search(embedding, top_n) -> list[dict]`
```cypher
CALL db.index.vector.queryNodes('element_embedding_idx', $top_n, $vector)
YIELD node, score
RETURN
    node.nkg_id   AS nkg_id,
    node.id        AS element_id,
    node.page_id   AS page_id,
    node.type      AS type,
    node.desc      AS description,
    node.selector  AS selector,
    node.text      AS text,
    score
```

#### `get_page_elements(page_id) -> list[dict]`
```cypher
MATCH (p:Page {id: $page_id})-[:CONTAINS]->(e:Element)
RETURN e.nkg_id AS nkg_id, e.id AS element_id, e.type AS type,
       e.desc AS description, e.selector AS selector, e.text AS text
ORDER BY e.id
```

#### `get_element_info(nkg_id) -> dict | None`
```cypher
MATCH (e:Element {nkg_id: $nkg_id})
OPTIONAL MATCH (e)-[:TRIGGERS]->(target)
RETURN e.nkg_id AS nkg_id, e.id AS element_id, e.page_id AS page_id,
       e.type AS type, e.desc AS description, e.selector AS selector,
       e.text AS text,
       collect({
           target_type: labels(target)[0],
           target_id: COALESCE(target.nkg_id, target.id),
           target_title: target.title,
           target_desc: target.desc,
           target_selector: target.selector
       }) AS triggers
```

#### `find_pages(search_term) -> list[dict]`
```cypher
MATCH (p:Page)
WHERE toLower(p.title) CONTAINS toLower($search_term)
   OR toLower(p.id) CONTAINS toLower($search_term)
OPTIONAL MATCH (p)-[:CONTAINS]->(e:Element)
RETURN p.id AS page_id, p.title AS title, p.desc AS description,
       count(e) AS element_count
ORDER BY element_count DESC
```

#### `text_search_elements(text, limit) -> list[dict]`
```cypher
MATCH (p:Page)-[:CONTAINS]->(e:Element)
WHERE toLower(e.text) CONTAINS toLower($search_text)
RETURN e.nkg_id AS nkg_id, e.id AS element_id, e.page_id AS page_id,
       e.type AS type, e.desc AS description, e.selector AS selector,
       e.text AS text, p.title AS page_title
LIMIT $limit
```

### Error Handling
All query functions catch `neo4j.exceptions.ServiceUnavailable` and `neo4j.exceptions.SessionExpired`, reconnect, and retry once. Other exceptions propagate.

### Return Format
All functions return plain `list[dict]` or `dict | None`. No Pydantic models at this layer — tools handle formatting.
