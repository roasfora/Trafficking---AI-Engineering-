"""Pipeline do TrafficJunky: tudo o que e ESPECIFICO deste provider.

    check_api >> extract >> validate_source >> transform >> validate_canonical >> load >> reconcile
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^   (os restantes sao comuns: pipeline/)
    especificos deste provider

O DAG nao faz nada disto: so chama estas funcoes. "O Airflow orquestra; nao transforma."

Regras do provider (versao pedagogica dos tickets):

* pedir as stats de UM dia: startDate = endDate = DD/MM/YYYY, sem timezone, todas as paginas;
* ignorar campanhas do tipo `deal`;
* mapear cada campanha do provider para a nossa (dim_campaign) POR NOME;
* campanhas SEM correspondencia: descartadas e registadas (a reconciliacao revela o impacto);
* campanhas com o MESMO nome: agregadas numa so linha (somam-se as metricas base).
"""

from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pandas as pd

from contracts.trafficjunky import TJStatsPage, TJTotal
from pipeline import http, load
from pipeline.config import Settings, get_settings
from pipeline.raw import raw_path, save_json, save_raw, staging_path
from pipeline.validate import ContractViolation, read_json, validate_payload

log = logging.getLogger(__name__)

PROVIDER = "trafficjunky"
FOUR = Decimal("0.0001")


class ExtractError(Exception):
    """A extracao nao conseguiu garantir que apanhou tudo."""


# --------------------------------------------------------------------------
# check_api
# --------------------------------------------------------------------------

def check_api(settings: Settings | None = None) -> dict[str, Any]:
    """Task `check_api`: o provider responde? Falha cedo, antes de gastar trabalho."""
    settings = settings or get_settings()
    p = settings.trafficjunky
    if not p.health_path:
        log.info("%s: sem health check dedicado configurado; nada a verificar", PROVIDER)
        return {"status": "skipped"}
    with http.make_client(p, settings.http_timeout_seconds) as client:
        response = http.get(client, p.health_path)
    log.info("%s saudavel: HTTP %d em %d ms", PROVIDER, response.status_code, response.elapsed.total_seconds() * 1000)
    return {"status": "ok"}


# --------------------------------------------------------------------------
# extract
# --------------------------------------------------------------------------

def _fetch_pages(client, p, day: date, page_size: int) -> tuple[list[str], int]:
    """Percorre TODAS as paginas (limit/offset) e devolve os corpos RAW (texto).

    Confirma que nao faltou nada (len(linhas) == total). Sem esta verificacao, um
    provider que devolva so as primeiras 5 de 12 linhas daria dados incompletos SEM
    nenhum erro.
    """
    # O TrafficJunky pede datas como DD/MM/YYYY e nao recebe timezone.
    when = day.strftime("%d/%m/%Y")
    bodies: list[str] = []
    received = 0
    offset = 0
    total: int | None = None
    while True:
        response = http.get(client, p.stats_path,
                            {"startDate": when, "endDate": when, "limit": page_size, "offset": offset})
        bodies.append(response.text)
        body = json.loads(response.text)
        page, page_total = body.get("data"), body.get("total")
        if not isinstance(page, list) or not isinstance(page_total, int):
            # estrutura partida: guardamos o raw e deixamos o validate_source explicar
            log.warning("%s: resposta sem data/total; a parar a paginacao", PROVIDER)
            return bodies, received
        if total is not None and page_total != total:
            raise ExtractError(f"o total mudou a meio da paginacao ({total} -> {page_total})")
        total = page_total
        received += len(page)
        offset += len(page)
        if not page or offset >= total:
            break
    if received != total:
        raise ExtractError(f"esperava {total} campanhas e recebi {received}")
    return bodies, received


def extract(day: date, settings: Settings | None = None) -> dict[str, Any]:
    """Task `extract`: stats do dia -> data/raw/.../response.json. Devolve so METADADOS."""
    settings = settings or get_settings()
    p = settings.trafficjunky
    with http.make_client(p, settings.http_timeout_seconds) as client:
        bodies, received = _fetch_pages(client, p, day, settings.page_size)
    path = raw_path(settings, PROVIDER, day)
    save_raw(path, bodies)
    log.info("%s %s: %d campanhas em %d paginas -> %s", PROVIDER, day, received, len(bodies), path)
    return {"provider": PROVIDER, "date": day.isoformat(), "raw_path": str(path),
            "pages": len(bodies), "rows_fetched": received, "currency": p.currency}


# --------------------------------------------------------------------------
# validate_source
# --------------------------------------------------------------------------

def validate_source(meta: dict[str, Any]) -> dict[str, Any]:
    """Task `validate_source`: o payload tem a forma do CONTRATO DO PROVIDER?

    Campo obrigatorio em falta, tipo errado ou campo renomeado => a task falha.
    """
    pages = read_json(meta["raw_path"])["pages"]
    failures = []
    for i, page in enumerate(pages):
        try:
            validate_payload(TJStatsPage, page, f"{PROVIDER} {meta['date']} pagina {i}")
        except ContractViolation as exc:
            failures.append(str(exc))
    if failures:
        raise ContractViolation(" | ".join(failures))
    log.info("%s: %d paginas validas no contrato do provider", PROVIDER, len(pages))
    return {**meta, "source_valid": True}


# --------------------------------------------------------------------------
# transform
# --------------------------------------------------------------------------

