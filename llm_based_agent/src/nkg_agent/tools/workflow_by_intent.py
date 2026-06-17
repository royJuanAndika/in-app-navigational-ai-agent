"""Search pre-computed navigational intents by semantic similarity.

Two-step pattern:
  1. ``search_intents(query)``     → shows top-N candidates; agent picks the right one.
  2. ``get_steps_for_intent(id)``  → fetches the full ordered step list for the chosen intent.

This split allows the agent to disambiguate when multiple similar intents exist
(e.g. "add employee via web" vs "add employee via mobile app").
"""

from langchain_core.tools import tool

from ..core.config import get_settings
from ..core.graph_db import vector_search_intents, get_intent_steps
from ..core.llm import get_query_embedding


@tool
def search_intents(query: str, top_n: int = 3) -> str:
    """Search for pre-computed navigational intents that match the user's question.

    Call this FIRST for any 'how do I...' or 'cara...' query.
    It returns the top matching intents with their type and whether they have
    steps — but NOT the steps themselves. Use ``get_steps_for_intent`` to
    fetch steps once you have identified the correct intent.

    If multiple similar intents are returned (e.g. web vs. mobile variants),
    prefer the one that matches the platform context (this is a web admin panel).

    Args:
        query:  The user's question or intent in natural language.
        top_n:  Number of candidates to return (default 3).
    """
    settings = get_settings()
    top_n = max(1, min(top_n, 5))  # clamp 1–5

    embedding = get_query_embedding(query, mode="intent")
    results = vector_search_intents(embedding, top_n=top_n)

    if not results:
        return f'No matching intents found for: "{query}"'

    threshold = settings.intent_search_threshold
    passed = [r for r in results if r["score"] >= threshold]

    if not passed:
        best = results[0]
        return (
            f'No confident intent match found for: "{query}"\n'
            f'Best score: {best["score"]:.3f} (threshold: {threshold:.3f})\n'
            "→ Fall back to search_elements_by_intent or find_page."
        )

    lines = [f"Found {len(passed)} intent candidate(s) for: \"{query}\"\n"]
    for i, r in enumerate(passed, 1):
        has_steps = r.get("has_steps", False)
        step_count = r.get("step_count", 0)
        intent_type = r.get("intent_type", "unknown")

        steps_info = f"{step_count} steps" if has_steps else "no steps (informational)"
        lines.append(
            f"{i}. [{intent_type}] \"{r['label']}\"\n"
            f"   intent_id : {r['intent_id']}\n"
            f"   score     : {r['score']:.3f}\n"
            f"   steps     : {steps_info}"
        )

    lines.append(
        "\n→ Call get_steps_for_intent(intent_id) with the most relevant intent_id above."
    )
    return "\n".join(lines)


@tool
def get_steps_for_intent(intent_id: str) -> str:
    """Fetch the full ordered step list for a specific navigational intent.

    Use this AFTER ``search_intents`` has returned candidates and you have
    identified the correct intent_id. Returns all HAS_STEP elements with
    their nkg_id, selector, action, and page.

    Args:
        intent_id: The exact intent_id returned by ``search_intents``.
    """
    steps = get_intent_steps(intent_id)

    if not steps:
        return (
            f'Intent "{intent_id}" has no steps in the knowledge graph.\n'
            "It may be informational — check its content with search_intents."
        )

    lines = [f"Steps for intent \"{intent_id}\" ({len(steps)} steps):\n"]
    for s in steps:
        lines.append(
            f"{s['order']}. [{s['action']}] {s['nkg_id']}\n"
            f"   Selector : {s['selector'] or 'N/A'}\n"
            f"   Text     : \"{s['text'] or ''}\"\n"
            f"   Page     : {s['page_id']}"
        )
    return "\n".join(lines)
