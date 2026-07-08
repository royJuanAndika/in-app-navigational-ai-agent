import json
import logging
from typing import List
from langchain_core.messages import SystemMessage, HumanMessage
from nkg_agent.core.llm import get_llm
from faq_pipeline.models import FAQEntry, Phase1Result
from faq_pipeline.prompts.classify import SYSTEM_PROMPT, USER_PROMPT

logger = logging.getLogger(__name__)

def classify_faq(faq: FAQEntry, all_pages: List[dict]) -> Phase1Result:
    """
    Calls get_llm() with the classify prompt.
    Parses JSON response into Phase1Result.
    Retries up to 2 times on JSON parse failure.
    """
    llm = get_llm()
    
    # Format pages list for prompt
    pages_list = "\n".join([
        f"{p['page_id']} | {p['title']} | {p['description'] or ''}"
        for p in all_pages
    ])
    
    user_content = USER_PROMPT.format(
        question=faq.question,
        category=faq.category,
        subcategory=faq.subcategory,
        subsubcategory=faq.subsubcategory or "",
        answer=faq.answer,
        pages_list=pages_list
    )
    
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_content)
    ]
    
    # DEBUG: Save prompt to file for inspection
    from pathlib import Path
    debug_path = Path(__file__).resolve().parents[1] / "output" / "debug_phase1_prompt.txt"
    with open(debug_path, "w", encoding="utf-8") as f:
        f.write(f"--- SYSTEM ---\n{SYSTEM_PROMPT}\n\n--- USER ---\n{user_content}")
    logger.info(f"    Phase 1 prompt saved to {debug_path}")

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            response = llm.invoke(messages)
            content = response.content.strip()
            
            # Find JSON block if LLM added preamble/postamble
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "{" in content and "}" in content:
                # Basic attempt to extract JSON if not in blocks
                start = content.find("{")
                end = content.rfind("}") + 1
                content = content[start:end]
            
            data = json.loads(content)
            return Phase1Result.model_validate(data)
            
        except Exception as e:
            if attempt == max_retries:
                logger.error(f"Failed to classify FAQ {faq.faq_id} after {max_retries} retries: {e}")
                raise
            logger.warning(f"Retry {attempt + 1}/{max_retries} for FAQ {faq.faq_id} due to: {e}")
            
    # Should not reach here
    raise RuntimeError(f"Unexpected exit in classify_faq for {faq.faq_id}")
