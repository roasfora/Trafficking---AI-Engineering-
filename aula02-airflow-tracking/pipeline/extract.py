"""EXTRACT: ir buscar os dados a API e guardá-los em ficheiros temporarios.

Duas regras que este modulo ilustra:

1. Cada run processa UMA janela: [interval_start, interval_end). E o Airflow
   que decide a janela (data interval); o codigo apenas a recebe. Isto e o
   que torna um backfill possivel: correr o passado e passar-lhe outra janela.

2. As tasks NAO trocam datasets pelo XCom. O XCom vive na base de dados de
   metadados do Airflow e serve para mensagens pequenas. Os dados vao para
   ficheiros (aqui, uma pasta partilhada) e o que viaja e o CAMINHO.

Extract nao valida o conteudo: so garante que apanhou TUDO (paginacao) e que a
API respondeu com sucesso. Validar e o trabalho da task seguinte.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from pipeline.config import Settings, get_settings

log = logging.getLogger(__name__)

# Dimensoes: pedem-se sempre completas. Factos: pedem-se por janela.
# Ordem = ordem de carga (as FKs apontam para tras).
DIMENSION_ENDPOINTS = {
    "workspaces": "/workspaces",
    "traffic_sources": "/traffic-sources",
    "campaigns": "/campaigns",
    "offers": "/offers",
}
# Cada fact e janelada pelo SEU tempo: conversions por postback_timestamp,
# campaign_costs por datetime (hora), daily_control por date.
FACT_ENDPOINTS = {
    "conversions": "/conversions",
    "campaign_costs": "/campaign-costs",
    "daily_control": "/daily-control",
}


class ExtractError(Exception):
    """A extracao nao conseguiu garantir que apanhou tudo."""


def run_dir_for(settings: Settings, interval_start: datetime) -> Path:
    """Pasta dos ficheiros temporarios desta janela.

    Determinada pela janela, nao por um timestamp de "agora": voltar a correr
    a mesma janela escreve nos mesmos ficheiros (overwrite), nunca acumula lixo.
    """
    return settings.staging_dir / interval_start.strftime("%Y%m%dT%H%M%S")


def check_api(settings: Settings | None = None) -> dict[str, Any]:
    """Task `check_api`: a API esta viva? Falha cedo, antes de gastar trabalho.

    raise_for_status() transforma um 500 ou 429 numa excecao -> a task falha ->
    o Airflow decide o que fazer (retries, retry_delay, falha final).
    """
    settings = settings or get_settings()
    with httpx.Client(base_url=settings.api_base_url, timeout=settings.http_timeout_seconds) as client:
        response = client.get("/health")
        if response.status_code == 429:
            log.warning("API devolveu 429 (rate limit). Retry-After=%s", response.headers.get("Retry-After"))
        response.raise_for_status()
        elapsed_ms = round(response.elapsed.total_seconds() * 1000)
    log.info("API saudavel: %s em %d ms", response.json(), elapsed_ms)
    return {"status": "ok", "latency_ms": elapsed_ms}


def fetch_all(client: httpx.Client, path: str, params: dict[str, Any], page_size: int) -> list[dict]:
    """Percorre TODAS as paginas (limit/offset) e confirma que nao faltou nada.

    Sem esta verificacao, uma API que devolva so as primeiras 100 linhas de 437
    produziria dados incompletos SEM nenhum erro. `total` existe para isto.
    """
    rows: list[dict] = []
    offset = 0
    total: int | None = None
    while True:
        response = client.get(path, params={**params, "limit": page_size, "offset": offset})
        response.raise_for_status()
        body = response.json()
        page = body["data"]
        if total is None:
            total = body["total"]
        elif body["total"] != total:
            raise ExtractError(
                f"{path}: o total mudou a meio da paginacao ({total} -> {body['total']})"
            )
        rows.extend(page)
        offset += len(page)
        if not page or offset >= total:
            break
    if len(rows) != total:
        raise ExtractError(f"{path}: esperava {total} registos e recebi {len(rows)}")
    return rows


def _write_json(path: Path, rows: list[dict]) -> None:
    # Escreve para um temporario e renomeia: nunca fica um ficheiro a meio.
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows))
    os.replace(tmp, path)


def run_extract(interval_start: str, interval_end: str, settings: Settings | None = None) -> dict[str, Any]:
    """Task `extract`. Devolve apenas METADADOS (caminhos e contagens)."""
    settings = settings or get_settings()
    start = datetime.fromisoformat(interval_start)
    end = datetime.fromisoformat(interval_end)
    run_dir = run_dir_for(settings, start)
    run_dir.mkdir(parents=True, exist_ok=True)
    log.info("Janela: [%s, %s)  ->  %s", start.isoformat(), end.isoformat(), run_dir)

    window = {"start_date": start.isoformat(), "end_date": end.isoformat()}
    files: dict[str, str] = {}
    counts: dict[str, int] = {}
    with httpx.Client(base_url=settings.api_base_url, timeout=settings.http_timeout_seconds) as client:
        plan = {
            **{name: (path, {}) for name, path in DIMENSION_ENDPOINTS.items()},
            **{name: (path, window) for name, path in FACT_ENDPOINTS.items()},
        }
        for name, (path, params) in plan.items():
            rows = fetch_all(client, path, params, settings.page_size)
            target = run_dir / f"raw_{name}.json"
            _write_json(target, rows)
            files[name] = str(target)
            counts[name] = len(rows)
            log.info("%-16s %5d registos -> %s", name, len(rows), target.name)

    return {
        "run_dir": str(run_dir),
        "interval_start": start.isoformat(),
        "interval_end": end.isoformat(),
        "files": files,
        "counts": counts,
    }
