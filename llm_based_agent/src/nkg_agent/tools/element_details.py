"""Get detailed info about a specific element + what it triggers."""

from langchain_core.tools import tool

from ..core.graph_db import get_element_info


@tool
def get_element_details(nkg_id: str) -> str:
    """Get detailed information about a specific UI element, including
    what it triggers when clicked or interacted with.

    Args:
        nkg_id: The unique NKG identifier of the element.
                Format: "{page_id}/{element_id}",
                e.g. "/customer/employee/btn_add".
    """
    info = get_element_info(nkg_id)

    if info is None:
        return (
            f"Element not found: \"{nkg_id}\".\n"
            "No element with this NKG ID exists. Check the ID and try again."
        )

    lines = [
        f"Element: {info['nkg_id']}",
        f"  Page:        {info['page_id']}",
        f"  Type:        {info['type']}",
        f"  Description: {info['description']}",
        f"  Selector:    {info['selector']}",
        f"  Text:        \"{info['text']}\"" if info.get("text") else "  Text:        (none)",
    ]

    triggers = info.get("triggers", [])
    if triggers:
        lines.append(f"\nTriggers ({len(triggers)}):")
        for t in triggers:
            target_label = t.get("target_title") or t.get("target_desc") or t.get("target_id", "?")
            lines.append(
                f"  → {t['target_type']}: {t['target_id']}\n"
                f"    Description: {target_label}\n"
                f"    Selector: {t.get('target_selector', 'N/A')}"
            )
    else:
        lines.append("\nTriggers: none (this element does not trigger other elements or pages)")

    return "\n".join(lines)
