# 08 — Verification Plan

## Testing Philosophy

**Iterative, not formal.** Build → chat → observe → fix → repeat.

The primary testing tool is a **CLI chat loop** (`cli.py`) that lets you interact with the agent in real-time, see every tool call, and evaluate responses qualitatively. Formal pytest tests come later once the agent behavior stabilizes.

---

## 1. CLI Chat Loop (`cli.py`)

### Purpose
Interactive terminal interface for testing and iterating on the agent.

### Features
- Type messages, see the agent's response
- See which tools were called and what they returned
- See the LLM's `thinking` trace (if available)
- Measure response time per query
- Save conversation logs to `docs/` for thesis documentation

### Usage
```bash
cd llm_based_agent
python cli.py
```

### Example Session
```
╔══════════════════════════════════════════════════════╗
║   In-App Navigational Agent — CLI Test Interface     ║
╚══════════════════════════════════════════════════════╝

Current page (empty for none): /customer/dashboard

You: Bagaimana cara menambah karyawan baru?

── Tool Call: search_elements_by_intent ──────────────
   Args: {"query": "tambah karyawan baru"}
   Result: Found 5 matching elements:
   1. [Score: 0.856] /customer/employee/btn_add ...
──────────────────────────────────────────────────────

── Tool Call: get_element_details ────────────────────
   Args: {"nkg_id": "/customer/employee/btn_add"}
   Result: Element: /customer/employee/btn_add ...
──────────────────────────────────────────────────────

Agent (final JSON):
{
   "message": "Untuk menambah karyawan baru, ikuti langkah berikut:\n\n1. Buka halaman **Karyawan** (`/customer/employee`)\n2. Klik tombol **Tambah Karyawan**\n3. Isi form yang muncul lalu simpan.",
   "type": "guidance",
   "guidance": [
      {"step": 1, "instruction": "Buka halaman Karyawan melalui menu navigasi.", "nkg_id": null},
      {"step": 2, "instruction": "Klik tombol Tambah Karyawan di sudut kanan atas tabel.", "nkg_id": "/customer/employee/btn_add"}
   ]
}

⏱ Response time: 8.2s | Tools used: 2

You: _
```

---

## 2. Test Scenarios

### Core Scenarios (Run these first)

| # | User Query | Expected Behavior |
|:--|:-----------|:-------------------|
| 1 | "Bagaimana cara menambah karyawan baru?" | Search → find btn_add on /customer/employee → step-by-step |
| 2 | "Saya ingin melihat laporan absensi" | Find page → /customer/report/attendance → list reports |
| 3 | "Di mana pengaturan profil perusahaan?" | Find page → /customer/setting/profile → highlight elements |
| 4 | "Cara mengajukan cuti karyawan" | Search → find leave-related elements |
| 5 | "Saya mau beli paket Prime" | Search → find price_list elements |
| 6 | "Tolong jelaskan halaman ini" (with current_page) | Get page content → summarize |

### Fuzzy Text Search Scenarios

| # | User Query | Expected Match |
|:--|:-----------|:---------------|
| 7 | "tombol Tamb Karywan" | "Tambah Karyawan" (fuzzy) |
| 8 | "ekspor data" | "Ekspor" |
| 9 | "Pengaturan Profit" (typo) | "Profil" |

### Edge Cases

| # | Query | Expected |
|:--|:------|:---------|
| 10 | "" (empty) | Helpful prompt |
| 11 | "halo" (greeting) | Friendly intro, explain capabilities |
| 12 | "hapus semua data" | Guide role, not executor |
| 13 | "asdkjhasd" (gibberish) | Ask for clarification |

### Cypher Tool (Last Resort) Scenarios

| # | Query | Expected |
|:--|:------|:---------|
| 14 | "Berapa total halaman yang ada?" | Uses cypher tool → count Pages |
| 15 | "Halaman mana yang punya elemen paling banyak?" | Cypher → aggregation query |

---

## 3. Evaluation Checklist (per response)

- [ ] Agent makes appropriate tool calls (not too many, not too few)
- [ ] Response is in Bahasa Indonesia
- [ ] Response ends with a valid JSON block (`message`, `type`, `guidance`)
- [ ] Mentioned pages and elements actually exist in Neo4j
- [ ] Response is actionable (user can follow the steps)
- [ ] No hallucinated element IDs or page paths
- [ ] Response time is acceptable (<30s)
- [ ] Cypher tool is only used as last resort

---

## 4. Agent Graph Visualization

LangGraph provides built-in visualization for thesis documentation:

```python
from nkg_agent.agent.graph import create_agent

agent = create_agent()

# Generate Mermaid diagram (text)
mermaid_str = agent.get_graph().draw_mermaid()
print(mermaid_str)

# Generate PNG image
png_bytes = agent.get_graph().draw_mermaid_png()
with open("docs/agent_graph.png", "wb") as f:
    f.write(png_bytes)
```

This produces a visual state graph similar to n8n workflows — perfect for thesis figures.

---

## 5. Iteration Workflow

```
1. Run cli.py
2. Test a scenario
3. Observe: tool calls, response quality, errors
4. Identify issue (bad prompt? wrong tool? missing data?)
5. Fix the code
6. Re-run the same scenario
7. Repeat until satisfied
8. Document findings in docs/
```

---

## 6. Formal Tests (Later Phase)

Once the agent behavior is stable, convert successful CLI test cases into pytest tests:

```bash
cd llm_based_agent
pytest tests/ -v --timeout=60
```

Unit tests for `graph_db` and tools can run fast (no LLM calls).
Integration tests with the agent are slow (10-30s each) — run selectively.
