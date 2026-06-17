"""
LLM and Embedding clients.

LLM backends supported (controlled by ``LLM_BACKEND`` in .env):
  - ``proxy``       → ChatOllama via Ollama proxy (gpu3 server)
  - ``local``       → ChatOllama via local Ollama instance
  - ``openrouter``  → ChatOpenAI via OpenRouter API

Embedding always uses Ollama (proxy or local) — OpenRouter does not serve embeddings.
"""

import logging

import requests
from typing import Optional, Literal
from langchain_core.language_models.chat_models import BaseChatModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .config import get_settings

logger = logging.getLogger(__name__)

# ── Asymmetric instructions for retrieval ────────────────────────────────
# For Element Search (Finding buttons/inputs at runtime)
ELEMENT_QUERY_INSTRUCTION = (
    "Given a user's navigation intent or action description, "
    "find the most relevant UI element in the web application "
    "that the user wants to interact with."
)

# For Intent Search (Finding FAQ help content at runtime)
INTENT_QUERY_INSTRUCTION = (
    "Represent a user's question about an HR SaaS platform for "
    "retrieving the most relevant navigational intent or help content."
)

# For Intent Storage (The 'Document' side for Phase 4)
INTENT_DOC_INSTRUCTION = (
    "Represent a user's navigation intent or knowledge query in a HR SaaS platform "
    "so that it can be retrieved when a user asks a related question."
)


# ── LLM ─────────────────────────────────────────────────────────────────

_llm: Optional[BaseChatModel] = None
_mode: str = "proxy"  # tracks embedding mode (proxy | local)


def set_llm_mode(mode: str):
    """Set the embedding mode (proxy or local). Does NOT control LLM backend.
    
    The LLM backend is controlled by LLM_BACKEND in .env.
    This function is kept for backward compatibility with the pipeline CLI.
    """
    global _mode, _llm
    _mode = mode
    _llm = None  # Reset cached LLM to force re-initialization


def init_llm(mode: str = "proxy") -> BaseChatModel:
    """Initialize the global LLM instance based on LLM_BACKEND setting.
    
    The ``mode`` parameter controls the *embedding* backend (proxy|local).
    The *LLM* backend is always read from settings.llm_backend.
    """
    global _llm, _mode
    _mode = mode
    s = get_settings()

    backend = s.llm_backend.lower()
    logger.info("LLM backend: %s", backend)

    if backend == "openrouter":
        from langchain_openai import ChatOpenAI
        if not s.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is not set in .env but LLM_BACKEND=openrouter")
        _llm = ChatOpenAI(
            model=s.openrouter_model,
            api_key=s.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=s.llm_temperature,
            max_tokens=s.llm_max_tokens,
            timeout=300,
        )
        logger.info("ChatOpenAI (OpenRouter) initialized: model=%s", s.openrouter_model)

    elif backend == "local":
        from langchain_ollama import ChatOllama
        _llm = ChatOllama(
            model=s.llm_model,
            base_url=s.ollama_base_url,
            temperature=s.llm_temperature,
            num_predict=s.llm_max_tokens,
            timeout=300,
        )
        logger.info("ChatOllama initialized (local): model=%s, base_url=%s", s.llm_model, s.ollama_base_url)

    else:  # proxy (default, gpu3 server)
        from langchain_ollama import ChatOllama
        _llm = ChatOllama(
            model=s.llm_model,
            base_url=s.ollama_proxy_url,
            client_kwargs={
                "headers": {"X-API-Token": s.ollama_proxy_token},
                "timeout": 300,
            },
            temperature=s.llm_temperature,
            num_predict=s.llm_max_tokens,
            timeout=300,
        )
        logger.info("ChatOllama initialized (proxy): model=%s, base_url=%s", s.llm_model, s.ollama_proxy_url)

    return _llm


def get_llm() -> BaseChatModel:
    """Return the cached LLM instance, initializing from LLM_BACKEND if needed."""
    global _llm
    if _llm is None:
        init_llm()
    return _llm


# ── Embedding (always Ollama) ────────────────────────────────────────────

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    reraise=True
)
def get_embedding(prompt: str) -> list[float]:
    """Internal helper to call the Ollama embedding API with a raw prompt.
    
    Embedding always uses Ollama regardless of LLM_BACKEND.
    _mode controls whether to use the proxy or local Ollama for embeddings.
    """
    s = get_settings()
    if _mode == "local":
        url = f"{s.ollama_base_url.rstrip('/')}/api/embeddings"
        headers = {}
    else:
        url = f"{s.ollama_proxy_url.rstrip('/')}/api/embeddings"
        headers = {"X-API-Token": s.ollama_proxy_token}

    response = requests.post(
        url,
        json={"model": s.embedding_model, "prompt": prompt},
        headers=headers,
        timeout=60,
    )
    
    # Check for transient server errors (like 502 Bad Gateway) and raise to trigger retry
    response.raise_for_status()
    
    embedding = response.json()["embedding"]
    return embedding


def get_query_embedding(text: str, mode: Literal["element", "intent"] = "element") -> list[float]:
    """Embed *text* using the asymmetric query instruction.

    The prompt is formatted as ``Instruct: {INSTRUCTION}\\nQuery: {text}``
    so the vector lands near the pre-stored document embeddings in the HNSW index.
    """
    if mode == "intent":
        instruction = INTENT_QUERY_INSTRUCTION
    else:
        instruction = ELEMENT_QUERY_INSTRUCTION

    prompt = f"Instruct: {instruction}\nQuery: {text}"
    embedding = get_embedding(prompt)
    logger.debug("Embedded query (%s, %d dims): %s…", mode, len(embedding), text[:60])
    return embedding
