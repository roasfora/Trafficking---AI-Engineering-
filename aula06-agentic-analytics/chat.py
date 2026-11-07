"""Funcoes puras do chat (sem Streamlit): historico e mensagens de erro amigaveis."""

from __future__ import annotations

import re
from typing import Any


def add_exchange(messages: list[dict], question: str, record: dict[str, Any]) -> None:
    """Acrescenta pergunta + resposta. Respostas falhadas ficam marcadas e nao voltam ao modelo."""
    messages.append({"role": "user", "content": question})
    if record["error"]:
        messages.append({"role": "assistant", "content": friendly_error(record), "failed": True, "record": record})
    else:
        messages.append({"role": "assistant", "content": record["answer"], "record": record})


def add_model_change(messages: list[dict], label: str) -> None:
    """Aviso visual. role='notice' nunca vai para o LLM (ver history_for_agent)."""
    messages.append({"role": "notice", "content": f"Model changed to {label}"})


def history_for_agent(messages: list[dict]) -> list[dict]:
    """So pares user/assistant bem-sucedidos, so texto."""
    return [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m["role"] in ("user", "assistant") and not m.get("failed")
    ]


def clear(messages: list[dict]) -> None:
    messages.clear()


def friendly_error(record: dict[str, Any]) -> str:
    """Erro tecnico (string "Tipo: msg") -> mensagem para a sala. Sem traceback."""
    raw = (record.get("error") or "").lower()
    if record.get("stopped_by") in ("max_model_calls", "max_tool_calls", "max_cost"):
        return "The agent reached its maximum number of turns."
    if "not configured" in raw or "model id is empty" in raw:
        return "Bedrock model is not configured."
    if "credentials" in raw:
        return "AWS credentials were not found."
    if "ollama" in raw or "11434" in raw:
        return "Could not connect to Ollama."
    if "accessdenied" in raw or "validationexception" in raw or "resourcenotfound" in raw:
        return "Bedrock rejected the request (check the model id, region and model access)."
    if "psycopg" in raw or "operationalerror" in raw or "connection refused" in raw:
        return "PostgreSQL is unavailable."
    return "Something went wrong while contacting the model. Enable technical details for more information."


def safe_details(record: dict[str, Any]) -> dict[str, Any]:
    """Campos do recibo para mostrar na UI. Nunca inclui nada alem do que ja vai para o log."""
    keys = [
        "provider", "model", "model_calls", "tool_calls", "sql_queries", "input_tokens",
        "output_tokens", "latency_ms", "estimated_model_cost", "stopped_by", "error",
    ]
    details = {k: record.get(k) for k in keys}
    if details["error"]:  # por defesa: nunca URLs/connection strings
        details["error"] = re.sub(r"\w+://\S+", "<redacted>", details["error"])
    return details
