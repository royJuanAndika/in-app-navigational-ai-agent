# Embedding & Retrieval Strategy

The pipeline uses an asymmetric embedding pattern to bridge the gap between user questions and technical documentation.

## 1. Asymmetric Instructions
We use specific instructions for the **Qwen/BGE** style models to separate the "Query" from the "Document."

### The "Document" Side (Ingestion)
Used in Phase 4 when storing the Intent.
> `Instruct: Represent a user's navigation intent or knowledge query in a HR SaaS platform so that it can be retrieved when a user asks a related question.`

### The "Query" Side (Runtime)
Used by the agent when searching for help.
> `Instruct: Represent a user's question about an HR SaaS platform for retrieving the most relevant navigational intent or help content.`

## 2. The Embedding Payload (Signal Optimization)
To prevent "Signal Dilution," we don't embed the entire FAQ. We construct a targeted document:

```text
Instruct: [INTENT_DOC_INSTRUCTION]
Document: Intent: [Label]
Kategori: [Category] > [Subcategory]
Tipe: [Intent Type]
Pertanyaan: [Paraphrase 1] | [Paraphrase 2] | ...
Konten: [First 200 chars of text OR Step Summary]
```

### Why we limit content?
*   **200 Chars:** Captures the core definition without including irrelevant details.
*   **5 Steps:** Captures the "Entry Point" of a workflow. If a user asks "How do I add...", the most important signal is the first few clicks (`click /btn_add`). 

## 3. Vector Indexing
Intents are stored in a Neo4j Vector Index (`intent_embedding_idx`) with:
*   **Dimensions:** 1024 (standard for Qwen3-embedding).
*   **Similarity Function:** Cosine.
