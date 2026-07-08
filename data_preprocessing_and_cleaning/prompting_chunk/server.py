"""
NKG Extraction Proxy Server
============================
Receives a compact HTML skeleton from the notebook, runs the LLM via
the local Ollama instance, validates the JSON response, and returns
structured NKG data ready to be written to disk.

Run with:
    uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

import json
import logging
import os
import re
from typing import AsyncGenerator, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="NKG Extraction Server", version="1.0.0")

# ── Configuration ──────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = "http://localhost:11434"
PRIMARY_MODEL = "deepseek-r1:70b"
FALLBACK_MODEL = "qwen3:32b"
TIMEOUT_SECONDS = 360  # large models need time
API_TOKEN = "some-secret-token-2026"


# ── System Prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are an expert UI analyst building a Navigational Knowledge Graph (NKG) \
for an HR SaaS admin panel called Platform XYZ.

Your task: given the FULL HTML of ONE admin panel page, extract NKG data that \
maps user actions to UI elements and page transitions. The HTML is unfiltered, so \
use your judgment to identify what is actionable vs. decorative.

────────────────────────────────────────
OUTPUT RULES  (follow strictly)
────────────────────────────────────────
1. Return ONLY a valid JSON object.
   - No explanation, no markdown fences, no code blocks, no extra keys.

2. `id` values  (CRITICAL — this id will be used by frontend JS to target the element)

   CASE A — Element already has a DOM id attribute:
     → Use the DOM id VERBATIM as the NKG id. Do NOT rename it.
     → Example: <button id="btn_favorite"> → NKG id: "btn_favorite"

   CASE B — Element has NO DOM id attribute:
     → Generate a SHORT, DESCRIPTIVE id in snake_case.
     → MANDATORY: prefix it with the page slug so it is globally unique
       across all 47 pages.
     → Page slug = last segment of page_url, e.g. page "/customer/employee"
       has slug "employee".
     → Format: "<page_slug>__<short_description>"
     → Example: button with onclick="check_addon_46_emp_quotas()" on /customer/employee
       → NKG id: "employee__btn_add_karyawan"
     → Example: modal with class "modal-add" but no id on /customer/office
       → NKG id: "office__modal_add_kantor"

3. `selector`  (CRITICAL — this is the CSS selector the JS will use to find the element)

   PRIORITY ORDER:
   1. If element has DOM id  → use  #dom_id   (e.g. "#btn_favorite")
   2. If no DOM id but has a meaningful onclick → use attribute selector:
        [onclick*="function_name"]   (e.g. '[onclick*="check_addon_46_emp_quotas"]')
   3. If no id and no onclick → combine tag + unique class + context:
        e.g.  "div.modal-add.fade"  or  ".form-group input[name='emp_name']"

   NEVER use a bare class selector alone (e.g. NEVER just ".btn_action" —
   that class appears on EVERY page and is not a unique target).
   The `selector` for an element with a DOM id must be exactly "#<id>", nothing more.

4. **HARD RULE — Never skip elements that have a DOM `id`.**
   If an element has an `id` attribute in the HTML, it MUST appear in your output.
   Do NOT skip it because it is hidden (display:none), looks decorative, or
   seems like a container. Hidden elements (like tables populated by JavaScript,
   modals hidden until triggered, or wrappers that appear after user action)
   are ESPECIALLY important — the frontend JS needs to target them.

5. `desc` values   → Bahasa Indonesia, action-oriented.
                     Good:  "Tombol untuk menambah karyawan baru"
                     Bad:   "button"

6. `triggers`      → `to_type` is:
                       - "element"  when the interaction opens/shows something
                         on the SAME page (modal, drawer, panel, tab content).
                       - "page"     when the interaction changes the route/URL.

6b. `parent_element_id` (optional) on each element:
     - Use when an actionable element is clearly nested inside another actionable element
         (for example input fields inside a modal/form container).
     - Parent id must reference another element id in the same output.
     - Do not set it for top-level elements.

7. **CONDITIONAL VISIBILITY — Model JavaScript-driven show/hide as TRIGGERS.**
   Many elements in this admin panel start hidden (`style="display:none"` or
   `style="display: none;"`) and only appear after a user action.
   You MUST detect and model these patterns:

   HOW TO DETECT:
   - Element has `style="display:none"` or `style="display: none;"` → it is
     conditionally visible. Something triggers it to appear.
   - Look at nearby elements for `onchange`, `onclick`, `oninput` handlers
     that call JS functions.
   - The JS function name is your clue (e.g. `filter_submit_()` shows a table,
     `check_addon_46_emp_quotas()` opens a modal).

   HOW TO MODEL IT:
   - Add a TRIGGER from the controlling element TO the hidden element.
   - Use `to_type: "element"`.
   - Example: `combo_filter_schedule` (onchange) makes `btn_filter_submit` appear
     → TRIGGER: combo_filter_schedule → btn_filter_submit
   - Example: `btn_filter_submit` (onclick="filter_submit_") causes the results
     table `div_emp_list` to populate and show
     → TRIGGER: btn_filter_submit → div_emp_list

   IMPORTANT: The hidden element itself MUST still appear in `elements[]`.
   Hidden ≠ unimportant. Hidden elements are often the most important targets
   for the navigation agent (the user needs to be guided TO them).

8. For elements WITHOUT a DOM id, use your judgment to focus on:
   - Action buttons  (tambah, simpan, hapus, ekspor, impor, ubah, submit)
   - Top-level modal containers  (NOT every field inside a modal)
   - Key form fields inside modals  (name, ID, date, select fields)
   - Navigation links to other admin panel pages
   - Table-row click handlers that open a detail view
   - Tab / filter controls that reveal different content
   - Skip pure decoration: bare icons, tooltip wrappers, style/layout divs.

9. When in doubt about a no-id element — include it.

────────────────────────────────────────
REQUIRED JSON SCHEMA
────────────────────────────────────────
{
  "page": {
    "id":    "/customer/<route>",
    "title": "Human-readable page title",
    "desc":  "Satu kalimat tentang tujuan halaman ini."
  },
  "elements": [
    {
      "id":       "element_id_snake_case",
      "desc":     "Deskripsi singkat dalam Bahasa Indonesia.",
      "type":     "button | input | select | textarea | modal | table | link | tab | section",
            "selector": "#css_selector",
            "parent_element_id": "optional parent element id when nested"
    }
  ],
  "triggers": [
    {
      "from":    "source_element_id",
      "to":      "target_element_id  OR  /page/path",
      "to_type": "element | page"
    }
  ]
}
"""


