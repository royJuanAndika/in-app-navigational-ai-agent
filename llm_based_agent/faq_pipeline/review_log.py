import json
from datetime import datetime, timezone
from pathlib import Path
from .models import ResolvedStep

def append_review(log_path: Path, faq_id: str, step: ResolvedStep, reason: str) -> None:
    """
    Appends one JSON object per line to review_log.jsonl (newline-delimited JSON).
    
    Object shape: {faq_id, order, nkg_id, action, confidence, note, reason, timestamp_utc}
    """
    log_entry = {
        "faq_id": faq_id,
        "order": step.order,
        "nkg_id": step.nkg_id,
        "action": step.action,
        "confidence": step.confidence,
        "note": step.note,
        "reason": reason,
        "timestamp_utc": datetime.now(timezone.utc).isoformat()
    }
    
    # Ensure parent directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")
