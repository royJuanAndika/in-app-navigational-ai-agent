# FAQ Ingestion Pipeline: Architecture Overview

## 1. Problem Statement
The Navigational Knowledge Graph (NKG) is often "unreliable" at runtime because:
1.  **Incomplete Relations:** `[:TRIGGERS]` or `[:CONTAINS]` edges may be missing or logically disconnected.
2.  **Implicit Prerequisites:** FAQ source text often skips essential UI steps (e.g., "Click the Add button" skips the prerequisite of clicking the "Employee Tab" first).
3.  **Language Mismatch:** User queries may use different vocabulary than the technical IDs or descriptions in the NKG.

## 2. The "Intent-Based" Solution
The pipeline solves these issues by transforming flat FAQ data into **Structured Navigational Intents**.

### Intent Nodes as Ground Truth
Instead of the agent trying to "figure it out" by hopping through a potentially broken graph at runtime, the pipeline pre-resolves the entire path.
*   We create `(i:Intent)` nodes that represent a high-level goal (e.g., "Tambah Karyawan").
*   We attach a sequence of `[:HAS_STEP]` edges directly to the `Intent`.
*   **Result:** The agent follows a verified "recipe" rather than a fragile heuristic traversal.

### The "Healer" Pipeline
The pipeline acts as a data-cleaning and enrichment layer:
*   **Hierarchy Awareness:** By providing the LLM with the UI hierarchy (Parents/Triggers), it can "heal" incomplete FAQs by automatically inserting missing navigational steps (like opening a modal or tab).
*   **Semantic Grounding:** By generating multi-register paraphrases (formal, informal, slang) and embedding them with asymmetric instructions, we ensure the agent can find the right intent even from vague user queries.

## 3. High-Level Workflow
1.  **Ingest:** Load raw JSON FAQs.
2.  **Analyze (Phase 1-2):** Use LLM to classify intent and draft procedural steps in Bahasa Indonesia.
3.  **Resolve (Phase 3):** Match drafts to real NKG IDs using hierarchy-aware logic.
4.  **Enrich (Phase 4):** Generate possible questions and asymmetric embeddings.
5.  **Persist (Phase 5):** Idempotently write to Neo4j with a "clean-slate" strategy per Intent.
