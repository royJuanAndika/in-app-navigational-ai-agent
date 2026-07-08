# Resilience & Recovery

Given the instability of external LLM proxies and the complexity of 121 FAQs, the pipeline is built for high reliability and resumeability.

## 1. Retry Logic
Every LLM-dependent phase (1, 2, 3, and 4) is wrapped in a retry loop:
*   **Max Retries:** 2.
*   **Catchable Errors:** Network timeouts, DNS failures, and JSON parsing errors.
*   **Implementation:** `Phase1Result.model_validate_json()` ensures that if the LLM output is cut off (EOF error), it triggers a retry immediately.

## 2. Validation & Hallucination Defense
*   **Schema Enforcement:** Pydantic models force the LLM to adhere to the expected structure.
*   **Page Resolution Check:** In Phase 2, if the LLM tries to output a step for a page that was **not** identified in Phase 1, a `ValueError` is raised, preventing "hallucinated navigation."

## 3. The Resume System
To handle long-running jobs (approx. 40 mins for 121 FAQs), the pipeline supports the `--resume` flag.

### Logic:
1.  Loads existing results from `final_intents.json`.
2.  Filters out any FAQ that **already has a non-empty embedding**.
3.  Initializes intermediate lists (`phase1_results`, etc.) with the partial data.
4.  Only processes the missing or failed items.

## 4. The Review Loop (`review_log.jsonl`)
Any step that does not meet the "High Confidence" threshold (e.g., semantic match was loose or a tab/modal was auto-inserted) is logged to `review_log.jsonl`.
*   **Purpose:** Allows a human expert to perform a final audit before "pushing" the data to the production graph.
*   **Format:** Newline-delimited JSON for easy parsing or searching.
