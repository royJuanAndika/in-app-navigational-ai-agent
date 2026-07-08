import logging
import json
from typing import List, Dict
from nkg_agent.core.llm import get_llm
from nkg_agent.core.graph_db import get_page_elements_with_hierarchy, get_page_info
from faq_pipeline.models import FAQEntry, Phase1Result, Phase2Result, Phase3Result, ResolvedStep
from faq_pipeline.prompts.element_match import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE, render_page_elements
from faq_pipeline.review_log import append_review

logger = logging.getLogger(__name__)

def match_elements(
    faq: FAQEntry,
    phase1: Phase1Result,
    phase2: Phase2Result,
    save_only: bool = False,
    feedback: str = None,
    previous_steps: List[ResolvedStep] = None
) -> Phase3Result:
    """
    For each page_id in phase1.page_ids (in order):
      1. Fetch elements: get_page_elements_with_hierarchy(page_id) from graph_db
      2. Render element list as structured text
      3. Filter phase2.steps to only those assigned to this page_id
      4. Call LLM with retry loop and Pydantic validation
      5. Parse Phase3Result, accumulate resolved_steps with strict global ordering
    """
    logger.info(f"Phase 3: Matching elements for {faq.faq_id}")
    
    accumulated_resolved_steps: List[ResolvedStep] = []
    
    # Process pages in order
    for page_id in phase1.page_ids:
        logger.info(f"  Processing page: {page_id}")
        
        # 1. Fetch elements
        import time
        start_fetch = time.time()
        elements = get_page_elements_with_hierarchy(page_id)
        fetch_duration = time.time() - start_fetch
        logger.info(f"    Fetched {len(elements)} elements from Neo4j in {fetch_duration:.2f}s")
        
        page_info = get_page_info(page_id)
        page_title = page_info.get('title', 'Unknown') if page_info else 'Unknown'
        
        # 2. Render element list
        element_list_str = render_page_elements(elements)
        
        # DEBUG: Save raw element list immediately
        from pathlib import Path
        debug_path = Path(__file__).resolve().parents[1] / "output" / "debug_elements.txt"
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(element_list_str)
        logger.info(f"    Raw element list saved to {debug_path}")

        # 3. Filter steps assigned to this page
        page_steps = [s for s in phase2.steps if s.page_id == page_id]
        if not page_steps:
            logger.info(f"    No draft steps assigned to {page_id}, skipping LLM call.")
            continue

        step_drafts_str = "\n".join([
            f"- Step {s.order}: {s.action} {s.description} (Hint: {s.element_hint})"
            for s in page_steps
        ])
        
        # 4. Accumulated steps string for context
        accumulated_steps_str = "\n".join([
            f"- Resolved Step {s.order}: {s.action} on {s.nkg_id} ({s.note})"
            for s in accumulated_resolved_steps
        ]) if accumulated_resolved_steps else "No previous steps."

        # 5. Build feedback section
        feedback_section = ""
        if feedback and previous_steps:
            prev_steps_str = "\n".join([f"- Step {s.order}: {s.action} on {s.nkg_id} ({s.note})" for s in previous_steps if s.page_id == page_id])
            feedback_section = f"\n### PREVIOUS INCORRECT RESULT\n{prev_steps_str}\n\n### USER FEEDBACK TO FIX ERRORS\n{feedback}\n"
        elif feedback:
            feedback_section = f"\n### USER FEEDBACK TO FIX ERRORS\n{feedback}\n"

        # 6. Call LLM with retry loop
        user_prompt = USER_PROMPT_TEMPLATE.format(
            page_id=page_id,
            page_title=page_title,
            accumulated_steps_str=accumulated_steps_str,
            element_list_str=element_list_str,
            step_drafts_str=step_drafts_str,
            feedback_section=feedback_section
        )
        
        # DEBUG: Save prompt to file for inspection
        from pathlib import Path
        debug_path = Path(__file__).resolve().parents[1] / "output" / "debug_prompt.txt"
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(f"### FAQ ID: {faq.faq_id}\n")
            f.write(f"--- SYSTEM PROMPT ---\n{SYSTEM_PROMPT}\n\n--- USER PROMPT ---\n{user_prompt}")
        logger.info(f"    Full prompt saved to {debug_path} for inspection.")
        
        if save_only:
            # Pipeline will handle the manual input
            return Phase3Result(resolved_steps=[])

        llm = get_llm()
        last_error = None
        
        for attempt in range(2):
            try:
                logger.info(f"    Attempt {attempt+1} starting (streaming to console)...")
                content = ""
                # Use stream to see tokens in real-time
                for chunk in llm.stream([
                    ("system", SYSTEM_PROMPT),
                    ("user", user_prompt)
                ]):
                    token = chunk.content
                    content += token
                    print(token, end="", flush=True) # Live stream to terminal
                
                print("\n") # Newline after stream finishes
                content = content.strip()

                if content.startswith("```json"):
                    content = content[7:-3].strip()
                elif content.startswith("```"):
                    content = content[3:-3].strip()
                
                # Robust Pydantic validation
                try:
                    page_result = Phase3Result.model_validate_json(content)
                except Exception as parse_err:
                    logger.error(f"    Failed to parse JSON. Raw length: {len(content)}")
                    raise parse_err
                
                # 6. Accumulate and re-index steps for global consistency
                for i, step in enumerate(page_result.resolved_steps):
                    # Ensure global sequential order
                    global_order = len(accumulated_resolved_steps) + 1
                    step.order = global_order
                    
                    # ── Look up additional metadata from our 'elements' list ────────────────
                    # This ensures we have the real CSS selector and DOM ID for highlighting
                    matched_el = next((e for e in elements if e['nkg_id'] == step.nkg_id), None)
                    if matched_el:
                        step.selector = matched_el.get('selector')
                        step.element_id = matched_el.get('id')
                    
                    accumulated_resolved_steps.append(step)
                    
                    # Review flagging for low confidence
                    if step.confidence != "high":
                        from pathlib import Path
                        log_path = Path(__file__).resolve().parents[1] / "output" / "review_log.jsonl"
                        append_review(log_path, faq.faq_id, step, f"Confidence is {step.confidence}")
                
                # Success for this page
                last_error = None
                break
                
            except Exception as e:
                last_error = e
                logger.warning(f"    Attempt {attempt+1} failed for {page_id}: {e}")
                continue
        
        if last_error:
            logger.error(f"    Failed to resolve steps for page {page_id} after retries: {last_error}")
            # We raise here to allow the pipeline loop in pipeline.py to catch it per-FAQ
            raise last_error

    return Phase3Result(resolved_steps=accumulated_resolved_steps)
