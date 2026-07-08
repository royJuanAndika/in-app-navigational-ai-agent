"""
FastAPI server for the In-App Navigational Agent.

Endpoints:
    POST /api/chatbot/message — primary chat endpoint (used by floating window)
    POST /chat                — legacy alias kept for CLI smoke-tests
    POST /api/chatbot/log     — accepts frontend debug logs (fire-and-forget)
    GET  /health              — health check
"""

import logging
import json
from pathlib import Path
from contextlib import asynccontextmanager

from langchain_core.globals import set_debug
set_debug(False)

import sys
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..agent.graph import achat_stream, chat, create_agent
from ..core.config import get_settings
from ..core.graph_db import close_driver, get_driver, update_element_metadata

logger = logging.getLogger(__name__)



# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class HistoryItem(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class GuidanceStep(BaseModel):
    step: int
    instruction: str
    nkg_id: str | None = None
    page_url: str | None = None
    selector: str | None = None
    element_id: str | None = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    # Frontend sends current URL (may include query string + hash)
    current_page: str | None = Field(None, alias="userCurrentPagePosition")
    history: list[HistoryItem] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ChatResponse(BaseModel):
    message: str
    type: str = "info"
    guidance: list[GuidanceStep] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Review Tool schemas
# ---------------------------------------------------------------------------

class ReviewNoteRequest(BaseModel):
    intent_id: str
    note: str
    needs_rerun: bool

class ReviewStatusUpdate(BaseModel):
    last_intent_id: str | None = None
    reviewed_ids: list[str] | None = None

class RevertRequest(BaseModel):
    intent_id: str

class NodeUpdateRequest(BaseModel):
    nkg_id: str
    selector: str | None = None
    element_id: str | None = None

RERUN_JOBS = {}  # { intent_id: { "status": "running"|"done"|"error", "error": str, "timestamp": float } }

# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify connections on startup; clean up on shutdown."""
    logger.info("Starting up — verifying Neo4j connection…")
    get_driver()
    logger.info("Creating agent…")
    app.state.agent = create_agent()
    logger.info("Startup complete.")
    yield
    logger.info("Shutting down — closing Neo4j driver…")
    close_driver()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="In-App Navigational Agent",
    version="0.2.0",
    description="AI agent that guides users through an HR SaaS admin panel.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_chat(agent, req: ChatRequest) -> ChatResponse:
    """Shared logic used by both chat endpoints."""
    if not req.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty.")

    # Strip query string / hash from page path — agent only needs the pathname
    current_page = req.current_page
    if current_page:
        current_page = current_page.split("?")[0].split("#")[0]

    history = [h.model_dump() for h in req.history] if req.history else None

    try:
        result = chat(
            agent=agent,
            user_message=req.message,
            current_page=current_page,
            history=history,
        )
    except Exception as exc:
        logger.exception("Agent error")
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}")

    guidance_steps = [GuidanceStep(**step) for step in result.get("guidance", [])]

    return ChatResponse(
        message=result["message"],
        type=result.get("type", "info"),
        guidance=guidance_steps,
        tools_used=result.get("tools_used", []),
        duration_ms=result.get("duration_ms", 0),
    )


class EnrichRequest(BaseModel):
    nkg_ids: list[str]


@app.post("/api/chatbot/enrich")
async def chatbot_enrich(req: EnrichRequest):
    """Batch-resolve selector/element_id/page for a list of NKG IDs."""
    logger.info(f"🔍 Batch enriching {len(req.nkg_ids)} IDs")
    results = {}
    
    driver = get_driver()
    with driver.session() as session:
        # We query for all at once to be efficient
        query = """
        MATCH (e:Element)
        WHERE e.nkg_id IN $ids
        OPTIONAL MATCH (p:Page)-[:CONTAINS*]->(e)
        RETURN e.nkg_id AS nkg_id, 
               e.selector AS selector, 
               e.id AS element_id, 
               p.id AS page_url
        """
        records = session.run(query, ids=req.nkg_ids)
        for r in records:
            results[r["nkg_id"]] = {
                "selector": r["selector"],
                "element_id": r["element_id"],
                "page_url": r["page_url"]
            }
            
    return results


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/api/chatbot/message", response_model=ChatResponse)
async def chatbot_message(req: ChatRequest):
    """Primary endpoint — used by the floating chat window."""
    return _run_chat(app.state.agent, req)


