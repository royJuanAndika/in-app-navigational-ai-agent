# Navigational Knowledge Graph (NKG) - Embedding & Vector Indexing

This document explains how UI elements from the Navigational Knowledge Graph are embedded into vector space and indexed in Neo4j to allow the AI navigational agent to find them efficiently via semantic search.

## 1. The Embedding Process (`embed/embed.py`)

To allow the navigational agent to find the correct UI element based on a user's natural language intent (e.g., "I want to add a new holiday"), we embed each `Element` into a high-dimensional vector using an embedding model (like `qwen3-embedding`).

### What We Embed
We don't just embed the raw HTML or a random string. We construct a highly structured, descriptive text for each element:

```text
Halaman: {page_title} ({page_id})
Elemen: {type} [{id}]
Fungsi: {desc}
```

**Why this format?**
* **Contextual:** Including the page title and URL ensures that elements with identical DOM IDs (like `#submit-btn` or `#content`) on different pages are separated in vector space.
* **Semantic & Structural:** It combines what the element *is* (type, id) with what it *does* (desc).
* **Language Alignment:** The structure is in Bahasa Indonesia, which matches the LLM-generated descriptions, improving tokenization and embedding quality.

### Asymmetric Instruction Prompting (Qwen3)
Models like `qwen3-embedding` are "instruction-tuned" for asymmetric retrieval. This means the model behaves differently depending on whether it's looking at a document to store or a query to search with.

In our script, we prepend instructions to the text:
* **`DOCUMENT_INSTRUCTION`**: `"Represent a UI element in a web application so that it can be retrieved when a user describes their navigation intent or the action they want to perform."` (Used during offline embedding of elements).
* **`QUERY_INSTRUCTION`**: `"Given a user's navigation intent or action description, find the most relevant UI element in the web application that the user wants to interact with."` (Used by the Agent at runtime).

This instructs the model to map the stored UI element and the user's conversational intent to the same point in vector space.

## 2. Neo4j Integration (`insert_neo4j/insert.ipynb`)

Once the embeddings are generated and saved to `data/neo4j-query/embeddings_neo4j.jsonl`, we load them into the Neo4j database efficiently.

### The HNSW Vector Index
Before performing similarity searches, we create a Vector Index on the `Element` nodes:

```cypher
CREATE VECTOR INDEX element_embedding_idx IF NOT EXISTS
FOR (e:Element) ON e.embedding
OPTIONS { 
    indexConfig: { 
        `vector.dimensions`: 1024, 
        `vector.similarity_function`: 'cosine' 
    } 
}
```

**Why do we need this?**
* Without an index, finding the most relevant element requires calculating the cosine distance between the query vector and *every single element* in the database (an O(N) operation).
* The **HNSW (Hierarchical Navigable Small World)** index builds a graph-like structure that allows Neo4j to find the closest vectors in roughly **O(log N)** time. This is critical for fast agent response times.
* *Note: The `vector.dimensions` must exactly match the output size of your chosen embedding model.*

### Batched Insertion & Type Safety
Inserting thousands of embeddings individually is slow due to network and transaction overhead. The insertion notebook uses a few performance tricks:

1. **Batched UNWIND:** We chunk the JSONL records into batches (e.g., 500 at a time) and send them in a single transaction using Cypher's `UNWIND`. This reduces network round-trips by ~100x.
2. **`db.create.setNodeVectorProperty`:** 
   ```cypher
   CALL db.create.setNodeVectorProperty(e, 'embedding', row.embedding)
   ```
   If you use a standard `SET e.embedding = row.embedding`, Neo4j stores the array as a generic List. The HNSW index cannot read a generic list. Using this specific Neo4j procedure ensures the data is stored natively as a `FLOAT ARRAY` vector type, allowing the index to recognize and index it correctly.

## 3. Agent Runtime Flow

When the navigational agent is running, the retrieval process looks like this:

1. **User Intent:** User says "hapus data karyawan ini" (delete this employee data).
2. **Embed Query:** The Agent embeds the string: `Instruct: {QUERY_INSTRUCTION}\nQuery: hapus data karyawan ini`.
3. **Vector Search:** The Agent sends the resulting vector to Neo4j using a `db.index.vector.queryNodes` call.
4. **Result:** Neo4j rapidly traverses the HNSW index and returns the top-K `Element` nodes with the highest cosine similarity.
5. **Action:** The Agent uses the `selector` and `page_id` of the top result to navigate or click the element in the browser.
