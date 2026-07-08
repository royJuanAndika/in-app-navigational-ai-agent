import sys
from pathlib import Path
import dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR / "src"))
sys.path.append(str(BASE_DIR))

dotenv.load_dotenv(BASE_DIR / ".env")

from nkg_agent.core.graph_db import get_driver, close_driver

def count_intents():
    driver = get_driver()
    with driver.session() as session:
        result = session.run("MATCH (i:Intent) RETURN count(i) AS count")
        count = result.single()["count"]
        print(f"Total :Intent nodes: {count}")
        
        result = session.run("MATCH (:Intent)-[r:HAS_STEP]->() RETURN count(r) AS count")
        count = result.single()["count"]
        print(f"Total :HAS_STEP relationships: {count}")
        
        result = session.run("MATCH (i:Intent) RETURN i.id LIMIT 5")
        ids = [record["i.id"] for record in result]
        print(f"Sample Intent IDs: {ids}")

if __name__ == "__main__":
    count_intents()
    close_driver()
