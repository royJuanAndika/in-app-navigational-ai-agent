import json
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from nkg_agent.core.llm import get_llm
from faq_pipeline.models import FAQEntry, Phase1Result, Phase2Result
from faq_pipeline.prompts.step_draft import SYSTEM_PROMPT, USER_PROMPT

logger = logging.getLogger(__name__)

def extract_steps(faq: FAQEntry, phase1: Phase1Result) -> Phase2Result:
    """
    Only called for procedural FAQs.
    Calls get_llm() with the step_draft prompt.
    Parses JSON response into Phase2Result.
    Retries up to 2 times on JSON parse failure.
    """
    if phase1.intent_type != "procedural":
        return Phase2Result(steps=[])

    llm = get_llm()
    
    # Format page notes for prompt
    page_notes_str = json.dumps(phase1.page_notes, indent=2)
    
    user_content = USER_PROMPT.format(
        answer=faq.answer,
        page_notes=page_notes_str
    )
    
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_content)
    ]
    
    # DEBUG: Save prompt to file for inspection
    from pathlib import Path
    debug_path = Path(__file__).resolve().parents[1] / "output" / "debug_phase2_prompt.txt"
    with open(debug_path, "w", encoding="utf-8") as f:
        f.write(f"--- SYSTEM ---\n{SYSTEM_PROMPT}\n\n--- USER ---\n{user_content}")
    logger.info(f"    Phase 2 prompt saved to {debug_path}")

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            response = llm.invoke(messages)
            content = response.content.strip()
            
            # Find JSON block
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "{" in content and "}" in content:
                start = content.find("{")
                end = content.rfind("}") + 1
                content = content[start:end]
            
            data = json.loads(content)
            result = Phase2Result.model_validate(data)
            
            # Validate that the LLM didn't hallucinate a page_id
            for step in result.steps:
                if step.page_id not in phase1.page_ids:
                    raise ValueError(f"Hallucinated page_id '{step.page_id}'. Must be exactly one of: {phase1.page_ids}")
                    
            return result
            
        except Exception as e:
            if attempt == max_retries:
                logger.error(f"Failed to extract steps for FAQ {faq.faq_id} after {max_retries} retries: {e}")
                raise
            logger.warning(f"Retry {attempt + 1}/{max_retries} for FAQ {faq.faq_id} due to: {e}")
            
    # Should not reach here
    raise RuntimeError(f"Unexpected exit in extract_steps for {faq.faq_id}")