RECONCILE_PATCH_SYSTEM_PROMPT = """\
You are reconciling an EXISTING page-level NKG by PATCH ONLY.

Return ONLY a valid JSON object (no markdown, no explanation):
{
    "elements": [
        {"id": "...", "desc": "...", "type": "...", "selector": "...", "parent_element_id": "optional_parent_id"}
    ],
    "triggers": [
        {"from": "...", "to": "...", "to_type": "element|page"}
    ]
}

Rules:
1) Do NOT regenerate whole NKG.
2) Add only useful missing relations/elements from full HTML context.
3) Keep DOM-id selector strictness (#id).
4) Avoid duplicates and decorative noise.
"""


PATCH_MISSING_SYSTEM_PROMPT = """\
You are patching missing DOM ids for an EXISTING page-level NKG.

Return ONLY valid JSON:
{
    "elements": [
        {"id": "...", "desc": "...", "type": "...", "selector": "#...", "parent_element_id": "optional_parent_id"}
    ],
    "excluded": [
        {"id": "...", "reason": "alasan singkat kenapa tidak dimasukkan"}
    ],
    "triggers": [
        {"from": "...", "to": "...", "to_type": "element|page"}
    ]
}

Rules:
1) Review each id in MISSING_DOM_IDS and decide include vs exclude.
2) Include only worthy/actionable/significant UI targets.
3) Exclude decorative/system/noise ids (e.g. auto-generated internal ids) unless clearly actionable.
4) For included DOM-id elements, selector must be exactly '#<id>'.
5) Never remove existing elements/triggers from EXISTING_NKG_JSON.
"""


