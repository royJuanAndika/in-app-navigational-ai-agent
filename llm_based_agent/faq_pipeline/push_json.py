import argparse
import json
import logging
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR / "src"))

from nkg_agent.core.graph_db import close_driver
from faq_pipeline.models import IntentWrite
from faq_pipeline.phases.phase5_write import push_to_neo4j

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("push_json")

def main():
    parser = argparse.ArgumentParser(description="Push pre-processed FAQ Intents JSON directly to Neo4j")
    parser.add_argument("file_path", type=str, help="Path to final_intents.json file")
    args = parser.parse_args()
    
    file_path = Path(args.file_path).resolve()
    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return
        
    logger.info(f"Loading intents from: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if not isinstance(data, list):
        data = [data]
        
    intents = [IntentWrite.model_validate(i) for i in data]
    logger.info(f"Loaded {len(intents)} intents.")
    
    success_count = 0
    for intent in intents:
        success = push_to_neo4j(intent)
        if success:
            success_count += 1
            
    logger.info(f"Finished! Successfully pushed {success_count}/{len(intents)} intents to Neo4j.")
    close_driver()

if __name__ == "__main__":
    main()
