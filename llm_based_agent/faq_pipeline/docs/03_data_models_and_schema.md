# Data Models & Graph Schema

The pipeline uses strict Pydantic models to ensure that LLM hallucinations are caught before they reach the database.

## 1. Pydantic Models

### `FAQEntry`
The raw input from `help_center_faq.json`.
*   `faq_id`, `question`, `answer`, `category`, `subcategory`.

### `Phase1Result`
*   `intent_type`: procedural | informational.
*   `intent_id`: A snake_case unique identifier.
*   `page_ids`: List of pages the workflow spans.
*   `page_notes`: Explanations for page resolution.

### `ResolvedStep` (Phase 3 Output)
*   `order`: Global sequence number (1-indexed).
*   `nkg_id`: The verified ID in Neo4j.
*   `action`: click | input | select | etc.
*   `confidence`: high | medium | low (Flags items for manual review).
*   `note`: Logic for matching or insertion.

### `IntentWrite` (Phase 5 Input)
The final aggregated object containing categorization, text content, resolved steps, paraphrases, and the vector embedding.

## 2. Neo4j Graph Schema

### Nodes
*   **(Intent {id, label, content, category, subcategory, embedding, ...})**: The core knowledge node.
*   **(Element {nkg_id, type, selector, ...})**: The existing UI element nodes in the NKG.
*   **(Page {id, title, ...})**: The existing application page nodes.

### Relationships
*   **(:Intent)-[:HAS_STEP {order, action}]->(:Element)**: Defines the navigational workflow.
*   **(:Intent)-[:ABOUT_PAGE]->(:Page)**: Scopes the intent to specific URLs.
*   **(:Intent)-[:HAS_PARAPHRASE]->(:Paraphrase)**: (Optional, usually stored as an array property on Intent).

## 3. Database Constraints
*   `CONSTRAINT intent_id FOR (i:Intent) REQUIRE i.id IS UNIQUE`
*   `VECTOR INDEX intent_embedding_idx FOR (i:Intent) ON (i.embedding)`
