# NKG JSON Schema Reference

Complete specification for the Navigational Knowledge Graph JSON output format.

---

## Root-Level Structure

```json
{
  "meta": { ... },           // ← Processing metadata
  "nkg": { ... },            // ← Core NKG data (for graph insertion)
  "verification": { ... },   // ← Coverage & quality metrics
  "chunk_reports": [ ... ],  // ← Per-chunk extraction stats
  "cypher_payload": { ... }  // ← Ready-to-use Neo4j parameters
}
```

---

## 1. `meta` — Processing Information

```json
{
  "meta": {
    "schema_version": "nkg_chunked_v1",
    "source_html": "data/cleaned_html/customer_employee.html",
    "filename": "customer_employee.html",
    "model": "gemma4:31b",
    "ollama_url": "http://localhost:11434",
    "page_url": "/customer/employee",
    "page_title": "Employee Management",
    "chunk_config": {
      "chunk_chars": 18000,
      "overlap_chars": 1200,
      "total_chunks": 32
    },
    "runtime_seconds": 245.67
  }
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Format version for compatibility tracking |
| `source_html` | string | Path to input HTML file |
| `filename` | string | Just the filename (e.g., `customer_employee.html`) |
| `model` | string | LLM model used (e.g., `gemma4:31b`) |
| `ollama_url` | string | Ollama server endpoint |
| `page_url` | string | Inferred URL from filename (e.g., `/customer/employee`) |
| `page_title` | string | HTML `<title>` tag content |
| `chunk_config.total_chunks` | int | Number of HTML chunks processed |
| `runtime_seconds` | float | Total processing time in seconds |

---

## 2. `nkg` — Core NKG Data (Cypher-Ready)

### Structure

```json
{
  "nkg": {
    "page": {
      "id": "/customer/employee",
      "title": "Employee Management",
      "desc": "Halaman untuk mengelola data karyawan perusahaan..."
    },
    "elements": [ /* ... */ ],
    "triggers": [ /* ... */ ]
  }
}
```

---

### 2a. `page` Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique page identifier (URL path) |
| `title` | string | Human-readable page name |
| `desc` | string | Indonesian description of page purpose |

**Example:**
```json
{
  "id": "/customer/employee",
  "title": "Manajemen Karyawan",
  "desc": "Halaman admin untuk menampilkan, mencari, dan mengelola data karyawan perusahaan"
}
```

---

### 2b. `elements` Array

Each element represents an actionable UI component.

```json
{
  "elements": [
    {
      "id": "btn_favorite",
      "desc": "Tombol untuk menandai karyawan favorit",
      "type": "button",
      "selector": "#btn_favorite",
      "parent_element_id": null
    },
    {
      "id": "employee__modal_add",
      "desc": "Modal form untuk menambah karyawan baru",
      "type": "modal",
      "selector": ".modal-add.fade"
    }
  ]
}
```

#### Element Properties

| Field | Type | Rules | Example |
|-------|------|-------|---------|
| `id` | string | **CRITICAL**: Must be verifiable against HTML. See section 3 below. | `"btn_favorite"` or `"employee__modal_add"` |
| `desc` | string | Bahasa Indonesia, action-oriented, 10-100 chars | `"Tombol untuk menandai karyawan favorit"` |
| `type` | string | One of: `button`, `input`, `select`, `textarea`, `modal`, `table`, `link`, `tab`, `section` | `"button"` |
| `selector` | string | CSS selector for JavaScript targeting. Must be unique enough to find element. | `"#btn_favorite"` or `[onclick*="check_addon"]` |
| `parent_element_id` | string or null | Optional parent element id for nested hierarchy (e.g. input di dalam modal/form) | `"employee__modal_add"` |

#### ID Generation Rules

**CASE A: Element HAS DOM `id`**
```html
<button id="btn_favorite">⭐</button>
```
→ NKG id: `"btn_favorite"` (use verbatim)
→ Selector: `"#btn_favorite"` (exact match required)

**CASE B: Element has NO DOM `id` (must generate)**
```html
<div class="modal-add fade" onclick="...">Add Employee</div>
```
On page `/customer/employee` (slug = `employee`):
→ NKG id: `"employee__modal_add"` (prefix with page slug)
→ Selector: `.modal-add.fade` or `[onclick*="add_employee"]`

**ID Format for Generated IDs:**
```
<page_slug>__<short_description>
```
- `page_slug` = last segment of URL (e.g., `/customer/employee` → `employee`)
- `short_description` = snake_case label (e.g., `modal_add`, `btn_submit`)
- Ensures global uniqueness across all 47 pages

---

### 2c. `triggers` Array

Represents user interactions and transitions.

```json
{
  "triggers": [
    {
      "from": "btn_favorite",
      "to": "/customer/employee",
      "to_type": "page"
    },
    {
      "from": "btn_add_karyawan",
      "to": "employee__modal_add",
      "to_type": "element"
    },
    {
      "from": "form_add_karyawan",
      "to": "/customer/attendance",
      "to_type": "page"
    }
  ]
}
```

#### Trigger Properties

| Field | Type | Rules | Example |
|-------|------|-------|---------|
| `from` | string | Must match an element id from `elements[]` | `"btn_favorite"` |
| `to` | string | Either a page URL or an element id | `"/customer/employee"` or `"employee__modal_add"` |
| `to_type` | string | `"page"` (navigation) or `"element"` (reveal/show on same page) | `"page"` |

#### Trigger Types

**Type 1: Navigation Trigger (`to_type: "page"`)**
- User clicks button → loads different page
- `from`: click source
- `to`: URL path (e.g., `"/customer/attendance"`)

**Type 2: Element Trigger (`to_type: "element"`)**
- User clicks button → reveals/shows modal or hidden element
- `from`: click source
- `to`: element id (can be `employee__modal_add` or `notification_panel`)

---

## 3. `verification` — Coverage Metrics

```json
{
  "verification": {
    "dom_ids_total": 911,
    "dom_ids_in_nkg_total": 875,
    "coverage_percent": 96.05,
    "missing_dom_ids": ["select2-data-12", "hidden_backup_id"],
    "missing_dom_ids_with_line": [
      {"id": "select2-data-12", "line": 456},
      {"id": "hidden_backup_id", "line": 789}
    ],
    "generated_non_dom_ids": ["employee__modal_add", "employee__btn_submit"],
    "selector_mismatches": [
      {
        "id": "btn_favorite",
        "expected": "#btn_favorite",
        "actual": ".btn_favorite"
      }
    ],
    "is_complete": false
  }
}
```

#### Fields

| Field | Type | Purpose |
|-------|------|---------|
| `dom_ids_total` | int | Total unique DOM ids found in HTML |
| `dom_ids_in_nkg_total` | int | How many DOM ids appear in extracted elements |
| `coverage_percent` | float | `(dom_ids_in_nkg_total / dom_ids_total) * 100` |
| `missing_dom_ids` | array | DOM ids not extracted (may be decorative) |
| `missing_dom_ids_with_line` | array | Missing ids with their HTML line numbers |
| `generated_non_dom_ids` | array | Generated ids (not from DOM) |
| `selector_mismatches` | array | Elements where selector != expected DOM selector |
| `is_complete` | bool | **True only if `coverage_percent == 100%`** |

#### When Coverage < 100%

**Possible reasons:**
1. Decorative elements (select2 dropdowns, loading spinners)
2. LLM missed some elements
3. Elements appear in later chunks (should be merged)

**Actions:**
- Use `--patch-missing` for second LLM pass
- Manually review missing ids with line numbers (might be decorative)
- Increase `--chunk-chars` if many ids missed in same area

---

## 4. `chunk_reports` — Per-Chunk Statistics

```json
{
  "chunk_reports": [
    {
      "chunk_index": 1,
      "line_range": [1, 334],
      "char_count": 17706,
      "dom_ids_in_chunk": 29,
      "new_ids_added": 24,
      "missing_dom_ids_after_chunk": [],
      "patch_added": 0,
      "patch_error": null
    },
    {
      "chunk_index": 2,
      "line_range": [320, 680],
      "char_count": 18155,
      "dom_ids_in_chunk": 32,
      "new_ids_added": 28,
      "missing_dom_ids_after_chunk": ["select2-data-12"],
      "patch_added": 1,
      "patch_error": null
    }
  ]
}
```

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `chunk_index` | int | Chunk sequence number (1-indexed) |
| `line_range` | array | `[start_line, end_line]` in HTML |
| `char_count` | int | Bytes of HTML in this chunk |
| `dom_ids_in_chunk` | int | Total DOM ids in this chunk |
| `new_ids_added` | int | New element ids added from this chunk |
| `missing_dom_ids_after_chunk` | array | DOM ids not covered after processing chunk |
| `patch_added` | int | Elements added by patching pass (if `--patch-missing`) |
| `patch_error` | string or null | Error during patching (if any) |

---

## 5. `cypher_payload` — Neo4j Parameters

```json
{
  "cypher_payload": {
    "params": {
      "page": {
        "id": "/customer/employee",
        "title": "Employee Management",
        "desc": "..."
      },
      "elements": [
        {
          "id": "btn_favorite",
          "desc": "...",
          "type": "button",
          "selector": "#btn_favorite"
        }
        // ... more elements
      ],
      "contains": [
        {"page_id": "/customer/employee", "element_id": "btn_favorite"},
        {"page_id": "/customer/employee", "element_id": "employee__modal_add"}
        // ...
      ],
      "element_contains": [
        {"parent_id": "employee__modal_add", "child_id": "employee__input_nama"}
        // ...
      ],
      "triggers": [
        {
          "from": "btn_favorite",
          "to": "/customer/employee",
          "to_type": "page"
        }
        // ...
      ]
    },
    "cypher_templates": {
      "upsert_nodes_and_edges": "MERGE (p:Page {id: $page.id}) SET p.title = $page.title, p.desc = $page.desc WITH p UNWIND $elements AS e MERGE (el:Element {id: e.id}) SET el.desc = e.desc, el.type = e.type, el.selector = e.selector WITH p UNWIND $contains AS c MATCH (el:Element {id: c.element_id}) MERGE (p)-[:CONTAINS]->(el);",
      "upsert_element_contains": "UNWIND $element_contains AS c MATCH (parent:Element {id: c.parent_id}) MATCH (child:Element {id: c.child_id}) MERGE (parent)-[:CONTAINS]->(child);",
      "upsert_triggers": "UNWIND $triggers AS t MATCH (from:Element {id: t.from}) FOREACH (_ IN CASE WHEN t.to_type = 'element' THEN [1] ELSE [] END | MERGE (toEl:Element {id: t.to}) MERGE (from)-[:TRIGGERS]->(toEl) ) FOREACH (_ IN CASE WHEN t.to_type = 'page' THEN [1] ELSE [] END | MERGE (toPg:Page {id: t.to}) MERGE (from)-[:TRIGGERS]->(toPg) );"
      }
    }
  }
}
```

### Using Cypher in Neo4j

**Python example:**
```python
from neo4j import GraphDatabase
import json

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))

