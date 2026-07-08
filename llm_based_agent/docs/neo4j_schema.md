# Neo4j — Navigational Knowledge Graph (NKG) Schema

> **Last verified:** 2026-05-04 against the live database at `bolt://localhost:7687`

This document describes the structure of the Neo4j graph database that powers
the In-App Navigational AI Agent. The agent queries this graph at runtime to
translate user intents into step-by-step UI guidance.

---

## 1. Node Labels

| Label | Count | Description |
|:------|------:|:------------|
| `Page` | 60 | Represents a route/page in the SaaS admin panel (e.g. `/customer/employee`) |
| `Element` | 4 365 | Represents an interactive or informational DOM element on a page |

### 1.1 Page Properties

| Property | Type | Example | Description |
|:---------|:-----|:--------|:------------|
| `id` | `STRING` (unique) | `/customer/employee` | URL path — serves as the primary key |
| `title` | `STRING` | `Karyawan` | Human-readable page title (Bahasa Indonesia) |
| `desc` | `STRING` | `Halaman admin untuk mendukung alur kerja pengguna.` | Short page description |

### 1.2 Element Properties

| Property | Type | Example | Description |
|:---------|:-----|:--------|:------------|
| `nkg_id` | `STRING` (unique) | `/customer/employee/btn_add` | Scoped key = `{page_id}/{element_id}`. **Primary key.** |
| `id` | `STRING` | `btn_add` | Raw DOM element ID (may collide across pages) |
| `page_id` | `STRING` | `/customer/employee` | FK back to the owning Page node |
| `type` | `STRING` | `button`, `input`, `select`, `modal`, `table`, `element` | Semantic UI element type |
| `desc` | `STRING` | `Tombol untuk menambahkan karyawan baru` | LLM-generated description of what this element does (Bahasa Indonesia) |
| `selector` | `STRING` | `#btn_add` | CSS selector to target this element in the DOM |
| `text` | `STRING` | `Tambah Karyawan` | Visible inner text of the element (may be empty for hidden elements) |
| `embedding` | `FLOAT[]` (1024-d) | `[0.012, -0.034, ...]` | Qwen3-embedding vector for semantic search |

---

## 2. Relationship Types

| Type | Count | Pattern | Description |
|:-----|------:|:--------|:------------|
| `CONTAINS` | 4 365 | `(Page)-[:CONTAINS]->(Element)` | A page owns/contains an element |
| `TRIGGERS` | 557 | `(Element)-[:TRIGGERS]->(Element)` or `(Element)-[:TRIGGERS]->(Page)` | Clicking/interacting with an element causes another element to appear or navigates to another page |

### 2.1 CONTAINS

- **Page → Element**: Every `Element` is `CONTAINS`-ed by exactly one `Page`.  
- There are **no orphan elements** (verified).
- *(Note: `Element → Element` CONTAINS edges were defined in the insertion schema for nested UI like modals containing buttons, but the current dataset has 0 such edges.)*

### 2.2 TRIGGERS

Two flavors:
1. **Element → Element** (e.g. clicking a button opens a modal on the same page)
2. **Element → Page** (e.g. clicking a sidebar link navigates to another route)

No properties on the relationship itself.

---

## 3. Indexes

| Name | Type | On | Properties | Status |
|:-----|:-----|:---|:-----------|:-------|
| `page_id` | RANGE (unique constraint) | `Page` | `id` | ONLINE |
| `element_nkg_id` | RANGE (unique constraint) | `Element` | `nkg_id` | ONLINE |
| `element_embedding_idx` | VECTOR (HNSW) | `Element` | `embedding` | ONLINE |

### Vector Index Details

```
Index:       element_embedding_idx
Dimensions:  1024
Similarity:  cosine
Provider:    vector-3.0
Population:  100% (all 4 365 elements have embeddings)
```

---

## 4. Key Cypher Patterns

### 4.1 Semantic Search — Find Elements by User Intent

```cypher
CALL db.index.vector.queryNodes('element_embedding_idx', $top_n, $query_vector)
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

### 4.2 Get All Elements on a Page

```cypher
MATCH (p:Page {id: $page_id})-[:CONTAINS]->(e:Element)
RETURN e.nkg_id AS nkg_id, e.id AS element_id, e.type AS type,
       e.desc AS description, e.selector AS selector, e.text AS text
ORDER BY e.id
```

### 4.3 Find What an Element Triggers

```cypher
MATCH (e:Element {nkg_id: $nkg_id})-[:TRIGGERS]->(target)
RETURN labels(target)[0] AS target_type,
       COALESCE(target.nkg_id, target.id) AS target_id,
       target.title AS target_title,
       target.desc AS target_desc,
       target.selector AS target_selector
```

### 4.4 Find Page by Title (fuzzy)

```cypher
MATCH (p:Page)
WHERE toLower(p.title) CONTAINS toLower($search_term)
RETURN p.id AS page_id, p.title AS title, p.desc AS description
```

### 4.5 Exact Text Search on Elements

```cypher
MATCH (p:Page)-[:CONTAINS]->(e:Element)
WHERE toLower(e.text) CONTAINS toLower($search_text)
RETURN e.nkg_id AS nkg_id, e.id AS element_id, e.page_id AS page_id,
       e.type AS type, e.desc AS description, e.selector AS selector, e.text AS text
```

### 4.6 Trace Navigation Path (Element triggers chain)

```cypher
MATCH path = (start:Element {nkg_id: $start_nkg_id})-[:TRIGGERS*1..5]->(end)
RETURN [n IN nodes(path) | COALESCE(n.nkg_id, n.id)] AS path_ids,
       length(path) AS depth
ORDER BY depth
LIMIT 10
```

---

## 5. Data Statistics

| Metric | Value |
|:-------|------:|
| Total pages | 60 (47 with elements, 13 stub/target-only pages) |
| Total elements | 4 365 |
| Total CONTAINS edges | 4 365 |
| Total TRIGGERS edges | 557 |
| Orphan elements | 0 |
| Embedding coverage | 100% |
| Embedding dimensions | 1024 |
| Embedding model | `qwen3-embedding:8b` |

---

## 6. Embedding Details

### Document Embedding (offline, during data prep)
```
Instruct: Represent a UI element in a web application so that it can be
retrieved when a user describes their navigation intent or the action
they want to perform.
Document: Halaman: {page_title} ({page_id})
Elemen: {type} [{id}]
Fungsi: {desc}
```

### Query Embedding (runtime, by the agent)
```
Instruct: Given a user's navigation intent or action description, find
the most relevant UI element in the web application that the user wants
to interact with.
Query: {user_message}
```

### Embedding API
- **Model:** `qwen3-embedding:8b`
- **Endpoint:** `POST {OLLAMA_PROXY_URL}/api/embeddings`
- **Auth Header:** `X-API-Token: {OLLAMA_PROXY_TOKEN}`
- **Payload:** `{"model": "qwen3-embedding:8b", "prompt": "<instruction+text>"}`
- **Response:** `{"embedding": [float, ...]}`
