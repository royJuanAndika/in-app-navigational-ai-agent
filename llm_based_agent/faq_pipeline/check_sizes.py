import sys
from pathlib import Path
import dotenv

BASE_DIR = Path.cwd()
sys.path.append(str(BASE_DIR / "src"))
sys.path.append(str(BASE_DIR))
dotenv.load_dotenv(BASE_DIR / ".env")

from nkg_agent.core.graph_db import get_driver, close_driver

def check():
    driver = get_driver()
    with driver.session() as s:
        res = s.run("MATCH (i:Intent) WHERE i.embedding IS NOT NULL RETURN size(i.embedding) as size LIMIT 1")
        record = res.single()
        if record:
            print(f"Intent embedding size: {record['size']}")
        else:
            print("No intent embeddings found.")
            
        res = s.run("MATCH (e:Element) WHERE e.embedding IS NOT NULL RETURN size(e.embedding) as size LIMIT 1")
        record = res.single()
        if record:
            print(f"Element embedding size: {record['size']}")
        else:
            print("No element embeddings found.")

if __name__ == "__main__":
    check()
    close_driver()