with driver.session() as session:
    result = json.load(open("customer_employee.nkg.json"))
    cypher_payload = result["cypher_payload"]
    params = cypher_payload["params"]
    templates = cypher_payload["cypher_templates"]
    
    # Execute insertion
    session.run(templates["upsert_nodes_and_edges"], **params)
    session.run(templates["upsert_element_contains"], **params)
    session.run(templates["upsert_triggers"], **params)
```

**Cypher template features:**
- `MERGE` ensures no duplicates
- `UNWIND` loops through arrays
- `FOREACH` handles conditional logic (element vs page triggers)
- All parameters are escaped ($param syntax)

---

## 6. Complete Example

```json
{
  "meta": {
    "schema_version": "nkg_chunked_v1",
    "source_html": "data/cleaned_html/customer_employee.html",
    "filename": "customer_employee.html",
    "model": "gemma4:31b",
    "page_url": "/customer/employee",
    "page_title": "Employee Management",
    "chunk_config": {
      "chunk_chars": 18000,
      "overlap_chars": 1200,
      "total_chunks": 32
    },
    "runtime_seconds": 245.67
  },

  "nkg": {
    "page": {
      "id": "/customer/employee",
      "title": "Employee Management",
      "desc": "Halaman untuk menampilkan, mencari, dan mengelola daftar karyawan perusahaan"
    },
    "elements": [
      {
        "id": "btn_add_karyawan",
        "desc": "Tombol untuk membuka form penambahan karyawan baru",
        "type": "button",
        "selector": "#btn_add_karyawan"
      },
      {
        "id": "employee__modal_add",
        "desc": "Modal form untuk input data karyawan",
        "type": "modal",
        "selector": ".modal-add.fade"
      },
      {
        "id": "table_karyawan",
        "desc": "Tabel daftar seluruh karyawan dengan informasi dasar",
        "type": "table",
        "selector": "#table_karyawan"
      }
    ],
    "triggers": [
      {
        "from": "btn_add_karyawan",
        "to": "employee__modal_add",
        "to_type": "element"
      },
      {
        "from": "modal_form_submit",
        "to": "/customer/employee",
        "to_type": "page"
      }
    ]
  },

  "verification": {
    "dom_ids_total": 911,
    "dom_ids_in_nkg_total": 875,
    "coverage_percent": 96.05,
    "missing_dom_ids": ["select2-data-12", "hidden_spinner"],
    "missing_dom_ids_with_line": [
      {"id": "select2-data-12", "line": 456},
      {"id": "hidden_spinner", "line": 789}
    ],
    "generated_non_dom_ids": ["employee__modal_add"],
    "selector_mismatches": [],
    "is_complete": false
  },

  "chunk_reports": [
    {
      "chunk_index": 1,
      "line_range": [1, 334],
      "char_count": 17706,
      "dom_ids_in_chunk": 29,
      "new_ids_added": 24,
      "missing_dom_ids_after_chunk": [],
      "patch_added": 0,
      "patch_error": null
    }
  ],

  "cypher_payload": {
    "params": {
      "page": {
        "id": "/customer/employee",
        "title": "Employee Management",
        "desc": "Halaman untuk menampilkan, mencari, dan mengelola daftar karyawan perusahaan"
      },
      "elements": [
        {
          "id": "btn_add_karyawan",
          "desc": "Tombol untuk membuka form penambahan karyawan baru",
          "type": "button",
          "selector": "#btn_add_karyawan"
        },
        {
          "id": "employee__modal_add",
          "desc": "Modal form untuk input data karyawan",
          "type": "modal",
          "selector": ".modal-add.fade"
        },
        {
          "id": "table_karyawan",
          "desc": "Tabel daftar seluruh karyawan dengan informasi dasar",
          "type": "table",
          "selector": "#table_karyawan"
        }
      ],
      "contains": [
        {"page_id": "/customer/employee", "element_id": "btn_add_karyawan"},
        {"page_id": "/customer/employee", "element_id": "employee__modal_add"},
        {"page_id": "/customer/employee", "element_id": "table_karyawan"}
      ],
      "triggers": [
        {
          "from": "btn_add_karyawan",
          "to": "employee__modal_add",
          "to_type": "element"
        },
        {
          "from": "modal_form_submit",
          "to": "/customer/employee",
          "to_type": "page"
        }
      ]
    },
    "cypher_templates": {
      "upsert_nodes_and_edges": "MERGE (p:Page {id: $page.id}) SET p.title = $page.title, p.desc = $page.desc WITH p UNWIND $elements AS e MERGE (el:Element {id: e.id}) SET el.desc = e.desc, el.type = e.type, el.selector = e.selector MERGE (p)-[:CONTAINS]->(el);",
      "upsert_triggers": "UNWIND $triggers AS t MATCH (from:Element {id: t.from}) FOREACH (_ IN CASE WHEN t.to_type = 'element' THEN [1] ELSE [] END | MERGE (toEl:Element {id: t.to}) MERGE (from)-[:TRIGGERS]->(toEl) ) FOREACH (_ IN CASE WHEN t.to_type = 'page' THEN [1] ELSE [] END | MERGE (toPg:Page {id: t.to}) MERGE (from)-[:TRIGGERS]->(toPg) );"
    }
  }
}
```

---

## Validation Checklist

When reviewing an NKG JSON:

- [ ] All elements have required fields: `id`, `desc`, `type`, `selector`
- [ ] All DOM ids in verification `missing_dom_ids` are either checked in HTML or confirmed decorative
- [ ] Selector mismatches list is empty (or checked)
- [ ] Cypher templates have proper parameter references ($page, $elements, etc.)
- [ ] No duplicate element ids
- [ ] All `triggers[].from` values exist in `elements[].id`
- [ ] `is_complete: true` or has justification for missing ids

---

**For more:** See [QUICKSTART.md](QUICKSTART.md) and [CHUNKED_EXTRACTION_GUIDE.md](CHUNKED_EXTRACTION_GUIDE.md)