SELECTOR_REPAIR_SYSTEM_PROMPT = """\
You are repairing selectors for EXISTING NKG elements.
Return ONLY valid JSON:
{
    "elements": [
        {"id": "...", "selector": "..."}
    ]
}

Rules:
1) Repair selectors only for IDs listed in FAILED_ELEMENTS.
2) Never change IDs.
3) For DOM-id elements, selector must be exactly '#<id>'.
4) Target one intended actionable element whenever possible.
5) Do not add new elements or triggers.
"""


def build_user_prompt(skeleton: dict) -> str:
    url = skeleton.get("page_url", "")
    page_slug = url.rstrip("/").split("/")[-1] if url else skeleton.get("filename", "").replace(".html", "")

    return (
        "Analyze the full HTML below and extract the NKG data.\n\n"
        f"PAGE SLUG (use this as prefix for generated ids on elements that have NO DOM id): \"{page_slug}\"\n"
        f"PAGE URL: {url}\n"
        f"PAGE TITLE: {skeleton.get('page_title', '?')}\n\n"
        "FULL HTML:\n"
        f"{skeleton.get('html_content', '')}\n\n"
        "Return ONLY the JSON object. No extra text."
    )


def build_missing_patch_prompt(skeleton: dict, existing_nkg: dict, missing_ids: list[str]) -> str:
    url = skeleton.get("page_url", "")
    title = skeleton.get("page_title", "?")
    missing_json = json.dumps(sorted(set(missing_ids)), ensure_ascii=False)
    existing_json = json.dumps(existing_nkg, ensure_ascii=False)

    return (
        "You are fixing an EXISTING NKG result by INSERTION ONLY.\\n\\n"
        "IMPORTANT:\\n"
        "- Do NOT regenerate full JSON.\\n"
        "- For each id in MISSING_DOM_IDS, decide whether to include (worthy) or exclude (noise).\\n"
        "- Keep ids verbatim exactly as DOM id.\\n"
        "- For included ids, selector must be exactly '#<id>'.\\n"
        "- Put excluded ids into excluded[] with short reason in Bahasa Indonesia.\\n"
        "- If an inserted element is clearly nested under another element, set parent_element_id.\\n"
        "- Add triggers only when confident and relevant.\\n\\n"
        "Return ONLY this JSON schema:\\n"
        "{\\n"
        '  "elements": [ {"id": "...", "desc": "...", "type": "...", "selector": "#...", "parent_element_id": "optional_parent_id"} ],\\n'
        '  "excluded": [ {"id": "...", "reason": "..."} ],\\n'
        '  "triggers": [ {"from": "...", "to": "...", "to_type": "element|page"} ]\\n'
        "}\\n\\n"
        f"PAGE URL: {url}\\n"
        f"PAGE TITLE: {title}\\n"
        f"MISSING_DOM_IDS: {missing_json}\\n\\n"
        "EXISTING_NKG_JSON:\\n"
        f"{existing_json}\\n\\n"
        "FULL HTML:\\n"
        f"{skeleton.get('html_content', '')}\\n"
    )


def build_reconcile_patch_prompt(skeleton: dict, existing_nkg: dict) -> str:
    url = skeleton.get("page_url", "")
    title = skeleton.get("page_title", "?")
    existing_json = json.dumps(existing_nkg, ensure_ascii=False)

    return (
        "Patch-only reconciliation after chunked extraction.\\n\\n"
        "IMPORTANT:\\n"
        "- Do NOT regenerate full JSON.\\n"
        "- Return only elements[] and triggers[] patch.\\n"
        "- Keep valid existing ids/selectors; add only missing useful items.\\n"
        "- Avoid duplicates.\\n\\n"
        "Return ONLY this JSON schema:\\n"
        "{\\n"
        '  "elements": [ {"id": "...", "desc": "...", "type": "...", "selector": "...", "parent_element_id": "optional_parent_id"} ],\\n'
        '  "triggers": [ {"from": "...", "to": "...", "to_type": "element|page"} ]\\n'
        "}\\n\\n"
        f"PAGE URL: {url}\\n"
        f"PAGE TITLE: {title}\\n\\n"
        "EXISTING_NKG_JSON:\\n"
        f"{existing_json}\\n\\n"
        "FULL HTML:\\n"
        f"{skeleton.get('html_content', '')}\\n"
    )


