# 05 — Agent Tools

All 9 tools the In-App Navigational Agent can call. Each tool is a `@tool`-decorated function that LangGraph exposes to the LLM.

---

## Tool Design Principles

1. **Clear docstrings** — The LLM reads these to decide which tool to call. They must be precise.
2. **String return** — Tools return formatted strings (not dicts). The LLM processes text.
3. **No side effects** — All tools are read-only queries against Neo4j.
4. **Graceful failures** — Return helpful messages when no results found (not empty strings).
5. **Bounded output** — Limit results to prevent flooding the LLM context window.

---

## Tool 1: `search_elements_by_intent`

### File: `tools/semantic_search.py`

### Purpose
Find UI elements by semantic similarity to the user's natural language intent. This is the **primary discovery tool** — the agent uses it first to find relevant elements.

### Signature
```python
@tool
def search_elements_by_intent(query: str) -> str:
    """Search for UI elements that match the user's navigation intent
    using semantic vector similarity. Use this tool when the user
    describes what they want to do in natural language.

    Args:
        query: The user's intent or action description in natural language.
               Examples: "tambah karyawan baru", "lihat laporan absensi",
               "ubah profil perusahaan"

    Returns:
        A formatted list of the top matching UI elements with their
        page location, description, CSS selector, and relevance score.
    """
```

### Implementation Flow
1. Call `llm.get_query_embedding(query)` → 1024-d vector
2. Call `graph_db.vector_search(embedding, top_n=5)` → results
3. Format results as readable text

### Output Format
```
Found 5 matching elements:

1. [Score: 0.856] /customer/employee/btn_add
   Page: /customer/employee
   Type: button
   Description: Tombol untuk menambahkan karyawan baru
   Selector: #btn_add
   Text: Tambah Karyawan

2. [Score: 0.821] /customer/employee/form_add_employee
   Page: /customer/employee
   ...
```

---

## Tool 2: `get_page_content`

### File: `tools/page_content.py`

### Purpose
Retrieve all UI elements on a specific page. Used when the agent knows which page to look at.

### Signature
```python
@tool
def get_page_content(page_id: str) -> str:
    """Get all UI elements on a specific page of the application.
    Use this when you know the page path and want to see what
    interactive elements are available on that page.

    Args:
        page_id: The page path/route. Must be an exact path like
                 "/customer/employee" or "/customer/dashboard".
                 Use the find_page tool first if you only have a keyword.
    """
```

### Truncation Strategy
Pages like `/customer/employee` have 720 elements. Strategy:
- Show first 50 elements, grouped by type
- Mention total count so the agent knows there's more
- Agent can use `search_elements_by_intent` or `search_elements_by_text` to narrow down

---

## Tool 3: `get_element_details`

### File: `tools/element_details.py`

### Purpose
Get full details about a specific element AND what happens when you interact with it (triggers).

### Signature
```python
@tool
def get_element_details(nkg_id: str) -> str:
    """Get detailed information about a specific UI element,
    including what it triggers when clicked/interacted with.

    Args:
        nkg_id: The unique NKG identifier of the element.
                Format: "{page_id}/{element_id}"
                Example: "/customer/employee/btn_add"
    """
```

### Output includes
- Element properties (type, desc, selector, text)
- List of triggered targets (elements or pages)

---

---

## Tool 4: `find_trigger_prerequisites`

### File: `tools/find_trigger_prerequisites.py`

### Purpose
Find elements that must be interacted with **before** a target element is visible (e.g., modal, dropdown, expandable section). This enforces prerequisite clicks before guiding users to hidden UI.

### Signature
```python
@tool
def find_trigger_prerequisites(nkg_id: str) -> str:
    """Find elements that TRIGGER the given element (backward lookup).

    Args:
        nkg_id: The unique NKG identifier of the target element.
               Example: "/customer/employee/add_employee_"
    """
```

### Output includes
- Trigger elements (nkg_id, page, type, selector, text)

---

## Tool 5: `find_page`

### File: `tools/find_page.py`

### Purpose
Search for pages by title or URL keyword.

### Signature
```python
@tool
def find_page(search_term: str) -> str:
    """Search for a page by its title or URL path keyword.
    Use this when the user mentions a page or section name.

    Args:
        search_term: A keyword to search in page titles and paths.
                     Examples: "karyawan", "absensi", "dashboard"
    """
```

---

## Tool 6: `search_elements_by_text` (Fuzzy / Levenshtein)

### File: `tools/text_search.py`

### Purpose
Find elements by their visible inner text using **fuzzy matching**. This is critical because the LLM (or the user) may not type the exact text — a slight typo or abbreviation should still find the right element.

### Why Fuzzy Instead of Exact Match?

| User types | Exact `CONTAINS` result | Fuzzy result |
|:-----------|:------------------------|:-------------|
| `"Tamb Karywan"` | ❌ Not found | ✅ `"Tambah Karyawan"` (score: 85) |
| `"tambah karyawan"` | ✅ Found | ✅ Found (score: 100) |
| `"Ekspor Data"` | ❌ Not found (actual: `"Ekspor"`) | ✅ `"Ekspor"` (score: 75) |
| `"Pengaturan Profit"` | ❌ (actual: `"Profil"`) | ✅ `"Profil"` (score: 83) |

