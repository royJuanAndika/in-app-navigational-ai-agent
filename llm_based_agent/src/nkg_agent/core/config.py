"""
Centralized configuration loaded from .env using Pydantic Settings.

All settings are validated at startup — if a required variable is missing
from .env, the application fails fast with a clear error message.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve the .env file path relative to the llm_based_agent directory.
# This works regardless of where the script is invoked from.
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Application settings — sourced from environment variables / .env file."""

    # ── Neo4j ────────────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str

    # ── LLM Backend ───────────────────────────────────────────────────────
    # "proxy" = Ollama proxy (gpu3), "local" = local Ollama, "openrouter" = OpenRouter API
    llm_backend: str = "proxy"

    # ── Ollama Proxy ─────────────────────────────────────────────────────
    ollama_proxy_url: str
    ollama_proxy_token: str
    ollama_base_url: str = "http://localhost:11434"

    # ── OpenRouter ────────────────────────────────────────────────────────
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-2.5-flash-preview"

    # ── Models ───────────────────────────────────────────────────────────
    llm_model: str = "gemma4:latest"  # Used only for Ollama (proxy/local) modes
    embedding_model: str = "qwen3-embedding:8b"
    embedding_dimensions: int = 4096

    # ── Agent Behaviour ──────────────────────────────────────────────────
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4096
    search_top_n: int = 5
    fuzzy_match_threshold: int = 60  # minimum rapidfuzz score to keep
    intent_search_threshold: float = 0.0  # minimum cosine similarity for Intents

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


from typing import Optional


# ── Singleton accessor ───────────────────────────────────────────────────

_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Return the cached Settings instance (created on first call)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