def build_selector_repair_prompt(skeleton: dict, elements_to_fix: list[dict]) -> str:
    url = skeleton.get("page_url", "")
    title = skeleton.get("page_title", "?")
    failed_json = json.dumps(elements_to_fix, ensure_ascii=False)

    return (
        "Repair failed selectors for existing NKG elements.\\n\\n"
        "IMPORTANT:\\n"
        "- Only repair ids listed in FAILED_ELEMENTS.\\n"
        "- Never change ids.\\n"
        "- Return only id + selector.\\n\\n"
        "Return ONLY this JSON schema:\\n"
        "{\\n"
        '  "elements": [ {"id": "...", "selector": "..."} ]\\n'
        "}\\n\\n"
        f"PAGE URL: {url}\\n"
        f"PAGE TITLE: {title}\\n"
        f"FAILED_ELEMENTS: {failed_json}\\n\\n"
        "FULL HTML:\\n"
        f"{skeleton.get('html_content', '')}\\n"
    )


# ── Pydantic Models ────────────────────────────────────────────────────────────
class ExtractRequest(BaseModel):
    filename: str
    skeleton: dict
    preferred_model: Optional[str] = None
    use_fallback: bool = True


class StreamExtractRequest(BaseModel):
    filename: str
    skeleton: dict
    preferred_model: Optional[str] = None
    use_fallback: bool = True
    show_thinking: bool = False


class PatchMissingRequest(BaseModel):
    filename: str
    skeleton: dict
    existing_nkg: dict
    missing_ids: list[str]
    preferred_model: Optional[str] = None
    use_fallback: bool = True


class ReconcilePatchRequest(BaseModel):
    filename: str
    skeleton: dict
    existing_nkg: dict
    preferred_model: Optional[str] = None
    use_fallback: bool = True


class SelectorRepairRequest(BaseModel):
    filename: str
    skeleton: dict
    elements_to_fix: list[dict]
    preferred_model: Optional[str] = None
    use_fallback: bool = True


class ExtractResponse(BaseModel):
    success: bool
    page_id: str
    data: Optional[dict] = None
    model_used: str
    error: Optional[str] = None
    raw_response: Optional[str] = None


class PatchMissingResponse(BaseModel):
    success: bool
    page_id: str
    data: Optional[dict] = None
    model_used: str
    added_elements: int = 0
    added_triggers: int = 0
    error: Optional[str] = None
    raw_response: Optional[str] = None


class GenericPatchResponse(BaseModel):
    success: bool
    page_id: str
    data: Optional[dict] = None
    model_used: str
    error: Optional[str] = None
    raw_response: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────────
def extract_json_from_text(text: str) -> dict:
    """
    Robustly extract a JSON object from raw LLM output.
    Handles:
      - <think>…</think> blocks (DeepSeek-R1, Qwen3 thinking mode)
      - Markdown code fences  ```json … ```
      - Leading/trailing prose
    """
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()

    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in LLM response")

    depth, end = 0, -1
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == -1:
        raise ValueError("Unclosed JSON object in LLM response")

    return json.loads(text[start:end])


def validate_nkg(data: dict) -> None:
    if "page" not in data:
        raise ValueError("Missing top-level 'page' key")
    for field in ("id", "title", "desc"):
        if field not in data["page"]:
            raise ValueError(f"page.{field} is missing")
    if not isinstance(data.get("elements"), list):
        raise ValueError("'elements' must be a list")
    if not isinstance(data.get("triggers"), list):
        raise ValueError("'triggers' must be a list")
    for el in data["elements"]:
        if "id" not in el or "desc" not in el:
            raise ValueError(f"Element missing 'id' or 'desc': {el}")


