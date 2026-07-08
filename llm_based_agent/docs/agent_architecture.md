# In-App Navigational Agent - Complete Architecture

## Agent & Tools Structure

```mermaid
graph TB
    subgraph API["🌐 FastAPI Server Layer"]
        SERVER["FastAPI Server<br/>- /api/chatbot/message<br/>- /chat<br/>- /api/chatbot/log<br/>- /health"]
        REQ["Request Handler<br/>ChatRequest<br/>conversation_id<br/>current_page<br/>history"]
        RESP["Response Handler<br/>ChatResponse<br/>- message<br/>- type<br/>- guidance<br/>- tools_used"]
    end

    subgraph AGENT["🤖 LangGraph ReAct Agent"]
        AGENT_CORE["create_agent()"]
        SYSTEM["System Prompt<br/>SYSTEM_PROMPT"]
        REFORMAT["Response Parser<br/>parse_agent_response()<br/>JSON extraction"]
    end

    subgraph TOOLS["🛠️ Tool Suite - 12 Tools"]
        subgraph INTENT_TOOLS["Intent Discovery"]
            T1["search_intents<br/>Semantic search intent candidates"]
            T2["get_steps_for_intent<br/>Fetch ordered workflow steps"]
            T3["get_intents_by_page<br/>List intents on page"]
        end

        subgraph ELEMENT_TOOLS["Element Search & Details"]
            T4["search_elements_by_intent<br/>Vector search UI elements"]
            T5["search_elements_by_text<br/>Fuzzy text matching"]
            T6["get_element_details<br/>Element properties & triggers"]
            T7["find_trigger_prerequisites<br/>Find elements that trigger this"]
        end

        subgraph PAGE_TOOLS["Page Navigation"]
            T8["find_page<br/>Search page by keyword"]
            T9["get_page_content<br/>All elements on page"]
            T10["get_container_content<br/>Nested container elements"]
            T11["get_form_fields_on_page<br/>Form controls on page"]
        end

        subgraph UTILITY_TOOLS["Utility"]
            T12["execute_cypher_read_query<br/>Direct Neo4j access"]
        end
    end

    subgraph CORE["⚙️ Core Layer"]
        CONFIG["Config<br/>get_settings()<br/>- Neo4j URI<br/>- LLM backend<br/>- Models<br/>- Thresholds"]
        LLM["LLM Manager<br/>get_llm()<br/>- Ollama Proxy<br/>- Local Ollama<br/>- OpenRouter API<br/>get_query_embedding"]
        GRAPHDB["Graph Database Layer<br/>get_driver()<br/>- _run_read()<br/>- Cypher queries"]
    end

    subgraph EXT["🔌 External Services"]
        NEO4J["Neo4j Database<br/>Navigational Knowledge Graph<br/>Nodes: Page, Element, Intent<br/>Relations: CONTAINS, TRIGGERS, HAS_STEP"]
        LLM_SVC["LLM Services<br/>- Ollama GPU3 Proxy<br/>- Local Ollama<br/>- OpenRouter<br/>Models: Gemma4, DeepSeek-R1"]
    end

    %% Connections - API Layer
    SERVER --> REQ
    REQ --> AGENT_CORE
    AGENT_CORE --> SYSTEM
    AGENT_CORE --> REFORMAT
    REFORMAT --> RESP

    %% Connections - Agent to Tools
    AGENT_CORE -->|call| T1
    AGENT_CORE -->|call| T2
    AGENT_CORE -->|call| T3
    AGENT_CORE -->|call| T4
    AGENT_CORE -->|call| T5
    AGENT_CORE -->|call| T6
    AGENT_CORE -->|call| T7
    AGENT_CORE -->|call| T8
    AGENT_CORE -->|call| T9
    AGENT_CORE -->|call| T10
    AGENT_CORE -->|call| T11
    AGENT_CORE -->|call| T12

    %% Connections - Tools to Core
    T1 --> LLM
    T1 --> GRAPHDB
    T2 --> GRAPHDB
    T3 --> GRAPHDB
    T4 --> LLM
    T4 --> GRAPHDB
    T5 --> GRAPHDB
    T5 --> CONFIG
    T6 --> GRAPHDB
    T7 --> GRAPHDB
    T8 --> GRAPHDB
    T9 --> GRAPHDB
    T10 --> GRAPHDB
    T11 --> GRAPHDB
    T12 --> GRAPHDB

    %% Connections - Core to External
    LLM --> LLM_SVC
    GRAPHDB --> NEO4J
    CONFIG -.->|read| CONFIG
    
    style API fill:#e1f5ff
    style AGENT fill:#fff3e0
    style TOOLS fill:#f3e5f5
    style CORE fill:#e8f5e9
    style EXT fill:#fce4ec
    style INTENT_TOOLS fill:#ffe0b2
    style ELEMENT_TOOLS fill:#f8bbd0
    style PAGE_TOOLS fill:#c5e1a5
    style UTILITY_TOOLS fill:#b3e5fc
```

