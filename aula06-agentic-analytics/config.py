"""Configuracao: tudo vem do ambiente (.env). Sem segredos no codigo."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _float_or_none(name: str) -> float | None:
    value = os.getenv(name, "").strip()
    return float(value) if value else None


@dataclass(frozen=True)
class Settings:
    database_url: str
    llm_provider: str
    aws_region: str
    bedrock_model_id: str
    bedrock_models: dict[str, str]  # etiqueta na UI -> model id (so os configurados)
    ollama_models: tuple[str, ...]  # fallback se a descoberta automatica falhar
    ollama_model: str
    ollama_base_url: str
    input_price_per_1m: float | None
    output_price_per_1m: float | None
    max_model_calls: int
    max_tool_calls: int
    max_cost_per_request: float | None
    as_of_date: date
    log_path: Path
    statement_timeout_ms: int = 5000
    max_rows: int = 200
    max_query_length: int = 2000

    @property
    def model_name(self) -> str:
        return self.bedrock_model_id if self.llm_provider == "bedrock" else self.ollama_model


# etiqueta mostrada na UI -> variavel de ambiente com o model id. Nada de ids inventados.
BEDROCK_MODEL_VARS = {
    "Nova 2 Lite": "BEDROCK_NOVA2_LITE_MODEL_ID",
    "Nova Lite": "BEDROCK_NOVA_LITE_MODEL_ID",
    "Claude Haiku": "BEDROCK_CLAUDE_HAIKU_MODEL_ID",
    "GPT Terra": "BEDROCK_GPT_TERRA_MODEL_ID",
}


def _bedrock_models() -> dict[str, str]:
    models = {label: os.getenv(var, "").strip() for label, var in BEDROCK_MODEL_VARS.items()}
    return {label: model_id for label, model_id in models.items() if model_id}  # vazio => fora da UI


def get_settings() -> Settings:
    as_of = os.getenv("AS_OF_DATE", "").strip()
    return Settings(
        database_url=os.getenv(
            "DATABASE_URL", "postgresql://analytics_agent:agent_dev@localhost:5434/analytics"
        ),
        llm_provider=os.getenv("LLM_PROVIDER", "bedrock").strip().lower(),
        aws_region=os.getenv("AWS_REGION", "eu-north-1"),
        bedrock_model_id=os.getenv("BEDROCK_MODEL_ID", "").strip(),
        bedrock_models=_bedrock_models(),
        ollama_models=tuple(m.strip() for m in os.getenv("OLLAMA_MODELS", "").split(",") if m.strip()),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen3:8b"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        input_price_per_1m=_float_or_none("MODEL_INPUT_PRICE_PER_1M"),
        output_price_per_1m=_float_or_none("MODEL_OUTPUT_PRICE_PER_1M"),
        max_model_calls=int(os.getenv("MAX_MODEL_CALLS", "6")),
        max_tool_calls=int(os.getenv("MAX_TOOL_CALLS", "8")),
        max_cost_per_request=_float_or_none("MAX_COST_PER_REQUEST"),
        as_of_date=date.fromisoformat(as_of) if as_of else date.today(),
        log_path=Path(os.getenv("LOG_PATH", BASE_DIR / "logs" / "requests.jsonl")),
    )
