import sys
from pathlib import Path
import dotenv

BASE_DIR = Path.cwd()
sys.path.append(str(BASE_DIR / "src"))
sys.path.append(str(BASE_DIR))
dotenv.load_dotenv(BASE_DIR / ".env")

from nkg_agent.core.graph_db import get_driver, close_driver
from faq_pipeline.graph_db_write import ensure_schema

def repair():
    driver = get_driver()
    with driver.session() as s:
        print("Dropping existing vector indexes to repair dimensions...")
        s.run("DROP INDEX intent_embedding_idx IF EXISTS")
        s.run("DROP INDEX element_embedding_idx IF EXISTS")
        
    print("Recreating indexes with correct dimensions (4096)...")
    # This will recreate intent_embedding_idx with 4096 (since we updated graph_db_write.py)
    ensure_schema()
    
    # We also need to recreate element_embedding_idx with 4096
    with driver.session() as s:
        s.run("""
        CREATE VECTOR INDEX element_embedding_idx IF NOT EXISTS
        FOR (e:Element) ON (e.embedding)
        OPTIONS { indexConfig: {
            `vector.dimensions`: 4096,
            `vector.similarity_function`: 'cosine'
        }}
        """)
        print("Ensured element_embedding_idx exists with 4096 dimensions.")
        
    print("Repair complete. Neo4j will now re-index the nodes in the background.")

if __name__ == "__main__":
    repair()
    close_driver()
