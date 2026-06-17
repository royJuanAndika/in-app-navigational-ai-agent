"""Semantic vector search — find UI elements by user intent."""

from langchain_core.tools import tool

from ..core.config import get_settings
from ..core.graph_db import vector_search
from ..core.llm import get_query_embedding


@tool
def search_elements_by_intent(query: str) -> str:
    """Search for UI elements that match the user's navigation intent using
    semantic vector similarity.

    Use this tool when the user describes what they want to do in natural
    language (e.g. "tambah karyawan baru", "lihat laporan absensi").

    Args:
        query: The user's intent or action description in natural language.
    """
    settings = get_settings()

    # 1. Embed the query
    embedding = get_query_embedding(query)

    # 2. Vector search
    results = vector_search(embedding, top_n=settings.search_top_n)

    if not results:
        return (
            f"No elements found matching the intent: \"{query}\".\n"
            "Try rephrasing or use find_page / search_elements_by_text."
        )

    # 3. Format
    lines = [f"Found {len(results)} matching elements:\n"]
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. [Score: {r['score']:.3f}] {r['nkg_id']}\n"
            f"   Page: {r['page_id']}\n"
            f"   Type: {r['type']}\n"
            f"   Description: {r['description']}\n"
            f"   Selector: {r['selector']}\n"
            f"   Text: \"{r['text']}\""
        )

    return "\n".join(lines)
