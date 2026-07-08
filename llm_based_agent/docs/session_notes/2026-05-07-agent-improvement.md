# 2026-05-07 Agent Improvements

## Summary
- Hardened JSON extraction in the agent response parser to reduce parsing failures.
- Reordered tool priority list to match the prompt guidance.
- Added page-filtered candidate search and bounded fallbacks in fuzzy text search.
- Updated implementation plan docs to reflect 9 tools and JSON-based guidance output.
- Strengthened prompt to require both trigger and target steps when prerequisites are found.
- Added prompt rules to always include modal/form steps and return guidance for field queries.
- Added retry/backoff handling for transient 502 errors during LLM streaming.
- Added post-processing to insert missing modal/form target steps when trigger prerequisites are used.
- Added a fallback that inserts trigger prerequisites and marks tool usage when hidden elements appear in guidance.

## Files Touched
- llm_based_agent/src/nkg_agent/agent/graph.py
- llm_based_agent/src/nkg_agent/agent/prompts.py
- llm_based_agent/src/nkg_agent/core/graph_db.py
- llm_based_agent/src/nkg_agent/tools/text_search.py
- llm_based_agent/src/nkg_agent/tools/__init__.py
- llm_based_agent/docs/implementation_plan/05_agent_tools.md
- llm_based_agent/docs/implementation_plan/06_agent_and_prompts.md
- llm_based_agent/docs/implementation_plan/08_verification.md
- llm_based_agent/docs/implementation_plan/README.md
