"""
Neo4j data-access layer.

Every Cypher query lives here — tool modules never contain raw Cypher.
All public functions return plain ``list[dict]`` or ``dict | None``.
"""

import json
import logging
from typing import Any, Optional, Union

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired

from .config import get_settings

logger = logging.getLogger(__name__)

# ── Driver management ────────────────────────────────────────────────────

_driver = None


def get_driver():
    """Return a cached Neo4j driver (created & verified on first call)."""
    global _driver
    if _driver is None:
        s = get_settings()
        _driver = GraphDatabase.driver(
            s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password)
        )
        _driver.verify_connectivity()
        logger.info("Neo4j connected: %s", s.neo4j_uri)
    return _driver


def close_driver() -> None:
    """Close the driver — call on application shutdown."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
        logger.info("Neo4j driver closed.")


def _run_read(query: str, **params) -> list[dict]:
    """Execute a read-only query and return results as list of dicts.

    Handles reconnection on ``ServiceUnavailable`` / ``SessionExpired``.
    """
    driver = get_driver()
    try:
        with driver.session() as session:
            return session.execute_read(lambda tx: tx.run(query, **params).data())
    except (ServiceUnavailable, SessionExpired):
        logger.warning("Neo4j session lost — reconnecting.")
        global _driver
        _driver = None
        driver = get_driver()
        with driver.session() as session:
            return session.execute_read(lambda tx: tx.run(query, **params).data())


def _run_write(query: str, **params) -> list[dict]:
    """Execute a write-only query and return results as list of dicts.

    Handles reconnection on ``ServiceUnavailable`` / ``SessionExpired``.
    """
    driver = get_driver()
    try:
        with driver.session() as session:
            return session.execute_write(lambda tx: tx.run(query, **params).data())
    except (ServiceUnavailable, SessionExpired):
        logger.warning("Neo4j session lost (write) — reconnecting.")
        global _driver
        _driver = None
        driver = get_driver()
        with driver.session() as session:
            return session.execute_write(lambda tx: tx.run(query, **params).data())


# ── Public query functions ───────────────────────────────────────────────


def vector_search(embedding: list[float], top_n: int = 5) -> list[dict]:
    """Semantic search via the HNSW vector index on Element.embedding."""
    query = """
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
    """
    return _run_read(query, vector=embedding, top_n=top_n)


def vector_search_intents(embedding: list[float], top_n: int = 3) -> list[dict]:
    """Semantic search via the HNSW vector index on Intent.embedding.

    Returns top_n results ordered by score, each including ``has_steps``
    and ``step_count`` so the caller can decide which intent to expand.
    """
    query = """
    CALL db.index.vector.queryNodes('intent_embedding_idx', $top_n, $vector)
    YIELD node, score
    OPTIONAL MATCH (node)-[:HAS_STEP]->()
    WITH node, score, count(*) AS step_count
    RETURN
        node.id                 AS intent_id,
        node.label              AS label,
        node.type               AS intent_type,
        node.content            AS content,
        node.possible_questions AS possible_questions,
        step_count              AS step_count,
        step_count > 0          AS has_steps,
        score
    ORDER BY score DESC
    """
    return _run_read(query, vector=embedding, top_n=top_n)


def get_intent_steps(intent_id: str) -> list[dict]:
    """Return the ordered HAS_STEP sequence for a procedural Intent."""
    query = """
    MATCH (i:Intent {id: $intent_id})-[r:HAS_STEP]->(e:Element)
    RETURN
        r.order     AS order,
        r.action    AS action,
        e.nkg_id    AS nkg_id,
        e.selector  AS selector,
        e.text      AS text,
        e.desc      AS description,
        e.page_id   AS page_id
    ORDER BY r.order
    """
    return _run_read(query, intent_id=intent_id)


def get_intents_for_page(page_id: str) -> list[dict]:
    """Return all Intents that are ABOUT_PAGE for the given page."""
    query = """
    MATCH (i:Intent)-[:ABOUT_PAGE]->(p:Page {id: $page_id})
    RETURN
        i.id                 AS intent_id,
        i.label              AS label,
        i.type               AS intent_type,
        i.possible_questions AS possible_questions
    ORDER BY i.type, i.label
    """
    return _run_read(query, page_id=page_id)


def get_page_elements(page_id: str) -> list[dict]:
    """Return all Element nodes contained by the given page."""
    query = """
    MATCH (p:Page {id: $page_id})-[:CONTAINS]->(e:Element)
    RETURN
        e.nkg_id  AS nkg_id,
        e.id       AS element_id,
        e.type     AS type,
        e.desc     AS description,
        e.selector AS selector,
        e.text     AS text
    ORDER BY e.type, e.id
    """
    return _run_read(query, page_id=page_id)


def get_page_elements_with_hierarchy(page_id: str) -> list[dict]:
    """Return all Element nodes on a page with parent and trigger info.

    Used by the FAQ ingestion pipeline (Phase 3) to allow the LLM to
    reconstruct the UI hierarchy and insert missing intermediate steps.
    """
    query = """
    MATCH (p:Page {id: $page_id})-[:CONTAINS*1..5]->(e:Element)
    OPTIONAL MATCH (parent)-[:CONTAINS]->(e)
    WHERE parent:Page OR parent:Element
    OPTIONAL MATCH (e)-[:TRIGGERS]->(target)
    RETURN DISTINCT
        e.nkg_id  AS nkg_id,
        e.id       AS id,
        e.type     AS type,
        e.text     AS text,
        e.desc     AS desc,
        e.selector AS selector,
        COALESCE(parent.nkg_id, parent.id) AS parent_nkg_id,
        COALESCE(target.nkg_id, target.id) AS triggers_nkg_id
    """
    return _run_read(query, page_id=page_id)


def get_container_elements(nkg_id: str) -> list[dict]:
    """Return all Element nodes contained by a page or element container.

    This is useful for modals, sections, and expandable areas where the visible
    fields live inside a container element rather than directly on the page.
    """
    query = """
    MATCH (parent)
    WHERE parent.id = $nkg_id OR parent.nkg_id = $nkg_id
    MATCH (parent)-[:CONTAINS*1..5]->(e:Element)
    WITH DISTINCT e
    RETURN
        e.nkg_id   AS nkg_id,
        e.id       AS element_id,
        e.page_id  AS page_id,
        e.type     AS type,
        e.desc     AS description,
        e.selector AS selector,
        e.text     AS text
    ORDER BY e.type, e.id
    """
    return _run_read(query, nkg_id=nkg_id)


def get_form_fields(page_id: str) -> list[dict]:
    """Return the primary form controls on a page.

    This focuses on actionable inputs such as input/select/textarea elements,
    as well as triggers like buttons and tabs that manage form flow.
    """
    query = """
    MATCH (p:Page {id: $page_id})-[:CONTAINS]->(e:Element)
    WHERE toLower(e.type) IN ['input', 'select', 'textarea', 'button', 'tab']
    RETURN
        e.nkg_id   AS nkg_id,
        e.id       AS element_id,
        e.page_id  AS page_id,
        e.type     AS type,
        e.desc     AS description,
        e.selector AS selector,
        e.text     AS text
    ORDER BY CASE e.type
        WHEN 'tab' THEN 1
        WHEN 'button' THEN 2
        WHEN 'input' THEN 3
        WHEN 'select' THEN 4
        WHEN 'textarea' THEN 5
        ELSE 6
    END, e.id
    """
    return _run_read(query, page_id=page_id)


def get_page_info(page_id: str) -> Optional[dict]:
    """Return basic info for a single page, or None."""
    query = """
    MATCH (p:Page {id: $page_id})
    OPTIONAL MATCH (p)-[:CONTAINS]->(e:Element)
    RETURN p.id AS page_id, p.title AS title, p.desc AS description,
           count(e) AS element_count
    """
    rows = _run_read(query, page_id=page_id)
    return rows[0] if rows else None


def get_element_info(nkg_id: str) -> Optional[dict]:
    """Return element properties + its TRIGGERS targets."""
    query = """
    MATCH (e:Element {nkg_id: $nkg_id})
    OPTIONAL MATCH (e)-[:TRIGGERS]->(target)
    WITH e, collect(CASE WHEN target IS NOT NULL THEN {
        target_type:     labels(target)[0],
        target_id:       COALESCE(target.nkg_id, target.id),
        target_title:    target.title,
        target_desc:     COALESCE(target.desc, ''),
        target_selector: COALESCE(target.selector, '')
    } ELSE null END) AS raw_triggers
    RETURN
        e.nkg_id   AS nkg_id,
        e.id        AS element_id,
        e.page_id   AS page_id,
        e.type      AS type,
        e.desc      AS description,
        e.selector  AS selector,
        e.text      AS text,
        [t IN raw_triggers WHERE t IS NOT NULL] AS triggers
    """
    rows = _run_read(query, nkg_id=nkg_id)
    return rows[0] if rows else None


def get_incoming_triggers(nkg_id: str) -> list[dict]:
    """Find elements that TRIGGER the given element.

    Includes both direct triggers and heuristic triggers (e.g., if the element
    is inside a modal/tab that has a trigger).
    """
    query = """
    MATCH (e:Element {nkg_id: $nkg_id})
    
    // 1. Direct triggers
    OPTIONAL MATCH (s1:Element)-[:TRIGGERS]->(e)
    
    // 2. Heuristic triggers (parents/containers)
    // We look for elements on the same page that are modals/tabs/sections
    // and share a logical naming relationship with our target element.
    OPTIONAL MATCH (container:Element {page_id: e.page_id})
    WHERE container.type IN ['modal', 'tab', 'section', 'expandable section']
      AND container.id <> e.id
      AND (
          (e.id STARTS WITH 'add' AND container.id STARTS WITH 'add') OR
          (e.id STARTS WITH 'edit' AND container.id STARTS WITH 'edit') OR
          (e.id CONTAINS container.id)
      )
    OPTIONAL MATCH (s2:Element)-[:TRIGGERS]->(container)
    
    WITH collect(DISTINCT s1) + collect(DISTINCT s2) as all_sources
    UNWIND all_sources as s
    WITH s WHERE s IS NOT NULL
    RETURN DISTINCT
        s.nkg_id   AS nkg_id,
        s.id       AS element_id,
        s.page_id  AS page_id,
        s.type     AS type,
        s.desc     AS description,
        s.selector AS selector,
        s.text     AS text
    """
    return _run_read(query, nkg_id=nkg_id)


def find_pages(search_term: str) -> list[dict]:
    """Fuzzy search pages by title or URL path (case-insensitive CONTAINS)."""
    query = """
    MATCH (p:Page)
    WHERE toLower(p.title) CONTAINS toLower($term)
       OR toLower(p.id) CONTAINS toLower($term)
    OPTIONAL MATCH (p)-[:CONTAINS]->(e:Element)
    RETURN p.id AS page_id, p.title AS title, p.desc AS description,
           count(e) AS element_count
    ORDER BY count(e) DESC
    """
    return _run_read(query, term=search_term)


def text_search_elements(
    search_text: str,
    limit: int = 200,
    page_id: Optional[str] = None,
) -> list[dict]:
    """Broad text search — returns candidates for fuzzy ranking in Python.

    Uses a loose CONTAINS to cast a wide net; the caller (text_search tool)
    applies Levenshtein scoring to rank and filter.
    """
    # Split the search text into individual words for broader matching
    words = search_text.strip().split()
    if not words:
        return []

    # Use the shortest word (≥ 2 chars) for the CONTAINS filter
    # This casts the widest net for fuzzy matching later
    filter_word = min((w for w in words if len(w) >= 2), key=len, default=words[0])

    if page_id:
        query = """
        MATCH (p:Page {id: $page_id})-[:CONTAINS]->(e:Element)
        WHERE e.text IS NOT NULL AND e.text <> ''
          AND toLower(e.text) CONTAINS toLower($filter_word)
        RETURN
            e.nkg_id   AS nkg_id,
            e.id        AS element_id,
            e.page_id   AS page_id,
            e.type      AS type,
            e.desc      AS description,
            e.selector  AS selector,
            e.text      AS text,
            p.title     AS page_title
        LIMIT $limit
        """
        return _run_read(
            query,
            filter_word=filter_word,
            limit=limit,
            page_id=page_id,
        )

    query = """
    MATCH (p:Page)-[:CONTAINS]->(e:Element)
    WHERE e.text IS NOT NULL AND e.text <> ''
      AND toLower(e.text) CONTAINS toLower($filter_word)
    RETURN
        e.nkg_id   AS nkg_id,
        e.id        AS element_id,
        e.page_id   AS page_id,
        e.type      AS type,
        e.desc      AS description,
        e.selector  AS selector,
        e.text      AS text,
        p.title     AS page_title
    LIMIT $limit
    """
    return _run_read(query, filter_word=filter_word, limit=limit)


def get_all_element_texts(
    page_id: Optional[str] = None,
    limit: int = 500,
) -> list[dict]:
    """Return nkg_id + text for all elements (optionally filtered by page).

    Used by the fuzzy text search tool when the CONTAINS filter misses.
    """
    if page_id:
        query = """
        MATCH (p:Page {id: $page_id})-[:CONTAINS]->(e:Element)
        WHERE e.text IS NOT NULL AND e.text <> ''
        RETURN e.nkg_id AS nkg_id, e.text AS text, e.selector AS selector,
               e.type AS type, e.desc AS description, e.page_id AS page_id
        LIMIT $limit
        """
        return _run_read(query, page_id=page_id, limit=limit)

    query = """
    MATCH (e:Element)
    WHERE e.text IS NOT NULL AND e.text <> ''
    RETURN e.nkg_id AS nkg_id, e.text AS text, e.selector AS selector,
           e.type AS type, e.desc AS description, e.page_id AS page_id
    LIMIT $limit
    """
    return _run_read(query, limit=limit)


def execute_read_query(cypher: str) -> list[dict]:
    """Execute an arbitrary read-only Cypher query.

    The caller (cypher_query tool) is responsible for validating the query
    before passing it here.
    """
    return _run_read(cypher)


def enrich_guidance_steps(nkg_ids: list[str]) -> dict[str, dict]:
    """Batch-resolve NKG element data for a list of nkg_ids.

    Given a list of ``nkg_id`` strings returned by the agent, fetches
    ``page_id``, ``selector``, and ``element_id`` (raw DOM id) for each one
    in a single round-trip to Neo4j.

    For ``nkg_id`` values that look like bare page paths (no element segment,
    e.g. ``/customer/employee``), the function falls back to a Page lookup so
    callers still get a ``page_url``.

    Args:
        nkg_ids: List of ``nkg_id`` strings from agent guidance steps.
                 ``None`` / empty entries are ignored.

    Returns:
        ``dict[nkg_id -> {page_url, selector, element_id}]``
        Missing/unresolvable IDs are absent from the returned dict.
    """
    if not nkg_ids:
        return {}

    # Split into "element nkg_ids" vs bare "page_ids" (no element segment)
    element_ids: list[str] = []
    page_ids: list[str] = []

    for nkg_id in nkg_ids:
        if not nkg_id:
            continue
        # A bare page path has no element segment and matches a known Page node.
        # Heuristic: if there's no sub-path after the second slash group, it's a Page.
        # We attempt element lookup first; fall back to page lookup if nothing found.
        element_ids.append(nkg_id)

    if not element_ids:
        return {}

    query = """
    UNWIND $nkg_ids AS nkg_id
    OPTIONAL MATCH (e:Element {nkg_id: nkg_id})
    OPTIONAL MATCH (p:Page   {id: nkg_id})
    RETURN
        nkg_id,
        COALESCE(e.page_id, p.id)       AS page_url,
        COALESCE(e.selector, '')        AS selector,
        COALESCE(e.id, '')              AS element_id
    """
    rows = _run_read(query, nkg_ids=element_ids)

    result: dict[str, dict] = {}
    for row in rows:
        nkg_id = row["nkg_id"]
        if row["page_url"]:  # skip rows where neither Element nor Page matched
            result[nkg_id] = {
                "page_url": row["page_url"],
                "selector": row["selector"] or None,
                "element_id": row["element_id"] or None,
            }

    logger.debug("enrich_guidance_steps: resolved %d / %d nkg_ids", len(result), len(element_ids))
    return result


def update_element_metadata(nkg_id: str, selector: str | None, element_id: str | None) -> bool:
    """Update the selector and ID of a specific Element node in Neo4j.

    Args:
        nkg_id:     The unique ID of the element node.
        selector:   The new CSS selector.
        element_id: The new DOM ID.

    Returns:
        True if the node was found and updated, False otherwise.
    """
    query = """
    MATCH (e:Element {nkg_id: $nkg_id})
    SET e.selector = $selector,
        e.id = $element_id
    RETURN count(e) AS updated
    """
    rows = _run_write(query, nkg_id=nkg_id, selector=selector, element_id=element_id)
    return bool(rows and rows[0]["updated"] > 0)