@app.post("/api/chatbot/stream")
async def chatbot_stream(req: ChatRequest):
    """SSE streaming endpoint for real-time thinking/tool events."""
    if not req.message.strip():     
        raise HTTPException(status_code=422, detail="Message cannot be empty.")
    
    print(req)
    current_page = req.current_page
    if current_page:
        current_page = current_page.split("?")[0].split("#")[0]

    history = [h.model_dump() for h in req.history] if req.history else None

    return StreamingResponse(
        achat_stream(
            agent=app.state.agent,
            user_message=req.message,
            current_page=current_page,
            history=history,
        ),
        media_type="text/event-stream",
    )


@app.post("/chat", response_model=ChatResponse)
async def chat_legacy(req: ChatRequest):
    """Legacy alias kept for CLI smoke-tests and existing integrations."""
    return _run_chat(app.state.agent, req)


@app.post("/api/chatbot/log")
async def chatbot_log(request: Request):
    """Accept frontend debug logs. Logs to server console and returns 200."""
    try:
        body = await request.json()
        logger.info("[Frontend Log] type=%s | %s", body.get("type", "?"), str(body)[:500])
    except Exception:
        pass  # fire-and-forget; never fail the caller
    return {"status": "logged"}


@app.get("/health")
async def health():
    """Quick health check."""
    settings = get_settings()
    try:
        get_driver()
        neo4j_status = "connected"
    except Exception:
        neo4j_status = "error"

    return {
        "status": "ok",
        "neo4j": neo4j_status,
        "model": settings.llm_model,
    }

# ---------------------------------------------------------------------------
# Review Dashboard Endpoints
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path(__file__).resolve().parents[3] / "faq_pipeline" / "output"

@app.get("/api/review/intents")
async def get_review_intents():
    path = OUTPUT_DIR / "final_intents.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/api/review/status")
