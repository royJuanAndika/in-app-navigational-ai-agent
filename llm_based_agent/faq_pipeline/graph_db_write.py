import logging
from nkg_agent.core.graph_db import get_driver
from .models import IntentWrite

logger = logging.getLogger(__name__)

def ensure_schema() -> None:
    """Create Intent unique constraint + vector index if not exists."""
    driver = get_driver()
    
    # 1. Create constraint for Intent ID
    constraint_query = """
    CREATE CONSTRAINT intent_id IF NOT EXISTS
    FOR (i:Intent) REQUIRE i.id IS UNIQUE
    """
    
    # 2. Create vector index for Intent embedding
    # Note: Using backticks for vector.dimensions as per 09_faq_ingestion_pipeline.md
    index_query = """
    CREATE VECTOR INDEX intent_embedding_idx IF NOT EXISTS
    FOR (i:Intent) ON (i.embedding)
    OPTIONS { indexConfig: {
        `vector.dimensions`: 4096,
        `vector.similarity_function`: 'cosine'
    }}
    """
    
    with driver.session() as session:
        session.run(constraint_query)
        logger.info("Ensured Intent unique constraint exists.")
        session.run(index_query)
        logger.info("Ensured Intent vector index exists.")

def write_intent(intent: IntentWrite) -> None:
    """
    Atomic transaction per Intent:
    1. MERGE (:Intent {id}) SET all properties (excluding embedding + resolved_steps)
    2. DELETE existing HAS_STEP relationships, then recreate from resolved_steps
    3. DELETE existing ABOUT_PAGE relationships, then recreate from page_ids
    Raises ValueError if any nkg_id in resolved_steps does not resolve to a real Element.
    """
    driver = get_driver()
    
    # Prepare properties for Intent node (including embedding)
    intent_props = {
        "label": intent.label,
        "type": intent.intent_type,
        "faq_id": intent.faq_id,
        "category": intent.category,
        "subcategory": intent.subcategory,
        "content": intent.content,
        "possible_questions": intent.possible_questions,
        "embedding": intent.embedding
    }
    
    # Cypher for Intent node and relationships
    cypher_intent = """
    MERGE (i:Intent {id: $intent_id})
    SET i += $props
    """
    
    cypher_steps = """
    MATCH (i:Intent {id: $intent_id})
    OPTIONAL MATCH (i)-[r:HAS_STEP]->()
    DELETE r
    WITH DISTINCT i
    UNWIND $steps AS step
    MATCH (e:Element {nkg_id: step.nkg_id})
    MERGE (i)-[:HAS_STEP {order: step.order, action: step.action}]->(e)
    """
    
    cypher_pages = """
    MATCH (i:Intent {id: $intent_id})
    OPTIONAL MATCH (i)-[r:ABOUT_PAGE]->()
    DELETE r
    WITH DISTINCT i
    UNWIND $page_ids AS pid
    MATCH (p:Page {id: pid})
    MERGE (i)-[:ABOUT_PAGE]->(p)
    """

    with driver.session() as session:
        def _write_tx(tx):
            # 1. Write Intent node
            tx.run(cypher_intent, intent_id=intent.intent_id, props=intent_props)
            
            # 2. Recreate HAS_STEP relationships if there are steps
            if intent.resolved_steps:
                # First check if all elements exist
                for step in intent.resolved_steps:
                    res = tx.run("MATCH (e:Element {nkg_id: $nkg_id}) RETURN e", nkg_id=step.nkg_id)
                    if not res.peek():
                        raise ValueError(f"nkg_id '{step.nkg_id}' does not resolve to a real Element.")
                
                steps_data = [
                    {"nkg_id": s.nkg_id, "order": s.order, "action": s.action}
                    for s in intent.resolved_steps
                ]
                tx.run(cypher_steps, intent_id=intent.intent_id, steps=steps_data)
            else:
                # If no steps, just clear existing ones
                tx.run("MATCH (i:Intent {id: $intent_id})-[r:HAS_STEP]->() DELETE r", intent_id=intent.intent_id)

            # 3. Recreate ABOUT_PAGE relationships
            if intent.page_ids:
                tx.run(cypher_pages, intent_id=intent.intent_id, page_ids=intent.page_ids)
            else:
                # If no pages, just clear existing ones
                tx.run("MATCH (i:Intent {id: $intent_id})-[r:ABOUT_PAGE]->() DELETE r", intent_id=intent.intent_id)

        session.execute_write(_write_tx)
        logger.info(f"Successfully wrote Intent '{intent.intent_id}' to Neo4j.")

def write_intent_embedding(intent_id: str, embedding: list[float]) -> None:
    """SET i.embedding on an already-written Intent node."""
    driver = get_driver()
    query = """
    MATCH (i:Intent {id: $intent_id})
    SET i.embedding = $embedding
    """
    with driver.session() as session:
        session.run(query, intent_id=intent_id, embedding=embedding)
        logger.info(f"Updated embedding for Intent '{intent_id}'.")