def validate_nkg_patch(data: dict) -> None:
    if not isinstance(data.get("elements", []), list):
        raise ValueError("Patch 'elements' must be a list")
    if not isinstance(data.get("triggers", []), list):
        raise ValueError("Patch 'triggers' must be a list")
    if "excluded" in data and not isinstance(data.get("excluded"), list):
        raise ValueError("Patch 'excluded' must be a list when provided")
    for el in data.get("elements", []):
        if "id" not in el or "desc" not in el:
            raise ValueError(f"Patch element missing 'id' or 'desc': {el}")


def validate_reconcile_patch(data: dict) -> None:
    if not isinstance(data.get("elements"), list):
        raise ValueError("Patch 'elements' must be a list")
    if not isinstance(data.get("triggers"), list):
        raise ValueError("Patch 'triggers' must be a list")
    for el in data["elements"]:
        if not isinstance(el, dict) or "id" not in el:
            raise ValueError(f"Patch element missing 'id': {el}")


def validate_selector_repair(data: dict) -> None:
    if not isinstance(data.get("elements"), list):
        raise ValueError("Selector repair 'elements' must be a list")
    for el in data["elements"]:
        if not isinstance(el, dict) or "id" not in el or "selector" not in el:
            raise ValueError(f"Selector repair item must include 'id' and 'selector': {el}")


def resolve_model_chain(preferred_model: Optional[str], use_fallback: bool) -> list[str]:
    if preferred_model:
        models = [preferred_model]
        if use_fallback and FALLBACK_MODEL != preferred_model:
            models.append(FALLBACK_MODEL)
        return models

    models = [PRIMARY_MODEL]
    if use_fallback and FALLBACK_MODEL != PRIMARY_MODEL:
        models.append(FALLBACK_MODEL)
    return models


def merge_patch(existing_nkg: dict, patch: dict) -> tuple[dict, int, int]:
    merged = {
        "page": existing_nkg.get("page", {}),
        "elements": list(existing_nkg.get("elements", [])),
        "triggers": list(existing_nkg.get("triggers", [])),
    }

    existing_ids = {el.get("id") for el in merged["elements"] if isinstance(el, dict)}
    existing_trigger_keys = {
        (tr.get("from"), tr.get("to"), tr.get("to_type"))
        for tr in merged["triggers"]
        if isinstance(tr, dict)
    }

    added_elements = 0
    for el in patch.get("elements", []):
        if not isinstance(el, dict):
            continue
        element_id = el.get("id")
        if element_id and element_id not in existing_ids:
            merged["elements"].append(el)
            existing_ids.add(element_id)
            added_elements += 1

    added_triggers = 0
    for tr in patch.get("triggers", []):
        if not isinstance(tr, dict):
            continue
        key = (tr.get("from"), tr.get("to"), tr.get("to_type"))
        if key not in existing_trigger_keys:
            merged["triggers"].append(tr)
            existing_trigger_keys.add(key)
            added_triggers += 1

    return merged, added_elements, added_triggers


async def call_ollama(
    model: str,
    skeleton: dict,
    client: httpx.AsyncClient,
    user_prompt: Optional[str] = None,
    system_prompt: Optional[str] = None,
) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt or SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt or build_user_prompt(skeleton)},
        ],
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 4096,
            "repeat_penalty": 1.1,
        },
    }
    resp = await client.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json=payload,
        timeout=TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def ensure_token(x_api_token: str) -> None:
    if x_api_token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


def ndjson_line(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


# ── Endpoints ──────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "ollama_url": OLLAMA_BASE_URL,
        "primary_model": PRIMARY_MODEL,
        "fallback_model": FALLBACK_MODEL,
    }


@app.get("/models")
async def list_models(x_api_token: str = Header(default="")):
    """Proxy to Ollama tag list so the notebook can confirm available models."""
    ensure_token(x_api_token)
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=30)
        resp.raise_for_status()
        return resp.json()