## Data Flow - Complete Request/Response Cycle

```mermaid
graph LR
    USER["👤 Frontend<br/>User Query"]
    
    USER -->|POST /api/chatbot/message| SERVER["🌐 FastAPI<br/>Server"]
    SERVER -->|ChatRequest| AGENT["🤖 LangGraph<br/>Agent"]
    
    AGENT -->|Tool Call| TOOLS["🛠️ Tools<br/>select best tool"]
    TOOLS -->|query| GRAPHDB["📊 Neo4j<br/>Graph DB"]
    
    GRAPHDB -->|results| TOOLS
    TOOLS -->|result| AGENT
    
    AGENT -->|iterate| TOOLS
    AGENT -->|final response| PARSER["🔄 Parser<br/>extract JSON"]
    PARSER -->|ChatResponse| SERVER
    SERVER -->|JSON payload| USER["Browser<br/>Floating Chat"]
    
    style USER fill:#c8e6c9
    style SERVER fill:#bbdefb
    style AGENT fill:#ffe0b2
    style TOOLS fill:#f8bbd0
    style GRAPHDB fill:#b3e5fc
    style PARSER fill:#f0f4c3
```

## Tool Interaction Map

```mermaid
graph TB
    USER["User Intent"]
    
    USER -->|"how do I...?"| SEARCH_INT["search_intents<br/>3 candidates"]
    SEARCH_INT -->|"get steps"| GET_STEPS["get_steps_for_intent<br/>ordered workflow"]
    
    USER -->|"search page"| FIND_PAGE["find_page<br/>keyword match"]
    FIND_PAGE -->|"browse"| PAGE_CONTENT["get_page_content<br/>all elements"]
    PAGE_CONTENT -->|"explore"| ELEMENT_DET["get_element_details<br/>properties"]
    
    USER -->|"find button"| SEARCH_TEXT["search_elements_by_text<br/>fuzzy match"]
    
    USER -->|"what to do here?"| INTENTS_PAGE["get_intents_by_page<br/>workflow suggestions"]
    
    USER -->|"semantic query"| SEARCH_ELEM["search_elements_by_intent<br/>vector similarity"]
    
    ELEMENT_DET -->|"needs to trigger"| FIND_TRIG["find_trigger_prerequisites<br/>what activates it"]
    
    GET_STEPS -->|"expand modal"| CONTAINER["get_container_content<br/>nested elements"]
    CONTAINER -->|"fill form"| FORM_FIELDS["get_form_fields_on_page<br/>inputs/selects"]
    
    USER -->|"custom query"| CYPHER["execute_cypher_read_query<br/>raw Neo4j"]
    
    style USER fill:#fff9c4
    style SEARCH_INT fill:#ffccbc
    style GET_STEPS fill:#ffab91
    style FIND_PAGE fill:#e1bee7
    style PAGE_CONTENT fill:#ce93d8
    style ELEMENT_DET fill:#ba68c8
    style FIND_TRIG fill:#ab47bc
    style SEARCH_TEXT fill:#90caf9
    style SEARCH_ELEM fill:#64b5f6
    style INTENTS_PAGE fill:#42a5f5
    style CONTAINER fill:#c8e6c9
    style FORM_FIELDS fill:#a5d6a7
    style CYPHER fill:#ffe082
```

## Neo4j Knowledge Graph Schema

```mermaid
graph TB
    subgraph NKG["Navigational Knowledge Graph Nodes & Relations"]
        PAGE["(p:Page)<br/>id: string<br/>title: string<br/>description: string"]
        
        ELEMENT["(e:Element)<br/>nkg_id: string<br/>id: string<br/>page_id: string<br/>type: string<br/>text: string<br/>description: string<br/>selector: string"]
        
        INTENT["(i:Intent)<br/>id: string<br/>label: string<br/>intent_type: string<br/>content: string<br/>category: string"]
        
        PAGE -->|CONTAINS| ELEMENT
        ELEMENT -->|TRIGGERS| ELEMENT
        INTENT -->|HAS_STEP<br/>order: int| ELEMENT
        PAGE -->|HAS_INTENT| INTENT
    end
    
    style PAGE fill:#bbdefb
    style ELEMENT fill:#c8e6c9
    style INTENT fill:#ffe0b2
```

## Core Layer - Configuration & Initialization

