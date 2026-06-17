"""Get primary form fields on a page."""

from langchain_core.tools import tool

from ..core.graph_db import get_form_fields


@tool
def get_form_fields_on_page(page_id: str) -> str:
    """Get the main form controls on a page.

    Use this after the user is already on the relevant page or after opening a
    modal/form that belongs to the current page. It focuses on actionable
    fields such as inputs, selects, and textareas.

    Args:
        page_id: Page id where the form is shown.
    """
    fields = get_form_fields(page_id)

    if len(fields) > 50:
        # Group by type for summary
        from collections import Counter
        counts = Counter(f['type'] for f in fields)
        summary = ", ".join([f"{count} {t}" for t, count in counts.items()])
        
        lines = [
            f"Found {len(fields)} fields on page: {page_id} ({summary}).",
            "Showing the first 50 fields below. Use search_elements_by_intent or search_elements_by_text to find specific fields if not listed.",
            ""
        ]
        fields = fields[:50]
    else:
        lines = [f"Form fields on page: {page_id}", f"Found {len(fields)} field(s):\n"]

    for field in fields:
        lines.append(
            f"• {field['type'].upper()}: {field['nkg_id']}\n"
            f"  Description: {field['description']}\n"
            f"  Selector: {field['selector']}\n"
            f"  Text: {field.get('text') or '(none)'}\n"
        )
    return "\n".join(lines)