@app.post("/extract", response_model=ExtractResponse)
async def extract(req: ExtractRequest, x_api_token: str = Header(default="")):
    """
    Main extraction endpoint.
    1. Uses preferred_model when provided.
    2. Retries with fallback model based on use_fallback.
    3. Returns structured NKG data or a descriptive error.
    """
    ensure_token(x_api_token)
    filename = req.filename
    page_id = "/" + filename.replace(".html", "").replace("_", "/", 1)
    model_chain = resolve_model_chain(req.preferred_model, req.use_fallback)

    raw = ""
    async with httpx.AsyncClient() as client:
        for model in model_chain:
            logger.info("[%s] Requesting model: %s", filename, model)
            try:
                raw = await call_ollama(model, req.skeleton, client)
                data = extract_json_from_text(raw)
                validate_nkg(data)

                logger.info(
                    "[%s] ✓ %s  →  %d elements, %d triggers",
                    filename,
                    model,
                    len(data["elements"]),
                    len(data["triggers"]),
                )
                return ExtractResponse(
                    success=True,
                    page_id=page_id,
                    data=data,
                    model_used=model,
                )

            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                logger.error("[%s] HTTP error with %s: %s", filename, model, exc)
                if model == model_chain[-1]:
                    raise HTTPException(status_code=503, detail=str(exc))

            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("[%s] JSON error with %s: %s", filename, model, exc)
                if model == model_chain[-1]:
                    return ExtractResponse(
                        success=False,
                        page_id=page_id,
                        model_used=model,
                        error=str(exc),
                        raw_response=raw[:3000],
                    )

            except Exception as exc:
                logger.error("[%s] Unexpected error with %s: %s", filename, model, exc)
                if model == model_chain[-1]:
                    raise HTTPException(status_code=500, detail=str(exc))

    raise HTTPException(status_code=500, detail="Extraction loop exhausted")


