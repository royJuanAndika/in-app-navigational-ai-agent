# NKG Generation & Ingestion Workflow

This document outlines the end-to-end process of creating the Navigational Knowledge Graph (NKG) from raw HTML files and populating the Neo4j database with searchable UI elements.

## Workflow Overview

The pipeline consists of four distinct phases:
1. **Extraction:** HTML → Raw JSON
2. **Repair:** Fixing orphans and bad triggers
3. **Embedding:** Text → Vectors
4. **Ingestion:** Uploading to Neo4j

---

## Phase 1: Extraction
**Script:** `prompting_chunk/chunked_html_to_nkg.py`  
**Input:** `data/cleaned_html/`  
**Output:** `data/nkg_gpu3/`

This script uses an LLM (e.g., `gemma4:31b`) to parse the HTML in chunks. It identifies UI elements, their descriptions, types, and how they relate to each other (triggers and nesting).

## Phase 2: Repair
**Script:** `prompting_chunk/fix_orphans.py`  
**Input:** `data/nkg_gpu3/`  
**Output:** `data/nkg_gpu3_fix_orphans/`

Because the extraction is done in chunks, the LLM sometimes hallucinates parent IDs or trigger targets that don't exist. This script:
1.  **Finds "Orphan" elements:** Elements whose `parent_element_id` doesn't exist in the page.
2.  **Finds "Bad Triggers":** Triggers where the `to` target is a placeholder (like `"element"`) or a hallucination.
3.  **Fixes them:** Uses an LLM to re-assign them to a real existing element or set them to `null` (direct page child).

## Phase 3: Embedding
**Script:** `embed/embed.py`  
**Input:** `data/nkg_gpu3_fix_orphans/`  
**Output:** `data/neo4j-query/embeddings_neo4j.jsonl`

This script takes the human-readable descriptions and converts them into mathematical vectors for search.
*   **Model:** `qwen3-embedding`
*   **Instruction Tuning:** It prepends a `DOCUMENT_INSTRUCTION` to the text so the model knows it is embedding a "target" for a future navigational search.
*   **Consistency:** It includes the Page Title in the text to ensure elements with the same ID across different pages (like `#content`) have different embeddings.

## Phase 4: Ingestion
**Tool:** `insert_neo4j/insert.ipynb`  
**Inputs:** 
*   `.nkg.json` files (from Phase 2)
*   `embeddings_neo4j.jsonl` (from Phase 3)

The ingestion happens in two logical steps inside the notebook to maximize performance:

### Step 4a: Create Nodes & Relationships
The notebook reads the `.nkg.json` files first. It creates the `Page` and `Element` nodes and draws the `CONTAINS` and `TRIGGERS` edges. At this point, the `embedding` property on the nodes is **empty**.

### Step 4b: Enrich with Embeddings
The notebook then reads the `.jsonl` file. It matches the `nkg_id` to the existing nodes in Neo4j and populates the `embedding` property. It uses a **Batched UNWIND** (500 at a time) and the `db.create.setNodeVectorProperty` procedure to ensure the vectors are indexed correctly in the **HNSW Vector Index**.

---

## Summary of Data Flow

| Stage | Input Data | Process | Output Data |
| :--- | :--- | :--- | :--- |
| **1. Extraction** | Clean HTML | LLM Extraction | Raw NKG JSON |
| **2. Repair** | Raw NKG JSON | Logic + LLM Fix | Repaired NKG JSON |
| **3. Embedding** | Repaired NKG JSON | Embedding Model | Vectors (JSONL) |
| **4. Ingestion** | Repaired JSON + Vectors | Neo4j Batch Upload | **Live Graph DB** |
