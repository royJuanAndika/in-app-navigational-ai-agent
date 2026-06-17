"""Find elements that TRIGGER this element (backward lookup)."""

from langchain_core.tools import tool

from ..core.graph_db import get_incoming_triggers


@tool
def find_trigger_prerequisites(nkg_id: str) -> str:
    """Find all UI elements that TRIGGER (activate/reveal) this element.
    
    Use this before recommending a hidden or modal element to discover what
    the user must click first to make that element visible.
    
    For example, if you want to guide a user to select from a dropdown option,
    first find its trigger (the toggle button that opens the dropdown).

    Args:
        nkg_id: The unique NKG identifier of the target element.
                Format: "{page_id}/{element_id}",
                e.g. "/customer/employee/dropdown_dept_option_eng".
    """
    triggers = get_incoming_triggers(nkg_id)

    if not triggers:
        return (
            f"No prerequisites found for: \"{nkg_id}\".\n"
            "This element is not triggered by other elements (it appears directly on the page)."
        )

    lines = [
        f"Prerequisites for: {nkg_id}",
        f"Found {len(triggers)} element(s) that TRIGGER this element:\n",
    ]

    for t in triggers:
        lines.append(
            f"• {t['type'].upper()}: {t['nkg_id']}\n"
            f"  Description: {t['description']}\n"
            f"  Text/Label: {t.get('text', '(none)')}\n"
            f"  Selector: {t.get('selector', 'N/A')}\n"
        )

    lines.append(
        "\n✓ TIP: Include these trigger elements in your guidance BEFORE "
        "recommending the target element."
    )

    return "\n".join(lines)
