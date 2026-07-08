from typing import Literal, Optional, Dict, List
from pydantic import BaseModel, Field

class FAQEntry(BaseModel):
    """Mirrors one JSON object from help_center_faq.json"""
    faq_id: str
    question: str
    answer: str
    category: str
    subcategory: str
    subsubcategory: Optional[str] = None
    source: Optional[str] = None

class Phase1Result(BaseModel):
    """Output of Phase 1 LLM call: Classify + Page Resolution"""
    intent_type: Literal["procedural", "informational"]
    intent_id: str
    label: str
    page_ids: List[str]
    page_notes: Dict[str, str] = Field(description="{page_id: note about what happens on this page}")

class StepDraft(BaseModel):
    """One step from Phase 2: Step Draft Extraction"""
    order: int
    page_id: str
    action: Literal["click", "input", "select", "upload", "navigate", "check"]
    description: str
    element_hint: str

class Phase2Result(BaseModel):
    """Output of Phase 2 LLM call"""
    steps: List[StepDraft]

class ResolvedStep(BaseModel):
    """Output of Phase 3 per step: Element Matching"""
    order: int
    nkg_id: str
    action: str
    confidence: Literal["high", "medium", "low"]
    note: str
    selector: Optional[str] = None
    element_id: Optional[str] = None

class Phase3Result(BaseModel):
    """Output of Phase 3"""
    resolved_steps: List[ResolvedStep]

class IntentWrite(BaseModel):
    """Final assembled object ready for Neo4j write"""
    # From Phase 1
    intent_type: Literal["procedural", "informational"]
    intent_id: str
    label: str
    page_ids: List[str]
    page_notes: Dict[str, str]
    
    # From FAQ source
    faq_id: str
    category: str
    subcategory: str
    content: str  # Cleaned answer text
    
    # From Phase 3
    resolved_steps: List[ResolvedStep] = []  # Empty for informational
    previous_resolved_steps: Optional[List[ResolvedStep]] = None # Backup for revert
    
    # From Phase 4
    possible_questions: List[str] = []
    embedding: List[float] = []