@app.post("/extract/stream")
async def extract_stream(req: StreamExtractRequest, x_api_token: str = Header(default="")):
    """
    Streaming extraction endpoint.
    Emits NDJSON events:
      - {"event":"model", ...}
      - {"event":"token", "text":"..."}
      - {"event":"status", "message":"..."}
      - {"event":"final", "success":true|false, ...}
    """
    ensure_token(x_api_token)
    filename = req.filename
    page_id = "/" + filename.replace(".html", "").replace("_", "/", 1)
    model_chain = resolve_model_chain(req.preferred_model, req.use_fallback)

    async def event_stream() -> AsyncGenerator[str, None]:
        raw = ""
        async with httpx.AsyncClient() as client:
            for idx, model in enumerate(model_chain, start=1):
                yield ndjson_line(
                    {
                        "event": "model",
                        "model": model,
                        "attempt": idx,
                        "total_attempts": len(model_chain),
                    }
                )
                logger.info("[%s] Streaming request model: %s", filename, model)

                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": build_user_prompt(req.skeleton)},
                    ],
                    "stream": True,
                    "think": req.show_thinking,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 4096,
                        "repeat_penalty": 1.1,
                    },
                }

                try:
                    raw_parts: list[str] = []
                    async with client.stream(
                        "POST",
                        f"{OLLAMA_BASE_URL}/api/chat",
                        json=payload,
                        timeout=TIMEOUT_SECONDS,
                    ) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line:
                                continue

                            chunk = json.loads(line)
                            if chunk.get("error"):
                                raise ValueError(f"Ollama stream error: {chunk['error']}")

                            text = (chunk.get("message") or {}).get("content", "")
                            if text:
                                raw_parts.append(text)
                                yield ndjson_line({"event": "token", "text": text})

                    raw = "".join(raw_parts)
                    data = extract_json_from_text(raw)
                    validate_nkg(data)

                    logger.info(
                        "[%s] ✓ %s (stream)  →  %d elements, %d triggers",
                        filename,
                        model,
                        len(data["elements"]),
                        len(data["triggers"]),
                    )
                    yield ndjson_line(
                        {
                            "event": "final",
                            "success": True,
                            "page_id": page_id,
                            "model_used": model,
                            "data": data,
                        }
                    )
                    return

                except (httpx.HTTPError, httpx.TimeoutException) as exc:
                    logger.error("[%s] Streaming HTTP error with %s: %s", filename, model, exc)
                    if idx < len(model_chain):
                        yield ndjson_line(
                            {
                                "event": "status",
                                "message": f"Model {model} failed ({exc}); trying fallback...",
                            }
                        )
                        continue
                    yield ndjson_line(
                        {
                            "event": "final",
                            "success": False,
                            "page_id": page_id,
                            "model_used": model,
                            "error": str(exc),
                        }
                    )
                    return

                except (json.JSONDecodeError, ValueError) as exc:
                    logger.warning("[%s] Streaming JSON error with %s: %s", filename, model, exc)
                    if idx < len(model_chain):
                        yield ndjson_line(
                            {
                                "event": "status",
                                "message": f"Model {model} returned invalid JSON ({exc}); trying fallback...",
                            }
                        )
                        continue
                    yield ndjson_line(
                        {
                            "event": "final",
                            "success": False,
                            "page_id": page_id,
                            "model_used": model,
                            "error": str(exc),
                            "raw_response": raw[:3000],
                        }
                    )
                    return

                except Exception as exc:
                    logger.error("[%s] Unexpected streaming error with %s: %s", filename, model, exc)
                    if idx < len(model_chain):
                        yield ndjson_line(
                            {
                                "event": "status",
                                "message": f"Model {model} unexpected error ({exc}); trying fallback...",
                            }
                        )
                        continue
                    yield ndjson_line(
                        {
                            "event": "final",
                            "success": False,
                            "page_id": page_id,
                            "model_used": model,
                            "error": str(exc),
                        }
                    )
                    return

        yield ndjson_line(
            {
                "event": "final",
                "success": False,
                "page_id": page_id,
                "model_used": model_chain[-1] if model_chain else "",
                "error": "Extraction loop exhausted",
            }
        )

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@app.post("/extract/patch-missing", response_model=PatchMissingResponse)
async def patch_missing(req: PatchMissingRequest, x_api_token: str = Header(default="")):
    """
    Patch endpoint for insertion-only workflow.
    - Input: existing NKG + list of missing DOM ids.
    - Output: merged NKG where only missing elements/triggers are inserted.
    """
    ensure_token(x_api_token)
    filename = req.filename
    page_id = "/" + filename.replace(".html", "").replace("_", "/", 1)
    model_chain = resolve_model_chain(req.preferred_model, req.use_fallback)
    user_prompt = build_missing_patch_prompt(req.skeleton, req.existing_nkg, req.missing_ids)

    raw = ""
    async with httpx.AsyncClient() as client:
        for model in model_chain:
            logger.info("[%s] Patching missing ids with model: %s", filename, model)
            try:
                raw = await call_ollama(
                    model=model,
                    skeleton=req.skeleton,
                    client=client,
                    user_prompt=user_prompt,
                    system_prompt=PATCH_MISSING_SYSTEM_PROMPT,
                )
                patch_data = extract_json_from_text(raw)
                if "elements" not in patch_data:
                    patch_data["elements"] = []
                if "triggers" not in patch_data:
                    patch_data["triggers"] = []
                validate_nkg_patch(patch_data)
                merged, added_elements, added_triggers = merge_patch(req.existing_nkg, patch_data)
                validate_nkg(merged)

                logger.info(
                    "[%s] ✓ %s patch  →  +%d elements, +%d triggers",
                    filename,
                    model,
                    added_elements,
                    added_triggers,
                )
                return PatchMissingResponse(
                    success=True,
                    page_id=page_id,
                    data=merged,
                    model_used=model,
                    added_elements=added_elements,
                    added_triggers=added_triggers,
                )

            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                logger.error("[%s] HTTP error with %s: %s", filename, model, exc)
                if model == model_chain[-1]:
                    raise HTTPException(status_code=503, detail=str(exc))

            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("[%s] Patch JSON error with %s: %s", filename, model, exc)
                if model == model_chain[-1]:
                    return PatchMissingResponse(
                        success=False,
                        page_id=page_id,
                        model_used=model,
                        error=str(exc),
                        raw_response=raw[:3000],
                    )

            except Exception as exc:
                logger.error("[%s] Unexpected patch error with %s: %s", filename, model, exc)
                if model == model_chain[-1]:
                    raise HTTPException(status_code=500, detail=str(exc))

    raise HTTPException(status_code=500, detail="Patch loop exhausted")


