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
        print("Checking VECTOR indexes...")
        res = s.run("SHOW INDEXES")
        for rec in res:
            # rec might be a dict or a record object
            data = rec.data() if hasattr(rec, 'data') else dict(rec)
            if data.get('type') == 'VECTOR' or 'vector' in str(data.get('indexConfig', '')).lower():
                name = data.get('name')
                labels = data.get('labelsOrTypes')
                properties = data.get('properties')
                options = data.get('options', {})
                print(f"Index Name: {name}")
                print(f"  Labels: {labels}")
                print(f"  Properties: {properties}")
                print(f"  Options: {options}")

if __name__ == "__main__":
    check()
    close_driver()
