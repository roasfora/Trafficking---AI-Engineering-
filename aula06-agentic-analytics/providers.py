"""A unica fronteira entre o projeto e o fornecedor do modelo.

Tools, semantic layer, PostgreSQL, SQL guard e workflows nao sabem que modelo
esta por baixo. Trocar Bedrock por Ollama = mudar (provider, model_id).
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import replace
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from config import Settings

PROVIDER_LABELS = {"bedrock": "Amazon Bedrock", "ollama": "Ollama (Local)"}


def get_llm(provider: str, model_id: str, settings: Settings) -> BaseChatModel:
    if provider == "bedrock":
        if not model_id:
            raise RuntimeError("Bedrock model is not configured (model id is empty)")
        from langchain_aws import ChatBedrockConverse

        # Credenciais: credential chain normal da AWS (profile, SSO, role). Nada no repo.
        return ChatBedrockConverse(
            model=model_id, region_name=settings.aws_region, temperature=0, max_tokens=1024
        )

    if provider == "ollama":
        if not model_id:
            raise RuntimeError("No Ollama model selected")
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model_id, base_url=settings.ollama_base_url, temperature=0)

    raise ValueError(f"unknown provider: {provider!r} (bedrock | ollama)")


def with_model(settings: Settings, provider: str, model_id: str) -> Settings:
    """Settings para este (provider, modelo). Os precos configurados so valem para o
    modelo default do .env: noutro modelo o custo fica indisponivel (nunca um preco errado)."""
    if model_id != settings.model_name or provider != settings.llm_provider:
        settings = replace(settings, input_price_per_1m=None, output_price_per_1m=None, max_cost_per_request=None)
    if provider == "bedrock":
        return replace(settings, llm_provider=provider, bedrock_model_id=model_id)
    return replace(settings, llm_provider=provider, ollama_model=model_id)


def bedrock_models(settings: Settings) -> dict[str, str]:
    """Etiqueta -> model id dos modelos configurados. O BEDROCK_MODEL_ID do CLI tambem entra."""
    models = dict(settings.bedrock_models)
    if settings.bedrock_model_id and settings.bedrock_model_id not in models.values():
        models["Default (BEDROCK_MODEL_ID)"] = settings.bedrock_model_id
    return models


def discover_ollama_models(settings: Settings, timeout: float = 2.0) -> dict[str, Any]:
    """Pergunta ao Ollama local que modelos tem instalados (GET /api/tags).

    Nunca levanta excecao: devolve {"running": bool, "models": [...], "error": str | None}.
    Se o servidor responde mas a resposta nao se percebe, usa OLLAMA_MODELS como fallback.
    """
    url = settings.ollama_base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.load(response)
    except json.JSONDecodeError:
        return {"running": True, "models": list(settings.ollama_models), "error": "Unexpected response from Ollama"}
    except Exception:  # sem rede, recusado, timeout...
        return {"running": False, "models": [], "error": "Ollama is not running"}

    try:
        names = [m["name"] for m in payload["models"]]
    except (KeyError, TypeError):
        return {"running": True, "models": list(settings.ollama_models), "error": "Unexpected response from Ollama"}
    # embeddings nao conversam: fora da lista
    names = [n for n in names if "embed" not in n]
    return {"running": True, "models": names or list(settings.ollama_models), "error": None}


def aws_credentials_found() -> bool:
    """Ha credenciais na credential chain? Nao faz chamadas ao modelo nem a AWS."""
    if os.getenv("AWS_BEARER_TOKEN_BEDROCK"):  # API key do Bedrock: boto3 usa-a, mas nao e uma "credential"
        return True
    try:
        import boto3

        return boto3.Session().get_credentials() is not None
    except Exception:
        return False