@app.post("/extract/reconcile-patch", response_model=GenericPatchResponse)
async def reconcile_patch(req: ReconcilePatchRequest, x_api_token: str = Header(default="")):
    ensure_token(x_api_token)
    filename = req.filename
    page_id = "/" + filename.replace(".html", "").replace("_", "/", 1)
    model_chain = resolve_model_chain(req.preferred_model, req.use_fallback)
    user_prompt = build_reconcile_patch_prompt(req.skeleton, req.existing_nkg)

    raw = ""
    async with httpx.AsyncClient() as client:
        for model in model_chain:
            logger.info("[%s] Reconcile patch with model: %s", filename, model)
            try:
                raw = await call_ollama(
                    model=model,
                    skeleton=req.skeleton,
                    client=client,
                    user_prompt=user_prompt,
                    system_prompt=RECONCILE_PATCH_SYSTEM_PROMPT,
                )
                patch_data = extract_json_from_text(raw)
                validate_reconcile_patch(patch_data)
                return GenericPatchResponse(
                    success=True,
                    page_id=page_id,
                    data=patch_data,
                    model_used=model,
                )

            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                logger.error("[%s] Reconcile HTTP error with %s: %s", filename, model, exc)
                if model == model_chain[-1]:
                    raise HTTPException(status_code=503, detail=str(exc))

            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("[%s] Reconcile JSON error with %s: %s", filename, model, exc)
                if model == model_chain[-1]:
                    return GenericPatchResponse(
                        success=False,
                        page_id=page_id,
                        model_used=model,
                        error=str(exc),
                        raw_response=raw[:3000],
                    )

            except Exception as exc:
                logger.error("[%s] Unexpected reconcile error with %s: %s", filename, model, exc)
                if model == model_chain[-1]:
                    raise HTTPException(status_code=500, detail=str(exc))

    raise HTTPException(status_code=500, detail="Reconcile patch loop exhausted")


@app.post("/extract/repair-selectors", response_model=GenericPatchResponse)
async def repair_selectors(req: SelectorRepairRequest, x_api_token: str = Header(default="")):
    ensure_token(x_api_token)
    filename = req.filename
    page_id = "/" + filename.replace(".html", "").replace("_", "/", 1)
    model_chain = resolve_model_chain(req.preferred_model, req.use_fallback)
    user_prompt = build_selector_repair_prompt(req.skeleton, req.elements_to_fix)

    raw = ""
    async with httpx.AsyncClient() as client:
        for model in model_chain:
            logger.info("[%s] Selector repair with model: %s", filename, model)
            try:
                raw = await call_ollama(
                    model=model,
                    skeleton=req.skeleton,
                    client=client,
                    user_prompt=user_prompt,
                    system_prompt=SELECTOR_REPAIR_SYSTEM_PROMPT,
                )
                repair_data = extract_json_from_text(raw)
                validate_selector_repair(repair_data)
                return GenericPatchResponse(
                    success=True,
                    page_id=page_id,
                    data=repair_data,
                    model_used=model,
                )

            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                logger.error("[%s] Selector repair HTTP error with %s: %s", filename, model, exc)
                if model == model_chain[-1]:
                    raise HTTPException(status_code=503, detail=str(exc))

            except (json.JSONDecodeError, ValueError) as exc:
                logger.warning("[%s] Selector repair JSON error with %s: %s", filename, model, exc)
                if model == model_chain[-1]:
                    return GenericPatchResponse(
                        success=False,
                        page_id=page_id,
                        model_used=model,
                        error=str(exc),
                        raw_response=raw[:3000],
                    )

            except Exception as exc:
                logger.error("[%s] Unexpected selector repair error with %s: %s", filename, model, exc)
                if model == model_chain[-1]:
                    raise HTTPException(status_code=500, detail=str(exc))

    raise HTTPException(status_code=500, detail="Selector repair loop exhausted")


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "false").lower() == "true"

    uvicorn.run("server:app", host=host, port=port, reload=reload)
