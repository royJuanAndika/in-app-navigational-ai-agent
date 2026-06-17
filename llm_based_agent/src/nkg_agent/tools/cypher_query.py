"""Last-resort: execute an arbitrary read-only Cypher query."""

import json

from langchain_core.tools import tool

from ..core.graph_db import execute_read_query


# Keywords that indicate a write operation — always reject these.
_FORBIDDEN_KEYWORDS = frozenset({
    "CREATE", "DELETE", "SET", "MERGE", "REMOVE", "DETACH", "DROP",
})


@tool
def execute_cypher_read_query(query: str) -> str:
    """Execute a read-only Cypher query against the Neo4j knowledge graph.

    ⚠️ LAST RESORT — only use this when the other tools cannot answer the question.

    The query MUST be read-only (MATCH/RETURN only).

    DATABASE SCHEMA (NKG):
    - Nodes:
      - (p:Page): Properties: id (url path, e.g., '/customer/device'), title, desc
      - (e:Element): Properties: nkg_id (globally unique), id (DOM id), page_id, type (e.g., 'input', 'button', 'modal', 'select'), text, desc, selector
      - (i:Intent): Properties: id, label, type, content, faq_id, category, subcategory, possible_questions
    - Relationships:
      - (p:Page)-[:CONTAINS]->(e:Element)
      - (e:Element)-[:TRIGGERS]->(target:Element OR target:Page)
      - (i:Intent)-[:HAS_STEP {order, action}]->(e:Element)
      - (i:Intent)-[:ABOUT_PAGE]->(p:Page)

    DO NOT hallucinate relationship types like BELONGS_TO. Use exactly the schema above.

    Args:
        query: A valid read-only Cypher query.
               Example: "MATCH (p:Page {id: '/customer/device'})-[:CONTAINS]->(e:Element) RETURN e.id, e.type LIMIT 20"
    """
    # 1. Validate — reject any write operations
    upper_query = query.upper()
    for kw in _FORBIDDEN_KEYWORDS:
        # Check as a whole word (avoid matching "ASSET" for "SET")
        if f" {kw} " in f" {upper_query} " or upper_query.startswith(f"{kw} "):
            return (
                f"Error: query rejected — '{kw}' is not allowed. "
                "This tool only executes read-only queries (MATCH/RETURN)."
            )

    # 2. Safety limit — append LIMIT if missing
    if "LIMIT" not in upper_query:
        query = query.rstrip().rstrip(";") + " LIMIT 20"

    # 3. Execute
    try:
        results = execute_read_query(query)
    except Exception as exc:
        return f"Cypher execution error: {exc}"

    # 4. Format
    if not results:
        return "Query returned no results."

    return json.dumps(results, indent=2, ensure_ascii=False, default=str)
