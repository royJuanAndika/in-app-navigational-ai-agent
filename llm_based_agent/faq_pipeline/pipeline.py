import argparse
import json
import os
import logging
from typing import List, Dict, Any
from pathlib import Path

# Fix path to allow importing from src/
import sys
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR / "src"))

from nkg_agent.core.llm import init_llm, set_llm_mode
from nkg_agent.core.graph_db import find_pages, close_driver
from faq_pipeline.models import FAQEntry, Phase1Result, Phase2Result
from faq_pipeline.phases.phase1_classify import classify_faq
from faq_pipeline.phases.phase2_steps import extract_steps
from faq_pipeline.phases.phase3_match import match_elements
from faq_pipeline.phases.phase4_embed import generate_questions_and_embed
from faq_pipeline.phases.phase5_write import push_to_neo4j
from faq_pipeline.html_cleaner import clean_html
from faq_pipeline.models import IntentWrite, Phase3Result

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("faq_pipeline")

FAQ_FILE = BASE_DIR.parents[0] / "data_preprocessing_and_cleaning" / "scrape_faq" / "help_center_faq.json"
OUTPUT_DIR = BASE_DIR / "faq_pipeline" / "output"

def load_faqs(filepath: Path = FAQ_FILE) -> List[FAQEntry]:
    """Load all FAQs from the JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return [FAQEntry.model_validate(faq) for faq in data['faq']]

def save_json(data: Any, filename: str):
    """Save data to the output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filepath = OUTPUT_DIR / filename
    with open(filepath, 'w', encoding='utf-8') as f:
        if isinstance(data, list):
            # If it's a list of Pydantic models, convert them to dict
            json.dump([item.model_dump() if hasattr(item, 'model_dump') else item for item in data], f, indent=2, ensure_ascii=False)
        elif isinstance(data, dict):
            # Handle dict where values might be Pydantic models
            json.dump({k: (v.model_dump() if hasattr(v, 'model_dump') else v) for k, v in data.items()}, f, indent=2, ensure_ascii=False)
        else:
            json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved: {filepath}")

