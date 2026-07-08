from typing import List, Dict
import json

SYSTEM_PROMPT = """You are a UI Navigation Expert. Your task is to match navigational step drafts to real UI elements from a provided page element list.

CONTEXT:
You are building a sequential "how-to" guide for a complex HR SaaS platform. 
The user has provided:
1. A list of UI elements on the current page, including their hierarchy (Parent) and behavior (Triggers).
2. A draft of steps assigned to this page.
3. (Optional) Steps that have already been resolved for previous pages in the sequence.

RULES:
1. MATCHING: Match each step draft to the single best `nkg_id` from the element list.
2. COMPLETENESS (CRITICAL): If a step requires interacting with a field that is hidden inside a tab or a modal, you MUST insert intermediate "click" steps to reveal that container.
   - Example: If the draft says "Fill Name" but "Name" has a Parent that is a Tab, you must first "click" the Tab.
   - Use the `parent_nkg_id` and `triggers_nkg_id` info to infer these dependencies.
3. ACTIONS: Ensure the `action` is appropriate (click, input, select, etc.).
4. CONFIDENCE:
   - "high": The draft hint directly matches the element's text or label.
   - "medium": Matches based on description or partial text.
   - "low": Uncertain match or fallback.
5. ORDER: Maintain the logical sequence. 1-indexed.
6. LANGUAGE: The "note" field MUST be written in Bahasa Indonesia to match the system's target language. Do not output notes in English.

OUTPUT FORMAT:
Return ONLY valid JSON matching this schema:
{
  "resolved_steps": [
    {
      "order": 1,
      "nkg_id": "element_nkg_id",
      "action": "click/input/etc",
      "confidence": "high/medium/low",
      "note": "Penjelasan tindakan dalam Bahasa Indonesia. Sebutkan secara eksplisit jika langkah ini disisipkan untuk membuka tab/modal."
    }
  ]
}

IMPORTANT: Your `resolved_steps` array MAY be longer than the input drafts if you insert intermediate steps. Ensure all steps are in logical execution order."""

USER_PROMPT_TEMPLATE = """
### PAGE CONTEXT
Page ID: {page_id}
Page Title: {page_title}

### ACCUMULATED STEPS (Previously Resolved)
{accumulated_steps_str}

### ELEMENT LIST FOR THIS PAGE
{element_list_str}

### STEP DRAFTS FOR THIS PAGE
{step_drafts_str}
{feedback_section}
Please resolve the step drafts to real NKG IDs from the element list above. Remember to insert intermediate steps for tabs/modals if necessary to make the workflow complete and executable.
"""

def render_page_elements(elements: List[Dict]) -> str:
    """Render the element list as a nested tree to show hierarchy (CONTAINS) explicitly."""
    if not elements:
        return "No elements found for this page."

    # 1. Build a parent-child map
    tree: Dict[str, List[Dict]] = {}
    element_map: Dict[str, Dict] = {}
    roots: List[str] = []

    all_ids = {e['nkg_id'] for e in elements}

    for e in elements:
        eid = e['nkg_id']
        element_map[eid] = e
        parent = e.get('parent_nkg_id')
        
        # If parent is not in the list of elements we have, treat it as a root
        if not parent or parent not in all_ids:
            roots.append(eid)
        else:
            if parent not in tree:
                tree[parent] = []
            tree[parent].append(e)

    # 2. Recursive renderer
    lines = []
    seen = set()

    def render_node(eid: str, level: int):
        if eid in seen: return
        seen.add(eid)
        
        e = element_map[eid]
        etype = (e.get('type') or 'element').lower()
        text = (e.get('text', '') or '').strip()
        desc = (e.get('desc', '') or '').strip()
        triggers = e.get('triggers_nkg_id')
        
        indent = "  " * level
        rel = f"(Triggers: {triggers}) " if triggers else ""
        text_preview = f'"{text[:40]}"' if text else ""
        desc_preview = f"— {desc[:60]}" if desc else ""
        
        line = f"{indent}[{etype:7}] {eid:<40} {rel} {text_preview} {desc_preview}"
        lines.append(line.rstrip())
        
        # Render children
        if eid in tree:
            # Sort children by type weight to keep structure clean
            TYPE_WEIGHTS = {'tab': 1, 'modal': 2, 'button': 3, 'input': 4, 'select': 5}
            children = sorted(tree[eid], key=lambda x: (TYPE_WEIGHTS.get(x.get('type','').lower(), 99), x.get('nkg_id','')))
            for child in children:
                render_node(child['nkg_id'], level + 1)

    # 3. Start rendering from roots
    root_elements = [element_map[rid] for rid in roots]
    root_elements.sort(key=lambda x: x.get('nkg_id', ''))
    
    for re in root_elements:
        render_node(re['nkg_id'], 0)

    return "\n".join(lines)
