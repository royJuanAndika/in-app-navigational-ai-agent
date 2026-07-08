# 06 — Agent & Prompts

## LangGraph Agent Definition

### File: `agent/graph.py`

The agent is built using `langgraph.prebuilt.create_react_agent`, which provides:
- A **ReAct loop** (Reason → Act → Observe → Repeat)
- Automatic tool execution and result injection
- Message history state management
- Conditional routing (tool call vs final answer)

### Agent Construction

```python
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage

from ..core.llm import get_llm
from ..tools import ALL_TOOLS
from .prompts import SYSTEM_PROMPT

def create_agent():
    """Create the In-App Navigational Agent with all tools."""
    llm = get_llm()
    
    agent = create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        prompt=SystemMessage(content=SYSTEM_PROMPT),
    )
    
    return agent
```

### Agent Invocation

```python
from langchain_core.messages import HumanMessage

def chat(agent, user_message: str, current_page: str | None = None) -> dict:
    """Send a message to the agent and get a response."""
    
    # Inject current page context if provided
    if current_page:
        full_message = f"[Pengguna sedang di halaman: {current_page}]\n\n{user_message}"
    else:
        full_message = user_message
    
    result = agent.invoke({
        "messages": [HumanMessage(content=full_message)]
    })
    
    # Extract the final AI message
    final_message = result["messages"][-1]
    return {
        "message": final_message.content,
        "tool_calls_made": [
            msg for msg in result["messages"]
            if hasattr(msg, "tool_calls") and msg.tool_calls
        ],
    }
```

### ReAct Loop Visualization

```
                    ┌─────────────────────┐
                    │       START          │
                    │  (user message)      │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
              ┌────│    AGENT (LLM)       │────┐
              │    │  gemma4:31b          │    │
              │    │  + system prompt     │    │
              │    │  + message history   │    │
              │    └─────────────────────┘    │
              │                                │
         tool_calls                      no tool_calls
         present                         (final answer)
              │                                │
              ▼                                ▼
    ┌─────────────────────┐         ┌─────────────────────┐
    │      TOOLS          │         │       END            │
    │  Execute tool(s)    │         │  Return response     │
    │  Append results     │         └─────────────────────┘
    │  to message history │
    └──────────┬──────────┘
               │
               └──────── back to AGENT ──────┘
```

### Message History Per Invocation

A single invocation might produce this message sequence:

```
[0] SystemMessage: SYSTEM_PROMPT
[1] HumanMessage: "cara tambah karyawan baru"
[2] AIMessage: tool_calls=[{name: "search_elements_by_intent", args: {query: "tambah karyawan baru"}}]
[3] ToolMessage: "Found 5 matching elements:\n1. [Score: 0.856] /customer/employee/btn_add..."
[4] AIMessage: tool_calls=[{name: "get_element_details", args: {nkg_id: "/customer/employee/btn_add"}}]
[5] ToolMessage: "Element: /customer/employee/btn_add\n  Triggers: modal_add_employee..."
[6] AIMessage: "Untuk menambah karyawan baru, ikuti langkah berikut:..."  ← FINAL
```

---

## System Prompt Design

### File: `agent/prompts.py`

The system prompt is critical — it defines agent behavior, personality, and output format.

### Prompt Structure

```python
SYSTEM_PROMPT = """Kamu adalah asisten navigasi untuk platform SaaS pengelolaan HR "Fingerspot.iO".
Tugasmu adalah MEMANDU pengguna (admin) untuk menemukan dan menggunakan fitur-fitur
di panel admin, bukan mengerjakan tugas untuk mereka.

## Identitas
- Nama: Asisten Navigasi Fingerspot.iO
- Bahasa: Bahasa Indonesia (formal tapi ramah)
- Peran: Pemandu navigasi UI, bukan pelaksana tugas

## Cara Kerja
1. SELALU gunakan tools untuk mencari informasi sebelum menjawab
2. JANGAN PERNAH mengarang ID elemen, selector CSS, atau nama halaman
3. Jika tidak menemukan elemen yang relevan, katakan dengan jujur
4. Berikan panduan langkah-demi-langkah yang jelas
5. Tool `execute_cypher_read_query` adalah PILIHAN TERAKHIR — gunakan HANYA jika
    8 tool lainnya tidak bisa menjawab pertanyaan

## Format Respons
Selalu akhiri jawaban dengan **blok JSON** yang berisi `message`, `type`, dan `guidance`.
UI menggunakan `guidance[*].nkg_id` lalu backend akan melakukan enrichment untuk
`page_url`, `selector`, dan `element_id`.

### Contoh Respons JSON
```json
{
    "message": "Untuk menambah karyawan baru, ikuti langkah berikut:\n\n1. Buka halaman **Karyawan** (`/customer/employee`)\n2. Klik tombol **Tambah Karyawan**\n3. Isi form yang muncul lalu simpan.",
    "type": "guidance",
    "guidance": [
        {
            "step": 1,
            "instruction": "Buka halaman Karyawan melalui menu navigasi.",
            "nkg_id": null
        },
        {
            "step": 2,
            "instruction": "Klik tombol Tambah Karyawan di sudut kanan atas tabel.",
            "nkg_id": "/customer/employee/btn_add_employee"
        },
        {
            "step": 3,
            "instruction": "Isi data karyawan baru pada field yang muncul.",
            "nkg_id": "/customer/employee/input_employee_name"
        },
        {
            "step": 4,
            "instruction": "Klik tombol Simpan untuk mendaftarkan karyawan.",
            "nkg_id": "/customer/employee/btn_save_employee"
        }
    ]
}
```

## Konteks Halaman
Jika informasi halaman saat ini diberikan (format: [Pengguna sedang di halaman: ...]),
gunakan informasi ini untuk:
- Menghindari instruksi navigasi yang tidak perlu jika user sudah di halaman yang benar
- Memberikan panduan yang lebih kontekstual

## Batasan
- Kamu HANYA bisa memandu berdasarkan data yang ada di knowledge graph
- Jika user bertanya tentang hal di luar navigasi UI, arahkan kembali ke tugasmu
- Jangan memberikan informasi sensitif tentang struktur teknis database
"""
```

### Prompt Design Rationale

| Section | Purpose |
|:--------|:--------|
| **Identitas** | Anchors the LLM's persona — prevents role confusion |
| **Cara Kerja** | Forces tool usage — prevents hallucination |
| **Format Respons** | Ensures structured JSON guidance for frontend enrichment |
| **Contoh** | Few-shot example — improves output consistency |
| **Konteks Halaman** | Teaches context-aware guidance |
| **Batasan** | Guardrails — prevents off-topic responses |

### Language Choice: Bahasa Indonesia
The prompt is in Bahasa Indonesia because:
1. All element descriptions (`desc`) are in Bahasa Indonesia
2. The target users are Indonesian
3. The embedding model was trained on Indonesian text for this domain
4. `gemma4:31b` handles Indonesian well

---

## Multi-Turn Conversation

The current design is **single-turn per API call** (no persistent memory between calls). Each `/chat` request starts fresh.

### Why No Memory (for now)?
- Simpler architecture
- Sufficient for navigational queries (most are self-contained)
- No user authentication means no user-scoped memory

### Adding Memory Later
LangGraph supports `checkpointers` for conversation persistence:
```python
from langgraph.checkpoint.memory import MemorySaver

memory = MemorySaver()
agent = create_react_agent(model, tools, checkpointer=memory)

# Each conversation gets a thread_id
config = {"configurable": {"thread_id": "user-123"}}
agent.invoke({"messages": [...]}, config=config)
```

This is a trivial addition when needed.
