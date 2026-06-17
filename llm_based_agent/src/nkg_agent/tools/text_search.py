"""Fuzzy text search on element inner text using Levenshtein distance."""

from langchain_core.tools import tool
from rapidfuzz import fuzz

from ..core.config import get_settings
from ..core.graph_db import get_all_element_texts, text_search_elements


@tool
def search_elements_by_text(text: str, page_id: str | None = None) -> str:
    """Search for UI elements by their visible text content using fuzzy
    matching (tolerant of typos and partial matches).

    Use this when the user mentions a specific button label, menu item,
    or text they can see on the screen.

    Args:
        text: The visible text to search for (fuzzy match).
              Examples: "Tambah Karyawan", "Simpan", "Ekspor"
        page_id: Optional. Limit search to a specific page path.
                 If not provided, searches all pages.
    """
    settings = get_settings()

    # Strategy 1: try Neo4j CONTAINS first for a fast broad match
    candidates = text_search_elements(text, limit=200, page_id=page_id)

    # Strategy 2: if page_id given or CONTAINS returned nothing, get all texts
    if not candidates:
        candidates = get_all_element_texts(page_id, limit=500)

    if not candidates:
        scope = f" on page {page_id}" if page_id else ""
        return f"No elements with visible text found{scope}."

    # Score each candidate with Levenshtein partial ratio
    scored: list[tuple[int, dict]] = []
    for el in candidates:
        el_text = el.get("text", "")
        if not el_text:
            continue
        score = fuzz.token_sort_ratio(text.lower(), el_text.lower())
        if score >= settings.fuzzy_match_threshold:
            scored.append((score, el))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        scope = f" on page {page_id}" if page_id else ""
        return (
            f"No elements with text similar to \"{text}\" found{scope}.\n"
            "Try search_elements_by_intent for a semantic search instead."
        )

    # Return top 10
    top = scored[:10]
    lines = [f"Found {len(scored)} elements matching \"{text}\" (showing top {len(top)}):\n"]
    for i, (score, el) in enumerate(top, 1):
        lines.append(
            f"{i}. [Match: {score}%] {el['nkg_id']}\n"
            f"   Page: {el['page_id']}\n"
            f"   Type: {el.get('type', '?')}\n"
            f"   Selector: {el.get('selector', '?')}\n"
            f"   Text: \"{el['text']}\"\n"
            f"   Description: {el.get('description', '')}"
        )

    return "\n".join(lines)
