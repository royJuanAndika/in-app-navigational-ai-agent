"""Get elements contained inside a page or container element."""

from langchain_core.tools import tool

from ..core.graph_db import get_container_elements


@tool
def get_container_content(nkg_id: str) -> str:
    """Get all UI elements contained inside a page or nested container.

    Use this when a modal, section, tab, or expandable container is already
    known and you need to inspect the fields inside it. This performs a nested
    traversal so descendants inside the container are included.

    Args:
        nkg_id: Page id or container nkg_id.
    """
    items = get_container_elements(nkg_id)

    if not items:
        return (
            f"No contained elements found for: \"{nkg_id}\".\n"
            "The container may not exist or it may not contain direct child elements."
        )

    lines = [f"Container: {nkg_id}", f"Found {len(items)} contained element(s):\n"]
    for item in items:
        lines.append(
            f"• {item['type'].upper()}: {item['nkg_id']}\n"
            f"  Description: {item['description']}\n"
            f"  Selector: {item['selector']}\n"
            f"  Text: {item.get('text') or '(none)'}\n"
        )
    return "\n".join(lines)
