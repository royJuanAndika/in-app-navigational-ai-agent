"""
LangGraph ReAct agent for in-app navigation guidance.

Uses ``langgraph.prebuilt.create_react_agent`` which builds a StateGraph
with two nodes (``agent`` and ``tools``) and conditional edges.
"""

import asyncio
import json
import logging
import re
import time
from pathlib import Path

from langchain_core.callbacks import StdOutCallbackHandler
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from ..core.graph_db import enrich_guidance_steps, get_element_info, get_incoming_triggers
from ..core.llm import get_llm
from ..tools import ALL_TOOLS
from .prompts import SYSTEM_PROMPT, REFORMAT_PROMPT

logger = logging.getLogger(__name__)

LOG_FILE_PATH = Path(__file__).resolve().parents[3] / "agent_responses.log"


def log_agent_response(content: str, user_message: str | None = None, is_reformat: bool = False):
    try:
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write("\n" + "="*60 + "\n")
            if user_message:
                f.write(f"REQUEST: {user_message}\n\n")
                f.write("="*60 + "\n")
            
            label = "AGENT FINAL RESPONSE MESSAGE (AFTER REFORMAT):" if is_reformat else "AGENT FINAL RESPONSE MESSAGE:"
            f.write(f"{label}\n\n")
            f.write(content + "\n")
            f.write("="*60 + "\n")
    except Exception as e:
        logger.error("Failed to write agent response to log file: %s", e)


# Safe print function for Windows/Linux terminal
def safe_print(text, end="\n", flush=True):
    try:
        print(text, end=end, flush=flush)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'replace').decode('ascii'), end=end, flush=flush)

# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def create_agent():
    """Create the In-App Navigational Agent with all tools.

    Returns a compiled LangGraph that can be invoked with::

        result = agent.invoke({"messages": [HumanMessage(content="...")]})
    """
    llm = get_llm()

    agent = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=SystemMessage(content=SYSTEM_PROMPT),
    )

    logger.info(
        "Agent created with %d tools: %s",
        len(ALL_TOOLS),
        [t.name for t in ALL_TOOLS],
    )
    return agent


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*(.*?)\s*```",
    re.DOTALL | re.IGNORECASE,
)

_FALLBACK_RESPONSE = {
    "message": (
        "Maaf, saya mengalami kesulitan memformat respons saat ini. "
        "Silakan coba lagi."
    ),
    "type": "error",
    "guidance": [],
}


def _extract_json_candidate(raw: str) -> str | None:
    # 1. Try to find the last JSON code block
    matches = list(_JSON_FENCE_RE.finditer(raw))
    if matches:
        block = matches[-1].group(1).strip()
        # Ensure it's actually JSON (starts with {)
        brace_start = block.find("{")
        brace_end = block.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            return block[brace_start : brace_end + 1]
        return block or None

    # 2. If no code block, try to find the largest outer braces { ... }
    # This handles cases where the model forgets code fences or includes text before/after
    brace_start = raw.find("{")
    brace_end = raw.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        return raw[brace_start : brace_end + 1]

    # 3. Fallback: simple scan if above failed
    return None


def _safe_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_agent_response(raw: str, enrich: bool = True) -> dict:
    """Extract the structured JSON block from the agent's final text.

    The prompt instructs the LLM to always end its response with a fenced
    JSON block.  This function finds that block, parses it, and validates
    the required fields.

    After parsing, if ``enrich=True``, the function resolves ``page_url``,
    ``selector``, and ``element_id`` for each guidance step by querying the
    NKG via a single batch Cypher call.  The LLM only needs to output
    ``nkg_id`` faithfully — all other navigation metadata comes from the graph.

    If parsing fails entirely, a safe fallback dict is returned.

    Args:
        raw:    The raw text content of the agent's final ``AIMessage``.
        enrich: If True (default), call Neo4j to enrich guidance steps.

    Returns:
        dict with keys: ``message``, ``type``, ``guidance``.
    """
    # ── 1. Extract JSON block ──────────────────────────────────────────
    json_str = _extract_json_candidate(raw)
    
    if not json_str:
        # If no JSON found, log it and return the raw text as the message
        # This prevents the user from seeing a "format error" when the LLM
        # actually gave a useful (but unformatted) text response.
        logger.warning("No JSON block found in agent response (length %d). Raw content: %s", len(raw), raw[:1000])
        return {
            "message": raw if raw.strip() else _FALLBACK_RESPONSE["message"],
            "type": "info", # fallback type
            "guidance": [],
        }

    try:
        # 1. First pass: standard JSON load
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # 2. Second pass: Try to fix unescaped newlines in "message" or "instruction" fields
        # Models often put raw newlines inside JSON strings which is invalid JSON.
        try:
            # This regex looks for text between quotes and replaces raw newlines with \n
            # It's a bit naive but handles the most common case of unescaped newlines in values.
            import re as standard_re
            
            def fix_newlines(match):
                return match.group(0).replace('\n', '\\n').replace('\r', '')
            
            # Match content inside double quotes: "..."
            # Using a lookbehind/lookahead to avoid matching keys if possible, but 
            # keys shouldn't have newlines anyway.
            fixed_str = standard_re.sub(r'":\s*"([^"]*)"', lambda m: '": "' + m.group(1).replace('\n', '\\n').replace('\r', '') + '"', json_str)
            
            # Also clean up trailing commas
            fixed_str = standard_re.sub(r",\s*([\]}])", r"\1", fixed_str)
            
            data = json.loads(fixed_str)
        except Exception as exc2:
            logger.warning("All JSON fix attempts failed: %s", exc2)
            return {
                "message": raw if raw.strip() else _FALLBACK_RESPONSE["message"],
                "type": "info",
                "guidance": [],
            }

    # ── 2. Normalise required fields ──────────────────────────────────
    response: dict = {
        "message": str(data.get("message", raw)),
        "type": str(data.get("type", "info")),
        "guidance": [],
    }

    raw_guidance = data.get("guidance", [])
    if isinstance(raw_guidance, list):
        for item in raw_guidance:
            if not isinstance(item, dict):
                continue
            response["guidance"].append(
                {
                    "step": _safe_int(item.get("step", 0)),
                    "instruction": str(item.get("instruction", "")),
                    "nkg_id": item.get("nkg_id") or None,
                    # These will be populated by the enricher below
                    "page_url": None,
                    "selector": None,
                    "element_id": None,
                }
            )

    # ── 3. Enrich from Neo4j (single batch) ────────────────────────────
    if enrich and response["guidance"]:
        nkg_ids = [
            step["nkg_id"]
            for step in response["guidance"]
            if step["nkg_id"] is not None
        ]
        if nkg_ids:
            enriched = enrich_guidance_steps(nkg_ids)
            for step in response["guidance"]:
                nkg_id = step["nkg_id"]
                if nkg_id and nkg_id in enriched:
                    step.update(enriched[nkg_id])
                    logger.debug(
                        "Enriched step %d: nkg_id=%s page_url=%s selector=%s",
                        step["step"], nkg_id, step["page_url"], step["selector"],
                    )
                elif nkg_id:
                    logger.warning(
                        "nkg_id not found in NKG: %s (step %d)", nkg_id, step["step"]
                    )

    return response


# NOTE: _ensure_trigger_prerequisites and _inject_missing_trigger_targets were
# removed. They were post-processing the LLM's guidance output by injecting
# extra steps from Neo4j trigger queries, which caused the LLM's clean
# response to be bloated with irrelevant sibling elements (e.g. "Tambah Data"
# buttons for family/emergency/education tabs when asking about the main
# Add Employee form). The LLM is the authoritative source for step ordering.
#
# The imports for get_element_info and get_incoming_triggers are kept in case
# they are needed by tools in the future.


# ---------------------------------------------------------------------------
# Main chat function
# ---------------------------------------------------------------------------


def chat(
    agent,
    user_message: str,
    current_page: str | None = None,
    history: list[dict] | None = None,
) -> dict:
    """Send a message to the agent and return a structured response.

    Args:
        agent: The compiled LangGraph agent.
        user_message: The user's natural language message.
        current_page: Optional current page path (e.g. "/customer/dashboard").
        history: Optional list of previous messages for context.
            Each item is ``{"role": "user"|"assistant", "content": "..."}``.

    Returns:
        dict with keys: ``message``, ``type``, ``guidance``,
        ``tools_used``, ``duration_ms``, ``all_messages``.
    """
    # Build context prefix
    ctx_parts: list[str] = []
    if current_page:
        ctx_parts.append(f"[Pengguna sedang di halaman: {current_page}]")
    if history:
        # Inject last N turns as a conversation history block
        history_lines = []
        for turn in history[-10:]:  # cap at 10 turns to control token usage
            role_label = "Pengguna" if turn.get("role") == "user" else "Asisten"
            history_lines.append(f"{role_label}: {turn.get('content', '')}")
        if history_lines:
            ctx_parts.append("[Riwayat percakapan sebelumnya]:\n" + "\n".join(history_lines))

    if ctx_parts:
        full_message = "\n\n".join(ctx_parts) + "\n\n" + user_message
    else:
        full_message = user_message

    t0 = time.time()
    
    safe_print("\n" + "="*60)
    safe_print("AGENT THINKING PROCESS STARTED")
    safe_print("="*60)

    tools_used: list[str] = []
    final_message = None
    all_messages = []
    
    safe_print("\nAGENT IS THINKING\n\n")

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            for event, chunk in agent.stream(
                {"messages": [HumanMessage(content=full_message)]},
                stream_mode=["messages", "updates"],
            ):
                if event == "messages":
                    msg_chunk, metadata = chunk
                    # Stream the standard text live to the console
                    if msg_chunk.content:
                        safe_print(msg_chunk.content, end="", flush=True)

                    # If the LLM is generating a tool call, stream its raw JSON arguments live
                    if hasattr(msg_chunk, "tool_call_chunks") and msg_chunk.tool_call_chunks:
                        for tcc in msg_chunk.tool_call_chunks:
                            if "args" in tcc and tcc["args"]:
                                safe_print(tcc["args"], end="", flush=True)

                elif event == "updates":
                    if "agent" in chunk:
                        msg = chunk["agent"]["messages"]
                        if isinstance(msg, list):
                            msg = msg[-1]
                        all_messages.append(msg)
                        final_message = msg

                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                tools_used.append(tc["name"])
                                safe_print(f"\n\n[TOOL CALL] {tc['name']}")
                                safe_print(f"   Args: {json.dumps(tc['args'], indent=2)}")
                                safe_print("\nAGENT IS THINKING: ", end="", flush=True)

                    elif "tools" in chunk:
                        msg = chunk["tools"]["messages"]
                        if isinstance(msg, list):
                            msg = msg[-1]
                        all_messages.append(msg)

                        result_text = msg.content
                        safe_print(f"\n\n[TOOL RESULT] ({msg.name}):")
                        if len(result_text) > 800:
                            safe_print(f"   {result_text[:800]}\n   ... [TRUNCATED]")
                        else:
                            safe_print(f"   {result_text}")
                        safe_print("\nAGENT IS THINKING: ", end="", flush=True)
            break
        except Exception as exc:
            message = str(exc)
            if "Bad Gateway" in message or "502" in message:
                if attempt < max_retries:
                    backoff = 2 ** attempt
                    logger.warning("LLM gateway error, retrying in %ds: %s", backoff, message)
                    time.sleep(backoff)
                    continue
            raise

    duration_ms = int((time.time() - t0) * 1000)
    
    safe_print("\n" + "="*60)
    safe_print(f"AGENT FINISHED in {duration_ms}ms")
    safe_print("="*60 + "\n")

    logger.info(
        "Chat completed in %dms — tools used: %s",
        duration_ms,
        tools_used or "(none)",
    )

    # ── 4. Parse structured response and validate ───────────────────
    if final_message and hasattr(final_message, "content") and final_message.content:
        log_agent_response(final_message.content, user_message)

        parsed = parse_agent_response(final_message.content)
        
        # If parsing failed or result is a fallback, try to reprompt once
        if _extract_json_candidate(final_message.content) is None or parsed.get("type") == "error":
            logger.warning("Agent response was malformed. Reprompting with REFORMAT_PROMPT...")
            
            try:
                # Use a CLEAN history for reformatting: just the faulty response and the reformat command.
                # This prevents the model from trying to "solve" the query again and focuses it on the fix.
                retry_messages = [
                    final_message,
                    HumanMessage(content=REFORMAT_PROMPT)
                ]
                
                # Bypass the React Agent loop entirely and call the raw LLM directly.
                # This avoids tools/system prompt interference and ensures clean JSON generation.
                llm = get_llm()
                final_message = llm.invoke(retry_messages)
                
                log_agent_response(final_message.content, is_reformat=True)

                # Re-parse the new message
                parsed = parse_agent_response(final_message.content)
            except Exception as retry_exc:
                logger.error("Reprompt failed: %s", retry_exc)
    else:
        logger.error("Agent failed to produce a final message.")
        parsed = {
            **_FALLBACK_RESPONSE,
            "message": "Maaf, sistem sedang mengalami kendala teknis dan tidak dapat memberikan jawaban. Silakan coba lagi nanti."
        }

    return {
        **parsed,
        "tools_used": tools_used,
        "duration_ms": duration_ms,
        "all_messages": all_messages,
    }


async def achat_stream(
    agent,
    user_message: str,
    current_page: str | None = None,
    history: list[dict] | None = None,
):
    """Async generator that yields Server-Sent Events (SSE) for the chat process.

    Yields:
        SSE formatted strings (e.g. "event: tool_call\\ndata: {...}\\n\\n")
    """
    ctx_parts: list[str] = []
    if current_page:
        ctx_parts.append(f"[Pengguna sedang di halaman: {current_page}]")
    if history:
        history_lines = []
        for turn in history[-10:]:
            role_label = "Pengguna" if turn.get("role") == "user" else "Asisten"
            history_lines.append(f"{role_label}: {turn.get('content', '')}")
        if history_lines:
            ctx_parts.append("[Riwayat percakapan sebelumnya]:\n" + "\n".join(history_lines))

    if ctx_parts:
        full_message = "\n\n".join(ctx_parts) + "\n\n" + user_message
    else:
        full_message = user_message

    t0 = time.time()
    tools_used = []
    trigger_targets = []
    final_message = None

    try:
        # We yield a starting event
        yield f"event: start\ndata: {json.dumps({'status': 'started'})}\n\n"

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                async for chunk in agent.astream(
                    {"messages": [HumanMessage(content=full_message)]},
                    stream_mode="updates",
                ):
                    if "agent" in chunk:
                        msg = chunk["agent"]["messages"]
                        if isinstance(msg, list):
                            msg = msg[-1]
                        final_message = msg

                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                tools_used.append(tc["name"])
                                if tc.get("name") == "find_trigger_prerequisites":
                                    nkg_id = tc.get("args", {}).get("nkg_id")
                                    if nkg_id:
                                        trigger_targets.append(nkg_id)
                                yield f"event: tool_call\ndata: {json.dumps({'tool': tc['name'], 'args': tc['args']})}\n\n"
                    elif "tools" in chunk:
                        msg = chunk["tools"]["messages"]
                        if isinstance(msg, list):
                            msg = msg[-1]
                        # Truncate result to avoid massive SSE payloads
                        result_text = msg.content
                        if len(result_text) > 200:
                            result_text = result_text[:197] + "..."
                        yield f"event: tool_result\ndata: {json.dumps({'tool': msg.name, 'result': result_text})}\n\n"
                break
            except Exception as exc:
                message = str(exc)
                if "Bad Gateway" in message or "502" in message:
                    if attempt < max_retries:
                        backoff = 2 ** attempt
                        logger.warning("LLM gateway error, retrying in %ds: %s", backoff, message)
                        await asyncio.sleep(backoff)
                        continue
                raise

        # Final message processing
        if final_message and hasattr(final_message, "content"):
            log_agent_response(final_message.content, user_message)

            parsed = parse_agent_response(final_message.content)
            
            # If parsing failed or result is a fallback, try to reprompt once
            if _extract_json_candidate(final_message.content) is None or parsed.get("type") == "error":
                logger.warning("Async agent response malformed. Reprompting with REFORMAT_PROMPT...")
                try:
                    # Bypass the React Agent loop entirely and call the raw LLM directly.
                    # This avoids tools/system prompt interference and ensures clean JSON generation.
                    llm = get_llm()
                    final_message = await llm.ainvoke([final_message, HumanMessage(content=REFORMAT_PROMPT)])
                    
                    log_agent_response(final_message.content, is_reformat=True)

                    parsed = parse_agent_response(final_message.content)
                except Exception as retry_exc:
                    logger.error("Async reprompt failed: %s", retry_exc)

            duration_ms = int((time.time() - t0) * 1000)
            final_payload = {
                **parsed,
                "tools_used": tools_used,
                "duration_ms": duration_ms,
            }
            yield f"event: complete\ndata: {json.dumps(final_payload)}\n\n"
        else:
            yield f"event: error\ndata: {json.dumps({'message': 'No response generated'})}\n\n"

    except Exception as exc:
        logger.exception("Stream error")
        yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"
