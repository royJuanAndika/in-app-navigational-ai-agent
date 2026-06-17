"""
Agent tools — all tools exposed to the LangGraph ReAct agent.

Import ``ALL_TOOLS`` to get the list used by ``create_react_agent``.
"""

from .workflow_by_intent import search_intents, get_steps_for_intent
from .intents_by_page import get_intents_by_page
from .semantic_search import search_elements_by_intent
from .page_content import get_page_content
from .element_details import get_element_details
from .find_page import find_page
from .text_search import search_elements_by_text
from .find_trigger_prerequisites import find_trigger_prerequisites
from .container_content import get_container_content
from .form_fields import get_form_fields_on_page
from .cypher_query import execute_cypher_read_query

ALL_TOOLS = [
    search_intents,           # Priority 1 — find top-N intent candidates
    get_steps_for_intent,     # Priority 2 — expand chosen intent into steps
    get_intents_by_page,      # Priority 3 — page-scoped intent discovery
    search_elements_by_intent,
    find_page,
    get_element_details,
    find_trigger_prerequisites,
    get_form_fields_on_page,
    get_container_content,
    get_page_content,
    search_elements_by_text,
    execute_cypher_read_query,
]

__all__ = [
    "ALL_TOOLS",
    "search_intents",
    "get_steps_for_intent",
    "get_intents_by_page",
    "search_elements_by_intent",
    "get_page_content",
    "get_element_details",
    "find_page",
    "search_elements_by_text",
    "find_trigger_prerequisites",
    "get_container_content",
    "get_form_fields_on_page",
    "execute_cypher_read_query",
]
