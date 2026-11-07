"""O agente controlado: um ciclo explicito, com limites, sobre 3 tools.

LangChain faz: abstracao do modelo (bind_tools / invoke) e definicao das tools.
O CICLO e nosso (30 linhas), para os limites e o log serem visiveis em sala.
Menos liberdade: so 3 tools, so uma tabela, so SELECT, e um maximo de passos.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from config import Settings, get_settings
from observability import estimate_model_cost, log_request
from providers import get_llm, with_model
from tools.catalog import get_dataset_metadata
from tools.metrics import get_metric_definition
from tools.postgres import run_postgres_query

MAX_HISTORY_MESSAGES = 10

PROMPTS = Path(__file__).resolve().parent / "prompts"

# O docstring de cada funcao e a descricao que o modelo ve.
ALL_TOOLS = [tool(get_metric_definition), tool(get_dataset_metadata), tool(run_postgres_query)]
NAIVE_TOOLS = [t for t in ALL_TOOLS if t.name != "get_metric_definition"]


def build_system_prompt(settings: Settings, naive: bool) -> str:
    text = (PROMPTS / ("system_naive.md" if naive else "system.md")).read_text(encoding="utf-8")
    today = settings.as_of_date
    return text.replace("{today}", today.isoformat()).replace("{yesterday}", (today - timedelta(days=1)).isoformat())


def history_to_messages(history: list[dict] | None) -> list:
    """[{"role": "user"|"assistant", "content": str}] -> mensagens LangChain.
    Curto de proposito: so as ultimas MAX_HISTORY_MESSAGES. Sem memoria de longo prazo."""
    classes = {"user": HumanMessage, "assistant": AIMessage}
    return [classes[m["role"]](m["content"]) for m in (history or [])[-MAX_HISTORY_MESSAGES:] if m["role"] in classes]


def run_agent(
    question: str,
    settings: Settings | None = None,
    naive: bool = False,
    llm: Any = None,
    history: list[dict] | None = None,
    provider: str | None = None,
    model_id: str | None = None,
) -> dict[str, Any]:
    """Responde a uma pergunta. Devolve o registo completo (resposta + recibo, o mesmo que vai para o log).

    CLI e Streamlit chamam esta mesma funcao. `provider`/`model_id` escolhem o modelo
    por pedido; sem eles usa o .env. `history` e a conversa anterior (so texto)."""
    settings = settings or get_settings()
    if provider or model_id:
        settings = with_model(settings, provider or settings.llm_provider, model_id or settings.model_name)
    tools = NAIVE_TOOLS if naive else ALL_TOOLS
    tools_by_name = {t.name: t for t in tools}

    record: dict[str, Any] = {
        "request_id": uuid.uuid4().hex[:12],
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question": question,
        "naive": naive,
        "provider": settings.llm_provider,
        "model": settings.model_name,
        "model_calls": 0,
        "tool_calls": [],
        "input_tokens": None,
        "output_tokens": None,
        "latency_ms": None,
        "sql_queries": [],
        "estimated_model_cost": None,
        "stopped_by": None,
        "answer": None,
        "error": None,
    }
    started = time.perf_counter()

    try:
        model = (llm or get_llm(settings.llm_provider, settings.model_name, settings)).bind_tools(tools)
        messages = [SystemMessage(build_system_prompt(settings, naive)), *history_to_messages(history), HumanMessage(question)]

        while True:
            if record["model_calls"] >= settings.max_model_calls:
                record["stopped_by"] = "max_model_calls"
                break
            ai: AIMessage = model.invoke(messages)
            record["model_calls"] += 1
            _add_usage(record, ai)
            record["estimated_model_cost"] = estimate_model_cost(
                record["input_tokens"], record["output_tokens"],
                settings.input_price_per_1m, settings.output_price_per_1m,
            )
            messages.append(ai)

            if not ai.tool_calls:
                record["answer"] = _text(ai)
                record["stopped_by"] = "end_turn"
                break
            if (
                settings.max_cost_per_request is not None
                and record["estimated_model_cost"] is not None
                and record["estimated_model_cost"] > settings.max_cost_per_request
            ):
                record["stopped_by"] = "max_cost"
                break
            if len(record["tool_calls"]) + len(ai.tool_calls) > settings.max_tool_calls:
                record["stopped_by"] = "max_tool_calls"
                break

            for call in ai.tool_calls:
                record["tool_calls"].append(call["name"])
                if call["name"] == "run_postgres_query":
                    record["sql_queries"].append(call["args"].get("sql", ""))
                result = _run_tool(tools_by_name, call)
                messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

        if record["answer"] is None:
            record["answer"] = f"Nao consegui concluir dentro dos limites ({record['stopped_by']})."
    except Exception as exc:  # falha do modelo/rede: regista e devolve, nao esconde
        record["stopped_by"] = "error"
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        record["latency_ms"] = int((time.perf_counter() - started) * 1000)
        log_request(record, settings.log_path)
    return record


def _run_tool(tools_by_name: dict, call: dict) -> Any:
    """Tools desconhecidas ou com argumentos errados voltam como erro ao modelo."""
    if call["name"] not in tools_by_name:
        return {"error": f"Unknown tool {call['name']}", "available_tools": list(tools_by_name)}
    try:
        return tools_by_name[call["name"]].invoke(call["args"])
    except Exception as exc:
        return {"error": f"Tool failed: {type(exc).__name__}: {exc}"}


def _add_usage(record: dict, ai: AIMessage) -> None:
    """Soma tokens se o provider os devolveu; senao fica None (nunca inventamos)."""
    usage = getattr(ai, "usage_metadata", None)
    if not usage:
        return
    record["input_tokens"] = (record["input_tokens"] or 0) + usage.get("input_tokens", 0)
    record["output_tokens"] = (record["output_tokens"] or 0) + usage.get("output_tokens", 0)


def _text(ai: AIMessage) -> str:
    if isinstance(ai.content, str):
        return ai.content
    return "".join(b.get("text", "") for b in ai.content if isinstance(b, dict) and b.get("type") == "text")
