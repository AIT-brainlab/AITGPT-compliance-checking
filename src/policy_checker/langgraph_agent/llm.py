from __future__ import annotations

import os

from langchain_ollama import ChatOllama

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
SECOND_MODEL = os.getenv("OLLAMA_SECOND_MODEL", "mistral")  # override with glm-4.7-flash if pulled
SEED = int(os.getenv("OLLAMA_SEED", "42"))


def get_llm(model: str | None = None,
            temperature: float = 0.0,
            seed: int = SEED) -> ChatOllama:
    """Return a ChatOllama instance with deterministic decoding."""
    return ChatOllama(
        model=model or DEFAULT_MODEL,
        temperature=temperature,
        base_url=OLLAMA_HOST,
        model_kwargs={
            "seed": seed,
            "num_predict": 512,
            "top_k": 1,          # greedy decoding — redundant with temp=0 but explicit
            "top_p": 1.0,
        },
    )


def get_second_llm() -> ChatOllama:
    """Return the second-opinion LLM used by reclassify_node.
    Different seed so it's not literally the same sample twice."""
    return get_llm(model=SECOND_MODEL, seed=SEED + 1)
