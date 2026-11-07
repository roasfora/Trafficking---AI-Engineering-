"""Um request concluido = uma linha em logs/requests.jsonl + um recibo legivel."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def estimate_model_cost(
    input_tokens: int | None,
    output_tokens: int | None,
    input_price_per_1m: float | None,
    output_price_per_1m: float | None,
) -> float | None:
    """USD estimados. None se faltarem precos ou tokens: nunca inventamos."""
    if None in (input_tokens, output_tokens, input_price_per_1m, output_price_per_1m):
        return None
    return round((input_tokens * input_price_per_1m + output_tokens * output_price_per_1m) / 1_000_000, 6)


def log_request(record: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def format_receipt(record: dict[str, Any]) -> str:
    def show(value: Any) -> str:
        return "n/d (o provider nao devolveu)" if value is None else str(value)

    cost = record["estimated_model_cost"]
    lines = [
        "REQUEST RECEIPT",
        "",
        "Question", record["question"], "",
        "Provider", record["provider"], "",
        "Model", record["model"], "",
        "Model calls", str(record["model_calls"]), "",
        "Tool calls", str(len(record["tool_calls"])), "",
        "Tools", *(record["tool_calls"] or ["-"]), "",
        "SQL", *(record["sql_queries"] or ["-"]), "",
        "Input tokens", show(record["input_tokens"]), "",
        "Output tokens", show(record["output_tokens"]), "",
        "Latency", f"{record['latency_ms']} ms", "",
        "Estimated model cost", "n/d (precos nao configurados)" if cost is None else f"{cost} USD", "",
        "Stopped by", record["stopped_by"],
    ]
    if record.get("error"):
        lines += ["", "Error", record["error"]]
    return "\n".join(lines)