def main():
    parser = argparse.ArgumentParser(description="FAQ Ingestion Pipeline")
    parser.add_argument("--mode", choices=["proxy", "local"], default="proxy", help="Ollama mode")
    parser.add_argument("--dry-run", action="store_true", help="Stop before any LLM calls (Phase 0 only)")
    parser.add_argument("--push", action="store_true", help="Push results to Neo4j (Phase 5)")
    parser.add_argument("--faq-id", type=str, help="Process a single FAQ by faq_id")
    parser.add_argument("--resume", action="store_true", help="Skip FAQs already in final_intents.json")
    parser.add_argument("--manual", action="store_true", help="Manual Phase 3: Wait for user to provide JSON in manual_p3.json")
    parser.add_argument("--dump-manual", action="store_true", help="Generate prompt/result files for all FAQs in output/manual/")
    parser.add_argument("--load-manual", action="store_true", help="Load filled result files from output/manual/ and finish processing")
    parser.add_argument("--fast-p4", action="store_true", help="Skip LLM in Phase 4 (use FAQ title only)")
    parser.add_argument("--faq-file", type=str, help="Path to a custom FAQ JSON file")
    parser.add_argument("--output-dir", type=str, help="Custom output directory for pipeline results")
    
    args = parser.parse_args()
    
    global OUTPUT_DIR
    if args.output_dir:
        OUTPUT_DIR = Path(args.output_dir).resolve()
        logger.info(f"Using custom output directory: {OUTPUT_DIR}")
        
    faq_file_path = FAQ_FILE
    if args.faq_file:
        faq_file_path = Path(args.faq_file).resolve()
        logger.info(f"Using custom FAQ file: {faq_file_path}")
    
    # Initialize LLM mode
    set_llm_mode(args.mode)
    init_llm(args.mode)
    
    try:
        # 1. Load Data
        logger.info("Loading FAQs and Pages...")
        faqs = load_faqs(faq_file_path)
        if args.faq_id:
            faqs = [f for f in faqs if f.faq_id == args.faq_id]
            if not faqs:
                logger.error(f"FAQ with id {args.faq_id} not found.")
                return

        all_pages = find_pages("")
        logger.info(f"Loaded {len(faqs)} FAQs and {len(all_pages)} pages.")

        if args.dry_run:
            logger.info("Dry run enabled. Stopping before LLM calls.")
            return

        final_intents: List[IntentWrite] = []
        phase1_results: List[Phase1Result] = []
        phase2_results: Dict[str, Phase2Result] = {}
        phase3_results: Dict[str, Phase3Result] = {}

        # 1.5 Load existing results if resuming
        processed_faq_ids = set()
        if args.resume:
            final_intents_path = OUTPUT_DIR / "final_intents.json"
            if final_intents_path.exists():
                with open(final_intents_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Only consider an FAQ "processed" if it has a non-empty embedding
                    final_intents = [IntentWrite.model_validate(i) for i in data]
                    processed_faq_ids = {i.faq_id for i in final_intents if i.embedding}
                    logger.info(f"Resuming: Found {len(processed_faq_ids)} fully processed FAQs (with embeddings).")
                    
                    # Remove incomplete items from final_intents to avoid duplicates
                    final_intents = [i for i in final_intents if i.embedding]
            
            # Seed other intermediate results for consistency
            # But only for those that are truly "finished" (have embeddings)
            finished_intent_ids = {fi.intent_id for fi in final_intents}
            for filename, model, target in [
                ("phase1_results.json", Phase1Result, phase1_results),
            ]:
                path = OUTPUT_DIR / filename
                if path.exists():
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        target.extend([model.model_validate(i) for i in data if i.get('intent_id') in finished_intent_ids])

            # Seed dict-based results
            for filename, model, target in [
                ("phase2_results.json", Phase2Result, phase2_results),
                ("phase3_results.json", Phase3Result, phase3_results),
            ]:
                path = OUTPUT_DIR / filename
                if path.exists():
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for k, v in data.items():
                            if k in processed_faq_ids:
                                target[k] = model.model_validate(v)

        # 2. Orchestration Loop
        for i, faq in enumerate(faqs):
            # Check for manual file first if in load-manual mode
            result_file = None
            manual_result_exists = False
            if args.load_manual:
                manual_dir = OUTPUT_DIR / "manual"
                # Robust lookup: Find any file starting with [index]_
                pattern = f"{i+1}_*_result.json"
                matches = list(manual_dir.glob(pattern))
                
                if matches:
                    result_file = matches[0]
                    with open(result_file, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    if content and '"resolved_steps": []' not in content:
                        manual_result_exists = True

            # Skip if resume is on and we already have it in the final file
            if args.resume and faq.faq_id in processed_faq_ids:
                continue
                
            # Skip if load-manual is on but no manual file found for this FAQ
            if args.load_manual and not manual_result_exists:
                continue
            progress = f"[{i+1}/{len(faqs)}]"
            logger.info(f"{progress} Processing {faq.faq_id}...")
            
            try:
                # Phase 1: Classify + Page Resolution
                # CHECK CACHE
                p1 = next((r for r in phase1_results if r.intent_id == faq.faq_id), None)
                if p1:
                    # Apply downgrade to cache if necessary
                    if p1.intent_type == "procedural" and not p1.page_ids:
                        p1.intent_type = "informational"
                    logger.info(f"  → Phase 1: (Loaded from cache) {p1.intent_type}")
                else:
                    p1 = classify_faq(faq, all_pages)
                    # Auto-downgrade to informational if no pages were found
                    if p1.intent_type == "procedural" and not p1.page_ids:
                        logger.warning(f"  → Phase 1 found NO pages for {p1.intent_id}. Downgrading to 'informational'.")
                        p1.intent_type = "informational"
                    
                    phase1_results.append(p1)
                    logger.info(f"  → Phase 1: {p1.intent_type}, pages: {p1.page_ids}")
                
                # Phase 2: Step Draft (only if procedural)
                p2 = phase2_results.get(faq.faq_id)
                if p1.intent_type == "procedural" and not p2:
                    p2 = extract_steps(faq, p1)
                    phase2_results[faq.faq_id] = p2
                    logger.info(f"  → Phase 2: {len(p2.steps)} steps extracted")
                elif p1.intent_type == "procedural" and p2:
                    logger.info(f"  → Phase 2: (Loaded from cache) {len(p2.steps)} steps")
                
                # Phase 3: Element Matching
                p3 = phase3_results.get(faq.faq_id)
                if p1.intent_type == "procedural" and p2:
                    if p3:
                        logger.info(f"  → Phase 3: (Loaded from cache) {len(p3.resolved_steps)} steps")
                    else:
                        manual_dir = OUTPUT_DIR / "manual"
                        manual_dir.mkdir(parents=True, exist_ok=True)
                        # Only define if not already set by glob lookup
                        prompt_file = manual_dir / f"{i+1}_{p1.intent_id}_prompt.txt"
                        if not result_file:
                            result_file = manual_dir / f"{i+1}_{p1.intent_id}_result.json"

                        if args.dump_manual:
                            if not p1.page_ids:
                                logger.warning(f"  → Phase 1 found NO pages for {p1.intent_id}. No prompt generated.")
                            else:
                                from faq_pipeline.phases.phase3_match import match_elements
                                match_elements(faq, p1, p2, save_only=True)
                                debug_path = OUTPUT_DIR / "debug_prompt.txt"
                                if debug_path.exists():
                                    import shutil
                                    shutil.move(str(debug_path), str(prompt_file))
                            
                            if not result_file.exists():
                                with open(result_file, "w", encoding="utf-8") as f:
                                    json.dump({"resolved_steps": []}, f, indent=2)
                            logger.info(f"  → Dumped manual files for {p1.intent_id}")
                            continue

                        elif args.load_manual:
                            # result_file is already found at the top of the loop via glob
                            if not result_file or not result_file.exists():
                                logger.warning(f"  → Result file for {p1.intent_id} missing, skipping.")
                                continue
                            with open(result_file, "r", encoding="utf-8") as f:
                                manual_content = f.read().strip()
                            if not manual_content or '"resolved_steps": []' in manual_content:
                                logger.info(f"  → {result_file.name} is empty or template, skipping.")
                                continue
                            if "```json" in manual_content:
                                manual_content = manual_content.split("```json")[1].split("```")[0].strip()
                            elif "```" in manual_content:
                                manual_content = manual_content.split("```")[1].split("```")[0].strip()
                            p3 = Phase3Result.model_validate_json(manual_content)
                            phase3_results[faq.faq_id] = p3
                            logger.info(f"  → Phase 3: Loaded manual result from {result_file.name}")

                        elif args.manual:
                            from faq_pipeline.phases.phase3_match import match_elements
                            match_elements(faq, p1, p2, save_only=True)
                            print(f"\n{'='*60}\n MANUAL PHASE 3 for: {faq.faq_id}\n{'='*60}")
                            print(f"1. Open: faq_pipeline/output/debug_prompt.txt")
                            print(f"2. Copy-paste into your Web LLM.")
                            print(f"3. SAVE the JSON result to: faq_pipeline/output/manual_p3.json")
                            input("\n[WAITING] Press ENTER once 'manual_p3.json' is saved...")
                            manual_path = OUTPUT_DIR / "manual_p3.json"
                            if not manual_path.exists():
                                raise FileNotFoundError(f"manual_p3.json not found in {OUTPUT_DIR}")
                            with open(manual_path, "r", encoding="utf-8") as f:
                                manual_content = f.read().strip()
                            if "```json" in manual_content:
                                manual_content = manual_content.split("```json")[1].split("```")[0].strip()
                            elif "```" in manual_content:
                                manual_content = manual_content.split("```")[1].split("```")[0].strip()
                            p3 = Phase3Result.model_validate_json(manual_content)
                            phase3_results[faq.faq_id] = p3
                            logger.info(f"  → Phase 3: Loaded manual result ({len(p3.resolved_steps)} steps)")
                        else:
                            from faq_pipeline.phases.phase3_match import match_elements
                            p3 = match_elements(faq, p1, p2)
                            phase3_results[faq.faq_id] = p3
                            logger.info(f"  → Phase 3: {len(p3.resolved_steps)} steps resolved")
                
                # Phase 4: Possible Questions + Embedding
                intent = IntentWrite(
                    intent_type=p1.intent_type,
                    intent_id=p1.intent_id,
                    label=p1.label,
                    page_ids=p1.page_ids,
                    page_notes=p1.page_notes,
                    faq_id=faq.faq_id,
                    category=faq.category,
                    subcategory=faq.subcategory,
                    content=clean_html(faq.answer),
                    resolved_steps=p3.resolved_steps if p3 else []
                )
                
                if args.fast_p4:
                    intent.possible_questions = [faq.question]
                    # We still need to embed it
                    from faq_pipeline.phases.phase4_embed import get_query_embedding
                    intent.embedding = get_query_embedding(faq.question, mode="intent")
                    logger.info(f"  → Phase 4: Fast Mode (FAQ title only)")
                else:
                    intent = generate_questions_and_embed(intent)
                    logger.info(f"  → Phase 4: Generated {len(intent.possible_questions)} questions + embedding")
                
                final_intents.append(intent)
                
                # Phase 5: Write Neo4j
                if args.push:
                    success = push_to_neo4j(intent)
                    if success:
                        logger.info(f"  → Phase 5: Successfully pushed to Neo4j")
                else:
                    logger.info(f"  → Phase 5: Skipped (use --push to write to Neo4j)")

            except Exception as e:
                logger.error(f"  FAILED {faq.faq_id}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                continue

            # 3. Save Progress Incrementally
            save_json(phase1_results, "phase1_results.json")
            save_json(phase2_results, "phase2_results.json")
            save_json(phase3_results, "phase3_results.json")
            save_json(final_intents, "final_intents.json")

        logger.info(f"Pipeline finished. Processed {len(final_intents)} intents.")
        if not args.push:
            logger.info("REMINDER: Results were NOT pushed to Neo4j. Review 'final_intents.json' and run with --push when ready.")

    finally:
        close_driver()

if __name__ == "__main__":
    main()