async def get_review_status():
    path = OUTPUT_DIR / "review_status.json"
    if not path.exists():
        return {"last_intent_id": None, "reviewed_ids": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@app.post("/api/review/status")
async def update_review_status(status: ReviewStatusUpdate):
    path = OUTPUT_DIR / "review_status.json"
    current = {"last_intent_id": None, "reviewed_ids": []}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            current = json.load(f)
    
    if status.last_intent_id is not None:
        current["last_intent_id"] = status.last_intent_id
    if status.reviewed_ids is not None:
        current["reviewed_ids"] = status.reviewed_ids
        
    with open(path, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
    return current

@app.post("/api/review/node/update")
async def update_node_metadata(req: NodeUpdateRequest):
    success = update_element_metadata(req.nkg_id, req.selector, req.element_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Node {req.nkg_id} not found in NKG")
    return {"status": "ok", "nkg_id": req.nkg_id}

@app.post("/api/review/note")
async def save_review_note(req: ReviewNoteRequest):
    path = OUTPUT_DIR / "review_notes.json"
    notes = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            notes = json.load(f)
    
    notes[req.intent_id] = {
        "note": req.note,
        "needs_rerun": req.needs_rerun
    }
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(notes, f, indent=2)
    return {"status": "saved"}

# ---------------------------------------------------------------------------
# Background Task for LLM Fix
# ---------------------------------------------------------------------------

def _run_phase3_fix(intent_id: str, note: str):
    import time
    try:
        RERUN_JOBS[intent_id] = {"status": "running", "error": None, "timestamp": time.time()}
        
        # 1. Load Intent to get faq_id
        intents_path = OUTPUT_DIR / "final_intents.json"
        with open(intents_path, "r", encoding="utf-8") as f:
            intents = json.load(f)
            
        intent_index = next((i for i, intent in enumerate(intents) if intent["intent_id"] == intent_id), None)
        if intent_index is None:
            raise ValueError(f"Intent {intent_id} not found in final_intents.json")
            
        current_intent = intents[intent_index]
        faq_id = current_intent["faq_id"]
        
        # 2. Load necessary models
        import sys
        base_dir = Path(__file__).resolve().parents[3]
        if str(base_dir) not in sys.path:
            sys.path.append(str(base_dir))
            
        from faq_pipeline.models import FAQEntry, Phase1Result, Phase2Result, ResolvedStep
        from faq_pipeline.phases.phase3_match import match_elements
        
        faq_file = base_dir.parents[0] / "data_preprocessing_and_cleaning" / "scrape_faq" / "help_center_faq.json"
        with open(faq_file, "r", encoding="utf-8") as f:
            faqs_data = json.load(f)["faq"]
            faq_dict = next((f for f in faqs_data if f["faq_id"] == faq_id), None)
            if not faq_dict:
                raise ValueError(f"FAQ {faq_id} not found in help_center_faq.json")
            faq = FAQEntry.model_validate(faq_dict)
            
        with open(OUTPUT_DIR / "phase1_results.json", "r", encoding="utf-8") as f:
            p1_data = json.load(f)
            p1_dict = next((p for p in p1_data if p["intent_id"] == faq_id), None)
            if not p1_dict:
                raise ValueError(f"Phase1Result for {faq_id} not found")
            p1 = Phase1Result.model_validate(p1_dict)
            
        with open(OUTPUT_DIR / "phase2_results.json", "r", encoding="utf-8") as f:
            p2_data = json.load(f)
            if faq_id not in p2_data:
                raise ValueError(f"Phase2Result for {faq_id} not found")
            p2 = Phase2Result.model_validate(p2_data[faq_id])
            
        previous_steps = [ResolvedStep.model_validate(s) for s in current_intent.get("resolved_steps", [])]
            
        # 3. Call match_elements with feedback
        p3_result = match_elements(faq, p1, p2, save_only=False, feedback=note, previous_steps=previous_steps)
        
        # 4. Save back to final_intents.json
        if "previous_resolved_steps" not in current_intent or current_intent["previous_resolved_steps"] is None:
            current_intent["previous_resolved_steps"] = current_intent.get("resolved_steps", [])
            
        current_intent["resolved_steps"] = [s.model_dump() for s in p3_result.resolved_steps]
        intents[intent_index] = current_intent
        
        with open(intents_path, "w", encoding="utf-8") as f:
            json.dump(intents, f, indent=2, ensure_ascii=False)
            
        RERUN_JOBS[intent_id] = {"status": "done", "error": None, "timestamp": time.time()}
        
    except Exception as e:
        import traceback
        RERUN_JOBS[intent_id] = {"status": "error", "error": str(e), "timestamp": time.time()}

@app.post("/api/review/rerun")
async def rerun_intent(req: ReviewNoteRequest, background_tasks: BackgroundTasks):
    """Trigger background job to re-run Phase 3 with feedback"""
    # Save the note first
    await save_review_note(req)
    # Start background task
    background_tasks.add_task(_run_phase3_fix, req.intent_id, req.note)
    return {"status": "started"}

@app.get("/api/review/jobs")
async def get_jobs():
    """Get status of all rerun jobs"""
    return RERUN_JOBS

@app.post("/api/review/revert")
async def revert_intent(req: RevertRequest):
    """Revert resolved_steps to previous_resolved_steps"""
    intents_path = OUTPUT_DIR / "final_intents.json"
    if not intents_path.exists():
        raise HTTPException(status_code=404, detail="final_intents.json not found")
        
    with open(intents_path, "r", encoding="utf-8") as f:
        intents = json.load(f)
        
    intent_index = next((i for i, intent in enumerate(intents) if intent["intent_id"] == req.intent_id), None)
    if intent_index is None:
        raise HTTPException(status_code=404, detail="Intent not found")
        
    current_intent = intents[intent_index]
    if "previous_resolved_steps" in current_intent and current_intent["previous_resolved_steps"] is not None:
        current_intent["resolved_steps"] = current_intent["previous_resolved_steps"]
        current_intent["previous_resolved_steps"] = None
        intents[intent_index] = current_intent
        
        with open(intents_path, "w", encoding="utf-8") as f:
            json.dump(intents, f, indent=2, ensure_ascii=False)
        return {"status": "reverted", "intent": current_intent}
    else:
        raise HTTPException(status_code=400, detail="No previous steps to revert to")
