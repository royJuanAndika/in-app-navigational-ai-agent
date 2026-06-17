"""Search pages by title or URL keyword."""

from langchain_core.tools import tool

from ..core.graph_db import find_pages


@tool
def find_page(search_term: str) -> str:
    """Search for a page by its title or URL path keyword.

    Use this when the user mentions a page or section of the application
    by name (e.g. "karyawan", "absensi", "laporan", "pengaturan").

    Args:
        search_term: A keyword to search in page titles and URL paths.
    """
    results = find_pages(search_term)

    if not results:
        return (
            f"No pages found matching \"{search_term}\".\n"
            "Try a broader keyword or use search_elements_by_intent."
        )

    lines = [f"Found {len(results)} pages matching \"{search_term}\":\n"]
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. {r['page_id']} — {r['title']} "
            f"({r['element_count']} elements)"
        )

    return "\n".join(lines)
