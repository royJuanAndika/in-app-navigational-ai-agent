# Element Text Extraction & Review Pipeline

This directory contains scripts to extract visible text labels from HTML snapshots, automatically/manually review their relevance, and prepare them for injection into the Navigational Knowledge Graph (NKG).

## The Pipeline

1. **Extraction** (`extract_element_text.py`)
2. **Review (LLM or Manual)** (`llm_review.py` & `review_summary.txt`)
3. **Sync Manual Edits** (`sync_review.py`)
4. **Apply (TODO)** - Injecting the approved `INCLUDE` texts back into the `.nkg.json` files.

---

### 1. Extraction: `extract_element_text.py`

Reads all `.nkg.json` files and their corresponding `.html` snapshots. Uses BeautifulSoup to extract the actual visible text for each element in the NKG.

**Rules:**
- Classifies elements with clear navigational value (e.g., `<button>`, `<a>`, `<input>`) as `INCLUDE` or `REVIEW`.
- Classifies structural/layout containers (e.g., `<div>`, `<table>`) as `SKIP` by default to avoid noise.
- Trims whitespace and cleans up the strings.

**Output:**
- `../data/element_text_review/review_report.json` (The source of truth)
- `../data/element_text_review/review_summary.txt` (Human-readable version for manual review)

**Usage:**
```powershell
cd data_preprocessing_and_cleaning/extract_element_text
python extract_element_text.py
```

---

### 2. LLM Automated Review: `llm_review.py`

Because manually reviewing thousands of extracted labels is tedious, this script sends the `REVIEW` and `SKIP` candidates to an LLM to make intelligent `INCLUDE`/`SKIP` decisions based on semantic relevance (is it an informational tooltip? is it a table column header?).

**Features:**
- Can use a local Ollama model (`--mode local`).
- Can use a remote GPU proxy server (`--mode remote`).
- Checkpoints progress automatically (safe to cancel and resume).
- Automatically updates both `review_report.json` and `review_summary.txt`.

**Usage:**
```powershell
cd data_preprocessing_and_cleaning/extract_element_text

# Use Remote GPU Server (Recommended)
python llm_review.py --mode remote --server-url https://youtube.com --token some-secret-token --model gemma4:27b

# Use Local Ollama
python llm_review.py --mode local --model qwen3:8b

# Test on a single file
python llm_review.py --mode remote --only customer_attendance_leave.nkg.json
```

---

### 3. Manual Review & Sync: `sync_review.py`

If you want to manually override decisions (e.g., fix a typo in the text, or change a `SKIP` to an `INCLUDE`), you can edit the `review_summary.txt` file directly.

**How to edit manually:**
1. Open `../data/element_text_review/review_summary.txt`
2. Change `status=SKIP` to `status=INCLUDE`
3. Edit the text string directly if needed: `text='Fixed label'`

**Syncing your changes:**
Once you've made manual edits to the `.txt` file, you must sync them back to the `.json` report.

```powershell
cd data_preprocessing_and_cleaning/extract_element_text
python sync_review.py
```
*(This script is safe and will not overwrite your JSON with truncated `...` strings from the summary).*
