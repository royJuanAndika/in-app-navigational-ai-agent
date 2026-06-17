"""Get all UI elements on a specific page."""

from langchain_core.tools import tool

from ..core.graph_db import get_page_elements, get_page_info


_MAX_DISPLAY = 50  # truncate large pages to avoid flooding the LLM context


@tool
def get_page_content(page_id: str) -> str:
    """Get all UI elements on a specific page of the application.

    Use this when you know the page path and want to see what interactive
    elements are available on that page.

    Args:
        page_id: The exact page path/route, e.g. "/customer/employee"
                 or "/customer/dashboard".
                 Use the find_page tool first if you only have a keyword.
    """
    # 1. Page info
    page = get_page_info(page_id)
    if page is None:
        return (
            f"Page not found: \"{page_id}\".\n"
            "Use find_page to search for the correct page path."
        )

    # 2. Elements
    elements = get_page_elements(page_id)

    if not elements:
        return (
            f"Page: {page['page_id']} ({page['title']})\n"
            f"Description: {page['description']}\n\n"
            "This page has no interactive elements in the knowledge graph."
        )

    # 3. Group by type
    by_type: dict[str, list[dict]] = {}
    for el in elements:
        el_type = el.get("type", "other")
        by_type.setdefault(el_type, []).append(el)

    # 4. Format
    lines = [
        f"Page: {page['page_id']} — {page['title']}",
        f"Description: {page['description']}",
        f"Total elements: {len(elements)}",
        "",
    ]

    shown = 0
    for el_type, items in sorted(by_type.items()):
        lines.append(f"── {el_type.upper()} ({len(items)}) ──")
        for el in items:
            if shown >= _MAX_DISPLAY:
                break
            text_part = f' | Text: "{el["text"]}"' if el.get("text") else ""
            lines.append(
                f"  • {el['element_id']} [{el['selector']}] "
                f"— {el['description']}{text_part}"
            )
            shown += 1
        if shown >= _MAX_DISPLAY:
            break

    remaining = len(elements) - shown
    if remaining > 0:
        lines.append(
            f"\n(Showing {shown} of {len(elements)} elements. "
            f"{remaining} more available — use search tools to narrow down.)"
        )

    return "\n".join(lines)
