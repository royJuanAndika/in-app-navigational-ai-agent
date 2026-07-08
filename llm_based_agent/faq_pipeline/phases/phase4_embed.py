import logging
import json
from typing import List
from nkg_agent.core.llm import get_llm, get_embedding
from faq_pipeline.models import IntentWrite
from faq_pipeline.prompts.paraphrase import PARAPHRASE_SYSTEM_PROMPT, PARAPHRASE_USER_PROMPT

logger = logging.getLogger(__name__)

def generate_questions_and_embed(intent: IntentWrite) -> IntentWrite:
    """
    1. Call LLM to generate possible_questions → update intent.possible_questions
    2. Build embedding document string
    3. Get embedding via get_embedding
    4. Update intent.embedding
    5. Return updated intent
    """
    logger.info(f"Phase 4: Generating questions and embedding for {intent.intent_id}")
    
    llm = get_llm()
    user_prompt = PARAPHRASE_USER_PROMPT.format(
        label=intent.label,
        category=intent.category,
        subcategory=intent.subcategory,
        type=intent.intent_type,
        content=intent.content[:300]
    )
    
    questions = []
    try:
        response = llm.invoke([
            ("system", PARAPHRASE_SYSTEM_PROMPT),
            ("user", user_prompt)
        ])
        
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        data = json.loads(content)
        questions = data.get("possible_questions", [])
        if not questions:
            logger.warning(f"  No questions generated for {intent.intent_id}, using label as fallback.")
            questions = [intent.label]
    except Exception as e:
        logger.error(f"  Failed to generate questions for {intent.intent_id}: {e}")
        questions = [intent.label]
        
    intent.possible_questions = questions
    
    # Building step summary for content field in embedding if procedural
    step_summary = ""
    if intent.intent_type == "procedural" and intent.resolved_steps:
        step_summary = "Steps: " + " | ".join([f"{s.action} {s.nkg_id}" for s in intent.resolved_steps[:5]])
    
    # 2. Build embedding document string (exact format from design)
    from nkg_agent.core.llm import INTENT_DOC_INSTRUCTION
    embed_doc = f"""Instruct: {INTENT_DOC_INSTRUCTION}
Document: Intent: {intent.label}
Kategori: {intent.category} > {intent.subcategory}
Tipe: {intent.intent_type}
Pertanyaan: {" | ".join(questions)}
Konten: {intent.content[:200] if intent.intent_type == "informational" else step_summary}"""

    # 3. Get embedding
    try:
        embedding = get_embedding(embed_doc)
        intent.embedding = embedding
    except Exception as e:
        logger.error(f"  Failed to get embedding for {intent.intent_id}: {e}")
        intent.embedding = []
        
    return intent
