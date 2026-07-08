import logging
from faq_pipeline.models import IntentWrite
from faq_pipeline.graph_db_write import write_intent, ensure_schema

logger = logging.getLogger(__name__)

def push_to_neo4j(intent: IntentWrite) -> bool:
    """
    Phase 5: Write the Intent, steps, and relationships to Neo4j.
    Returns True if successful, False otherwise.
    """
    logger.info(f"Phase 5: Writing {intent.intent_id} to Neo4j")
    
    try:
        # Ensure schema exists (constraints/indexes)
        ensure_schema()
        
        # Write intent
        write_intent(intent)
        return True
    except Exception as e:
        logger.error(f"  Failed to write {intent.intent_id} to Neo4j: {e}")
        return False