```mermaid
graph TB
    CONFIG["⚙️ Configuration Layer<br/>config.py"]
    
    CONFIG -->|reads .env| NEO4J_CFG["Neo4j<br/>- URI<br/>- User<br/>- Password"]
    CONFIG -->|reads .env| LLM_CFG["LLM<br/>- backend type<br/>- model name<br/>- temperature"]
    CONFIG -->|reads .env| EMBED_CFG["Embedding<br/>- model name<br/>- dimensions"]
    CONFIG -->|reads .env| AGT_CFG["Agent<br/>- search_top_n<br/>- fuzzy threshold<br/>- intent threshold"]
    
    CONFIG -->|Singleton| DRIVER["Driver<br/>get_driver()<br/>close_driver()"]
    CONFIG -->|Singleton| LLM["LLM Client<br/>get_llm()<br/>set_llm_mode()"]
    CONFIG -->|queries| SETTINGS["Settings<br/>get_settings()"]
    
    style CONFIG fill:#fff9c4
```

## LLM Integration Points

```mermaid
graph TB
    LLM_MGR["LLM Manager<br/>llm.py"]
    
    LLM_MGR -->|Backend Selection<br/>env: llm_backend| PROXY["Ollama Proxy<br/>GPU3 Server<br/>token auth"]
    LLM_MGR -->|Backend Selection| LOCAL["Local Ollama<br/>localhost:11434"]
    LLM_MGR -->|Backend Selection| OPENROUTER["OpenRouter API<br/>Chat API<br/>Models: Gemini,DeepSeek"]
    
    LLM_MGR -->|get_llm<br/>returns BaseChatModel| AGENT["ReAct Agent<br/>tool calling"]
    
    LLM_MGR -->|get_query_embedding<br/>vector embedding| VECTOR_SEARCH["Vector Search<br/>Intent & Element search"]
    
    LLM_MGR -->|get_document_embedding| EMBED_STORE["Embedding Storage<br/>Neo4j vector index"]
    
    style LLM_MGR fill:#fff3e0
    style PROXY fill:#ffccbc
    style LOCAL fill:#ffab91
    style OPENROUTER fill:#ff8a65
    style AGENT fill:#bbdefb
    style VECTOR_SEARCH fill:#c8e6c9
    style EMBED_STORE fill:#a5d6a7
```

## API Server Endpoints & Workflows

```mermaid
graph TD
    subgraph ENDPOINTS["API Endpoints"]
        EP1["POST /api/chatbot/message<br/>Primary chat endpoint"]
        EP2["POST /chat<br/>Legacy alias"]
        EP3["POST /api/chatbot/log<br/>Frontend debug logs"]
        EP4["GET /health<br/>Health check"]
    end
    
    subgraph CHAT_FLOW["Chat Processing"]
        PARSE_REQ["Parse ChatRequest<br/>- message<br/>- conversation_id<br/>- current_page<br/>- history"]
        
        INVOKE["Invoke Agent<br/>agent.invoke() or<br/>agent.stream()"]
        
        STREAM["Optional Streaming<br/>achat_stream() for<br/>real-time output"]
        
        ENRICH["Enrich Guidance<br/>resolve element metadata<br/>from NKG"]
        
        FORMAT_RESP["Format Response<br/>ChatResponse JSON"]
    end
    
    subgraph REVIEW_ENDPOINTS["Review Tools Endpoints"]
        REVIEW_NOTE["POST /review/intent/{intent_id}<br/>Add review note"]
        REVIEW_STATUS["POST /review/status<br/>Update review status"]
        REVERT["POST /review/revert<br/>Revert changes"]
        NODE_UPDATE["POST /node/update<br/>Update node metadata"]
    end
    
    EP1 --> PARSE_REQ
    EP2 --> PARSE_REQ
    PARSE_REQ --> INVOKE
    INVOKE --> STREAM
    STREAM --> ENRICH
    ENRICH --> FORMAT_RESP
    FORMAT_RESP --> EP1
    
    style ENDPOINTS fill:#e3f2fd
    style CHAT_FLOW fill:#f3e5f5
    style REVIEW_ENDPOINTS fill:#fce4ec
```

---

## Summary Statistics

| Component | Count | Details |
|-----------|-------|---------|
| **Tools** | 12 | Intent Discovery (3), Element Search (4), Page Navigation (4), Utility (1) |
| **Intent Tools** | 3 | search_intents, get_steps_for_intent, get_intents_by_page |
| **Element Tools** | 4 | search_elements_by_intent, search_elements_by_text, get_element_details, find_trigger_prerequisites |
| **Page Tools** | 4 | find_page, get_page_content, get_container_content, get_form_fields_on_page |
| **Utility Tools** | 1 | execute_cypher_read_query |
| **Core Modules** | 4 | config.py, llm.py, graph_db.py, |
| **API Endpoints** | 7 | /api/chatbot/message, /chat, /health, /api/chatbot/log, + review endpoints |
| **Neo4j Node Types** | 3 | Page, Element, Intent |
| **Neo4j Relationship Types** | 4 | CONTAINS, TRIGGERS, HAS_STEP, HAS_INTENT |
| **LLM Backends** | 3 | Ollama Proxy, Local Ollama, OpenRouter |