def build_canonical(
    stats: list[dict[str, Any]], mapping: dict[str, UUID], day: date, currency: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Linhas do provider -> linhas no modelo canonico (funcao pura, testavel).

    Devolve (linhas, contagens). Usa Pandas para o que e tabular (filtrar, juntar
    com a dimensao, agregar); o dinheiro continua em Decimal (colunas `object`).
    """
    counts: dict[str, Any] = {"fetched": len(stats), "deals_skipped": 0,
                              "unmapped_dropped": 0, "unmapped_names": [], "merged": 0, "saved": 0}
    if not stats:
        return [], counts

    df = pd.DataFrame(stats, columns=["campaign_name", "campaign_type", "impressions", "clicks", "cost"])

    # 1. ignorar deals
    is_deal = df["campaign_type"] == "deal"
    counts["deals_skipped"] = int(is_deal.sum())
    df = df[~is_deal].copy()

    # 2. mapear a campanha do provider para a NOSSA, por nome
    df["campaign_id"] = df["campaign_name"].map(mapping)
    unmatched = df[df["campaign_id"].isna()]
    if len(unmatched):
        names = sorted(set(unmatched["campaign_name"]))
        counts["unmapped_dropped"] = len(unmatched)
        counts["unmapped_names"] = names
        # Na realidade: Sentry, nivel critical. Aqui: log. Nao e um erro de DADOS
        # (o registo e valido); e uma campanha que nao sabemos mapear.
        log.critical("%s: %d campanhas sem correspondencia em dim_campaign (descartadas): %s",
                     PROVIDER, len(unmatched), names)
    df = df[df["campaign_id"].notna()]

    # 3. campanhas com o mesmo nome: uma so linha, somando as metricas BASE.
    #    (Os racios do provider nao se somam, e nao os usamos.)
    counts["merged"] = int(len(df) - df["campaign_id"].nunique())
    if counts["merged"]:
        dup = sorted(set(df[df["campaign_id"].duplicated(keep=False)]["campaign_name"]))
        log.critical("%s: nomes de campanha duplicados (agregados): %s", PROVIDER, dup)
    out = df.groupby("campaign_id", as_index=False).agg(
        impressions=("impressions", "sum"), clicks=("clicks", "sum"), cost=("cost", "sum"))

    rows = [
        {
            "date": day.isoformat(), "provider": PROVIDER, "campaign_id": str(r.campaign_id),
            "source_specific_id": None,  # o TrafficJunky nao tem este nivel
            "currency": currency, "impressions": int(r.impressions), "clicks": int(r.clicks),
            "cost": Decimal(r.cost).quantize(FOUR),
        }
        for r in out.itertuples()
    ]
    counts["saved"] = len(rows)
    return rows, counts


def transform(meta: dict[str, Any], mapping: dict[str, UUID] | None = None,
              settings: Settings | None = None) -> dict[str, Any]:
    """Task `transform`: raw -> linhas no modelo canonico (data/staging/.../canonical.json)."""
    settings = settings or get_settings()
    day = date.fromisoformat(meta["date"])
    if mapping is None:
        mapping = load.fetch_campaign_mapping()  # cria o schema se for a 1.a run

    pages = [TJStatsPage.model_validate(p) for p in read_json(meta["raw_path"])["pages"]]
    stats = [s.model_dump() for page in pages for s in page.data]
    rows, counts = build_canonical(stats, mapping, day, meta["currency"])

    path = staging_path(settings, PROVIDER, day)
    save_json(path, rows)
    log.info("%s %s: fetched=%d deals_skipped=%d dropped=%d merged=%d saved=%d",
             PROVIDER, day, counts["fetched"], counts["deals_skipped"],
             counts["unmapped_dropped"], counts["merged"], counts["saved"])
    return {**meta, "staging_path": str(path), "counts": counts}


# --------------------------------------------------------------------------
# total de controlo (usado pela reconciliacao)
# --------------------------------------------------------------------------

def fetch_api_total(meta: dict[str, Any], settings: Settings | None = None) -> tuple[Decimal, str]:
    """Total de CONTROLO do dia, vindo da API e INDEPENDENTE do detalhe extraido.

    Estrategias (TRAFFICJUNKY_TOTAL_STRATEGY):

    summary_endpoint  um endpoint de totais separado (o do mock). Se o detalhe vier
                      incompleto, o total continua correto: e isto que permite a
                      reconciliacao apanhar dados em falta.
    refetch_stats     voltar a pedir as stats e somar o custo das campanhas nao-deal.
                      E o que os tickets descrevem, mas NAO e independente do detalhe:
                      se o endpoint de detalhe esta truncado, trunca os dois.
    """
    settings = settings or get_settings()
    p = settings.trafficjunky
    day = date.fromisoformat(meta["date"])
    with http.make_client(p, settings.http_timeout_seconds) as client:
        if p.total_strategy == "refetch_stats":
            bodies, _ = _fetch_pages(client, p, day, settings.page_size)
            pages = [TJStatsPage.model_validate(json.loads(b, parse_float=Decimal)) for b in bodies]
            total = sum((s.cost for pg in pages for s in pg.data if s.campaign_type != "deal"), Decimal("0"))
            return total, p.currency
        if p.total_strategy != "summary_endpoint":
            raise ValueError(f"TRAFFICJUNKY_TOTAL_STRATEGY invalida: {p.total_strategy}")
        response = http.get(client, p.total_path, {"date": day.isoformat()})
    summary = validate_payload(TJTotal, json.loads(response.text, parse_float=Decimal), f"{PROVIDER} total")
    return summary.total_cost, summary.currency