### Implementation Strategy
1. Fetch candidate elements from Neo4j (either all on a page, or filter with loose `CONTAINS`)
2. Use `rapidfuzz.fuzz.partial_ratio` or `token_sort_ratio` to score each candidate
3. Return top matches sorted by fuzzy score
4. Threshold: only return matches with score ≥ 60

### Signature
```python
@tool
def search_elements_by_text(text: str, page_id: str | None = None) -> str:
    """Search for UI elements by their visible text content using
    fuzzy matching. Use this when the user mentions specific button
    labels, menu items, or text they see on screen.
    
    The search is tolerant of typos and partial matches.

    Args:
        text: The visible text to search for (fuzzy match).
              Examples: "Tambah Karyawan", "Simpan", "Ekspor"
        page_id: Optional. Limit search to a specific page.
                 If not provided, searches all pages.
    """
```

### Dependency
```
rapidfuzz >= 3.0    # Much faster than thefuzz, pure C implementation
```

---

---

## Tool 7: `get_form_fields_on_page`

### File: `tools/form_fields.py`

### Purpose
Return input/select/textarea elements on a page to provide field-by-field form guidance.

### Signature
```python
@tool
def get_form_fields_on_page(page_id: str) -> str:
    """Get form fields (input/select/textarea) on a specific page.

    Args:
        page_id: The page path/route. Must be an exact path like
                 "/customer/employee".
    """
```

---

## Tool 8: `get_container_content`

### File: `tools/container_content.py`

### Purpose
Return elements inside a container (modal/section/dropdown) using recursive `CONTAINS` traversal.

### Signature
```python
@tool
def get_container_content(nkg_id: str) -> str:
    """Get elements contained by a page or element container.

    Args:
        nkg_id: The unique NKG identifier for a page or container element.
    """
```

---

## Tool 9: `execute_cypher_read_query` (Last Resort)

### File: `tools/cypher_query.py`

### Purpose
Execute a **read-only** Cypher query against Neo4j. This is the **last resort** when the other 8 tools cannot answer the question.

### Safety Guardrails
1. **Read-only transaction** — uses `session.execute_read()`
2. **Query validation** — rejects any query containing write keywords:
   `CREATE`, `DELETE`, `SET`, `MERGE`, `REMOVE`, `DETACH`, `DROP`
3. **Result limit** — appends `LIMIT 20` if no LIMIT clause is present
4. **System prompt** — explicitly tells the LLM this is a last resort

### Signature
```python
@tool
def execute_cypher_read_query(query: str) -> str:
    """Execute a read-only Cypher query against the Neo4j knowledge graph.
    
    ⚠️ LAST RESORT: Only use this tool when the other tools
    (search_elements_by_intent, get_page_content, get_element_details,
    find_page, search_elements_by_text) cannot answer the question.
    
    The query MUST be read-only (MATCH/RETURN only, no CREATE/DELETE/SET).

    Args:
        query: A valid read-only Cypher query.
               Example: "MATCH (p:Page) RETURN p.id, p.title ORDER BY p.title"
    """
```

### Implementation
```python
FORBIDDEN_KEYWORDS = {"CREATE", "DELETE", "SET", "MERGE", "REMOVE", "DETACH", "DROP"}

def execute_cypher_read_query(query: str) -> str:
    # 1. Validate — reject write operations
    upper_query = query.upper()
    for kw in FORBIDDEN_KEYWORDS:
        if kw in upper_query:
            return f"Error: Query rejected — '{kw}' is not allowed. This tool is read-only."
    
    # 2. Add LIMIT if missing
    if "LIMIT" not in upper_query:
        query = query.rstrip().rstrip(";") + " LIMIT 20"
    
    # 3. Execute in read-only transaction
    driver = get_driver()
    with driver.session() as session:
        result = session.execute_read(lambda tx: tx.run(query).data())
    
    # 4. Format results
    if not result:
        return "Query returned no results."
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)
```

---

## Tool Registration

### `tools/__init__.py`
```python
from .semantic_search import search_elements_by_intent
from .page_content import get_page_content
from .element_details import get_element_details
from .find_page import find_page
from .text_search import search_elements_by_text
from .cypher_query import execute_cypher_read_query

ALL_TOOLS = [
    search_elements_by_intent,
    get_page_content,
    get_element_details,
    find_page,
    search_elements_by_text,
    execute_cypher_read_query,
]
```

---

## Future Tool: `get_workflow_by_intent`

When `Intent` and `HAS_STEP` nodes are added:

```python
@tool
def get_workflow_by_intent(intent_query: str) -> str:
    """Find a step-by-step workflow for a user intent.
    Returns an ordered sequence of UI elements to interact with."""
```

**No existing code needs to change** — just add the file and register it in `ALL_TOOLS`.
