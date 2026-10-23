"""Pipeline da Erobella: tudo o que e ESPECIFICO deste provider.

Chegou um segundo provider e o schema e completamente diferente do TrafficJunky:

                     TrafficJunky                Erobella
    estrutura        uma lista paginada          tres partes (by_day_creative, by_creative, by_day)
    nivel            campanha                    CREATIVE
    campanha         pelo NOME                   escondida num LINK (UUID dentro do URL)
    duplicados       agregam-se                  nao ha: cada creative e uma linha
    total de dia     endpoint a parte            dentro da propria resposta (by_day)

A forma da pipeline e a mesma (check_api >> extract >> validate_source >> transform
>> validate_canonical >> load >> reconcile). Mudam as regras do provider, e o
resultado converge no MESMO modelo canonico.

Regras (versao pedagogica dos tickets):

* ler by_day_creative; ir buscar o `link` do creative a by_creative pelo `label`;
* extrair do link o UUID da campanha (extract_campaign_id);
* creative SEM link, ou cujo link nao tem UUID, ou cujo UUID nao e uma campanha nossa:
  descartado e registado (a reconciliacao revela o impacto);
* source_specific_id = label do creative.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pandas as pd

from contracts.erobella import EroResponse
from pipeline import http, load
from pipeline.config import Settings, get_settings
from pipeline.raw import raw_path, save_json, save_raw, staging_path
from pipeline.validate import ContractViolation, read_json, validate_payload

log = logging.getLogger(__name__)

PROVIDER = "erobella"
FOUR = Decimal("0.0001")

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_VCID = re.compile(rf"[?&]vcid=({_UUID})(?![0-9a-fA-F-])")
_PATH = re.compile(rf"/({_UUID})(?=[/?#]|$)")


def extract_campaign_id(link: str | None) -> UUID | None:
    """O UUID da campanha dentro do link de um creative, ou None.

    Dois formatos (os mesmos que o ep-tasks reconhece para o Pushground):

        https://trk.example/<uuid>?creative=x       UUID no caminho, seguido de ? / # ou fim
        https://trk.example/click?vcid=<uuid>&...   parametro vcid

    Se houver os dois, `vcid` ganha (e explicito). Devolve None se o link nao existir
    ou nao tiver UUID: nunca levanta excecao para um link estranho.
    """
    if not isinstance(link, str) or not link:  # None, "" ou NaN (creative sem linha em by_creative)
        return None
    match = _VCID.search(link) or _PATH.search(link)
    return UUID(match.group(1)) if match else None


# --------------------------------------------------------------------------
# check_api / extract / validate_source
# --------------------------------------------------------------------------

def check_api(settings: Settings | None = None) -> dict[str, Any]:
    """Task `check_api`: o provider responde? Falha cedo, antes de gastar trabalho."""
    settings = settings or get_settings()
    p = settings.erobella
    if not p.health_path:
        log.info("%s: sem health check dedicado configurado; nada a verificar", PROVIDER)
        return {"status": "skipped"}
    with http.make_client(p, settings.http_timeout_seconds) as client:
        response = http.get(client, p.health_path)
    log.info("%s saudavel: HTTP %d", PROVIDER, response.status_code)
    return {"status": "ok"}


def extract(day: date, settings: Settings | None = None) -> dict[str, Any]:
    """Task `extract`: stats do dia -> data/raw/.../response.json. Devolve so METADADOS.

    A resposta vem de uma so vez (as tres partes juntas): nao ha paginacao.
    """
    settings = settings or get_settings()
    p = settings.erobella
    with http.make_client(p, settings.http_timeout_seconds) as client:
        response = http.get(client, p.stats_path, {"start_date": day.isoformat(), "end_date": day.isoformat()})
    body = json.loads(response.text)
    path = raw_path(settings, PROVIDER, day)
    save_raw(path, [response.text])
    rows = len(body.get("by_day_creative", [])) if isinstance(body, dict) else 0
    log.info("%s %s: %d linhas de desempenho -> %s", PROVIDER, day, rows, path)
    return {"provider": PROVIDER, "date": day.isoformat(), "raw_path": str(path),
            "pages": 1, "rows_fetched": rows, "currency": p.currency}


def validate_source(meta: dict[str, Any]) -> dict[str, Any]:
    """Task `validate_source`: o payload tem a forma do CONTRATO DO PROVIDER?"""
    (page,) = read_json(meta["raw_path"])["pages"]
    validate_payload(EroResponse, page, f"{PROVIDER} {meta['date']}")
    log.info("%s: resposta valida no contrato do provider", PROVIDER)
    return {**meta, "source_valid": True}


# --------------------------------------------------------------------------
# transform
# --------------------------------------------------------------------------

def build_canonical(
    day_creative: list[dict[str, Any]], creatives: list[dict[str, Any]],
    known_campaigns: set[UUID], day: date, currency: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Linhas do provider -> linhas no modelo canonico (funcao pura, testavel)."""
    counts: dict[str, Any] = {"fetched": len(day_creative), "other_days_skipped": 0, "no_link_dropped": 0,
                              "no_campaign_id_dropped": 0, "unknown_campaign_dropped": 0,
                              "dropped_labels": [], "merged": 0, "saved": 0}
    if not day_creative:
        return [], counts

    df = pd.DataFrame(day_creative, columns=["date", "label", "impressions", "clicks", "cost_eur"])
    # (a resposta pode trazer varios dias; so queremos o desta run)
    same_day = df["date"].astype(str) == day.isoformat()
    counts["other_days_skipped"] = int((~same_day).sum())
    df = df[same_day]

    # 1. ir buscar o link ao creative, pelo label (left join: nao perde linhas de desempenho)
    links = (pd.DataFrame(creatives, columns=["label", "link"]) if creatives
             else pd.DataFrame(columns=["label", "link"]))
    links = links.drop_duplicates("label")
    df = df.merge(links, on="label", how="left")

    # 2. do link, o UUID da campanha
    df["campaign_id"] = df["link"].map(extract_campaign_id)

    # 3. o que nao conseguimos mapear para o nosso dominio: descartado e registado
    no_link = df["link"].isna() | (df["link"] == "")
    no_uuid = ~no_link & df["campaign_id"].isna()
    unknown = df["campaign_id"].notna() & ~df["campaign_id"].isin(known_campaigns)
    counts["no_link_dropped"] = int(no_link.sum())
    counts["no_campaign_id_dropped"] = int(no_uuid.sum())
    counts["unknown_campaign_dropped"] = int(unknown.sum())
    bad = no_link | no_uuid | unknown
    if bad.any():
        counts["dropped_labels"] = sorted(df[bad]["label"])
        # Na realidade: Sentry, nivel critical.
        log.critical("%s: %d creatives sem campanha identificavel (descartados): sem link=%s, link sem UUID=%s, "
                     "campanha desconhecida=%s", PROVIDER, int(bad.sum()),
                     sorted(df[no_link]["label"]), sorted(df[no_uuid]["label"]), sorted(df[unknown]["label"]))
    df = df[~bad]

    rows = [
        {
            "date": day.isoformat(), "provider": PROVIDER, "campaign_id": str(r.campaign_id),
            "source_specific_id": r.label,  # o creative e o nivel de detalhe da Erobella
            "currency": currency, "impressions": int(r.impressions), "clicks": int(r.clicks),
            "cost": Decimal(r.cost_eur).quantize(FOUR),
        }
        for r in df.sort_values("label").itertuples()
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

    (page,) = read_json(meta["raw_path"])["pages"]
    resp = EroResponse.model_validate(page)
    rows, counts = build_canonical(
        [r.model_dump() for r in resp.by_day_creative], [c.model_dump() for c in resp.by_creative],
        set(mapping.values()), day, meta["currency"])

    path = staging_path(settings, PROVIDER, day)
    save_json(path, rows)
    dropped = counts["no_link_dropped"] + counts["no_campaign_id_dropped"] + counts["unknown_campaign_dropped"]
    log.info("%s %s: fetched=%d dropped=%d saved=%d", PROVIDER, day, counts["fetched"], dropped, counts["saved"])
    return {**meta, "staging_path": str(path), "counts": counts}


# --------------------------------------------------------------------------
# total de controlo (usado pela reconciliacao)
# --------------------------------------------------------------------------

def fetch_api_total(meta: dict[str, Any], settings: Settings | None = None) -> tuple[Decimal, str]:
    """Total de CONTROLO do dia: a parte `by_day` da PROPRIA resposta.

    E independente do detalhe (by_day_creative): se este vier truncado, o by_day
    continua a dizer o total real.
    """
    settings = settings or get_settings()
    (page,) = read_json(meta["raw_path"])["pages"]
    resp = EroResponse.model_validate(page)
    total = sum((d.cost_eur for d in resp.by_day if d.date.isoformat() == meta["date"]), Decimal("0"))
    return total, settings.erobella.currency
