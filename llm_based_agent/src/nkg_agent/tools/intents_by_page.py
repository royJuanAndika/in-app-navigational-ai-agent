"""Get all navigational intents associated with a specific page."""

from langchain_core.tools import tool

from ..core.graph_db import get_intents_for_page


@tool
def get_intents_by_page(page_id: str) -> str:
    """Get all known navigational workflows and info topics for a page.

    Use when the user's current_page is known and you want to proactively
    suggest what they can do on this page, or check if a known workflow
    covers their request.

    Args:
        page_id: The exact page path, e.g. "/customer/employee"
    """
    intents = get_intents_for_page(page_id)

    if not intents:
        return f"No specific navigational intents found for page: \"{page_id}\""

    lines = [f"Found {len(intents)} intents for page {page_id}:\n"]
    for i, intent in enumerate(intents, 1):
        lines.append(
            f"{i}. [{intent['intent_type']}] {intent['label']} (ID: {intent['intent_id']})"
        )

    return "\n".join(lines)
