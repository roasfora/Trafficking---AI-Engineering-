"""Gera sql/04_seed_raw.sql: dados RAW sinteticos, deterministicos (seed fixo).

    python scripts/generate_seed_raw.py

14 dias (2026-10-26 .. 2026-11-08), 3 providers. Padroes plantados de proposito:
  - CPC diferente por provider (Voluum > TrafficJunky > Erobella)
  - TJ-Banner-DE: queda do CR a partir de 2026-11-02
  - TJ-Native-FR: CTR bom (1.4%) mas CR mau (0.4%)
  - TJ-Pop-ES: pico de custo em 2026-11-05 (outlier)
  - EB-PUSH-D: colapso de cliques em 2026-11-04 (outlier)
  - VL-HEALTH-FR: melhor ROAS; VL-VPN-UK: pior ROAS
  - Erobella e TrafficJunky nao reportam receita; Erobella nao reporta conversoes
"""

from __future__ import annotations

import random
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

rng = random.Random(7)
DAYS = [date(2026, 10, 26) + timedelta(days=i) for i in range(14)]
NS = uuid.UUID("12345678-1234-5678-1234-567812345678")


def jitter(pct: float = 0.07) -> float:
    return 1 + rng.uniform(-pct, pct)


def sql_val(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(round(v, 4)) if isinstance(v, float) else str(v)
    return "'" + str(v).replace("'", "''") + "'"


def insert(table: str, columns: list[str], rows: list[tuple]) -> str:
    values = ",\n".join("  (" + ", ".join(sql_val(v) for v in row) + ")" for row in rows)
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES\n{values};\n"


out: list[str] = ["-- GERADO por scripts/generate_seed_raw.py (seed fixo). Nao editar a mao.\n"]

# ------------------------------------------------------------------ Erobella
EROBELLA = [  # label, partner, impressions/dia, ctr %, ecpm EUR
    ("EB-NATIVE-A", "partner_alpha", 120_000, 0.90, 1.10),
    ("EB-NATIVE-B", "partner_alpha", 80_000, 0.70, 0.95),
    ("EB-BANNER-C", "partner_beta", 150_000, 0.35, 0.60),
    ("EB-PUSH-D", "partner_beta", 40_000, 2.40, 3.10),
]
eb_creative, eb_daily = [], []
for d in DAYS:
    tot_i = tot_c = 0
    tot_cost = 0.0
    for label, partner, imps, ctr, ecpm in EROBELLA:
        i = round(imps * jitter())
        c = round(i * ctr / 100 * jitter())
        if label == "EB-PUSH-D" and d == date(2026, 11, 4):
            c = 9  # outlier: colapso de cliques
        cost = round(i / 1000 * ecpm, 4)
        eb_creative.append((d.isoformat(), label, partner, i, c, cost, round(c / i * 100, 4), ecpm))
        tot_i, tot_c, tot_cost = tot_i + i, tot_c + c, tot_cost + cost
    eb_daily.append((d.isoformat(), tot_i, tot_c, round(tot_c / tot_i * 100, 4), round(tot_cost, 4),
                     round(tot_cost / tot_i * 1000, 4), f"{(d + timedelta(days=1)).isoformat()} 06:00:00+00"))
out.append(insert("raw.erobella_creative_stats",
                  ["day", "label", "partner", "impressions", "clicks", "cost_eur", "ctr_pct", "ecpm_eur"], eb_creative))
out.append(insert("raw.erobella_daily_stats",
                  ["day", "impressions", "clicks", "ctr_pct", "cost_eur", "ecpm_eur", "updated_at"], eb_daily))
out.append(insert("raw.erobella_rates", ["partner", "country", "model", "price_eur", "valid_from", "valid_to"], [
    ("partner_alpha", "Portugal", "cpm", 1.10, "2026-01-01", None),
    ("partner_alpha", "Germany", "revshare", 50.0, "2026-01-01", None),     # 50.0 = 50 %, NAO 50 EUR
    ("partner_beta", "Spain", "cpm", 0.60, "2026-01-01", "2026-12-31"),
    ("partner_beta", "France", "revshare", 35.0, "2026-03-01", None),
    ("partner_beta", "Italy", "cpm", 2.25, "2026-06-01", "2026-10-31"),
]))

# -------------------------------------------------------------- TrafficJunky
TJ = [  # id, nome, tipo, impressions/dia, ctr %, ecpm USD, cr % (de cliques)
    (5001, "TJ-Video-Preroll-PT", "video", 200_000, 0.55, 3.80, 1.6),
    (5002, "TJ-Banner-DE", "banner", 260_000, 0.30, 1.20, 2.4),
    (5003, "TJ-Native-FR", "native", 110_000, 1.40, 2.60, 0.4),
    (5004, "TJ-Pop-ES", "popunder", 90_000, 0.90, 1.00, 1.0),
]
tj_rows = []
for d in DAYS:
    for cid, name, ctype, imps, ctr, ecpm, cr in TJ:
        i = round(imps * jitter())
        c = round(i * ctr / 100 * jitter())
        cr_today = 1.1 if (cid == 5002 and d >= date(2026, 11, 2)) else cr  # queda do CR
        conv = round(c * cr_today / 100 * jitter(0.12))
        cost = round(i / 1000 * ecpm * (3.5 if (cid == 5004 and d == date(2026, 11, 5)) else 1), 4)  # outlier
        tj_rows.append((d.isoformat(), cid, name, ctype, i, c, conv, round(c / i * 100, 4),
                        round(cost / i * 1000, 4), round(cost / c, 4), cost))
out.append(insert("raw.trafficjunky_campaign_stats",
                  ["day", "campaign_id", "campaign_name", "campaign_type", "impressions", "clicks",
                   "conversions", "ctr", "ecpm", "ecpc", "cost"], tj_rows))

spot_rows = []
for d in DAYS:
    for spot_id in (9101, 9102, 9103, 9104, 9105):
        i = round(rng.uniform(20_000, 90_000))
        c = round(i * rng.uniform(0.002, 0.012))
        conv = round(c * rng.uniform(0.005, 0.03))
        rev = round(conv * rng.uniform(8, 30), 4)
        spot_rows.append((d.isoformat(), spot_id, i, c, conv, rev, round(rev / i * 1000, 4),
                          round(rev / c, 4), round(c / i * 100, 4)))
out.append(insert("raw.trafficjunky_spot_stats",
                  ["day", "spot_id", "impressions", "clicks", "conversions", "revenue", "ecpm", "ecpc", "ctr"], spot_rows))

# -------------------------------------------------------------------- Voluum
VL = [  # nome, source, offer, pais, cliques/dia, visits/clicks, cpc EUR, cr % (de cliques), payout EUR, ctr impressoes %
    ("VL-SWEEPS-US", "PopSource", "Sweeps US offer", "US", 1800, 1.08, 0.65, 2.2, 38, 1.5),
    ("VL-DATING-DE", "NativeNet", "Dating DE offer", "DE", 900, 1.10, 0.70, 4.0, 22, 1.2),
    ("VL-GAMES-BR", "PushHub", "Mobile Games BR offer", "BR", 2500, 1.02, 0.10, 1.0, 12, 2.0),
    ("VL-VPN-UK", "PopSource", "VPN UK offer", "GB", 600, 1.15, 0.85, 1.2, 25, 0.9),
    ("VL-HEALTH-FR", "NativeNet", "Health FR offer", "FR", 700, 1.12, 0.55, 3.0, 40, 1.1),
]
uid = lambda kind, name: str(uuid.uuid5(NS, f"{kind}:{name}"))  # noqa: E731
vl_rows, vl_meta = [], {}
for d in DAYS:
    for name, src, offer, cc, clicks, v_ratio, cpc, cr, payout, ctr_imp in VL:
        c = round(clicks * jitter())
        visits = round(c * v_ratio * jitter(0.02))
        imps = round(c / (ctr_imp / 100))
        conv = round(c * cr / 100 * jitter(0.12))
        cost = round(c * cpc * jitter(0.04), 4)
        rev = round(conv * payout, 4)
        vl_rows.append((d.isoformat(), uid("campaign", name), name, uid("source", src), src, uid("offer", offer),
                        offer, cc, visits, c, conv, imps, rev, cost, round(rev - cost, 4),
                        round(c / visits * 100, 4), round(conv / visits * 100, 4),
                        round(cost / conv, 4) if conv else None, round(cost / c, 4), round(cost / imps * 1000, 4)))
        vl_meta[(d, name)] = (src, offer, cc, conv, cost, c, payout)
out.append(insert("raw.voluum_report",
                  ["day", "campaign_id", "campaign_name", "traffic_source_id", "traffic_source_name", "offer_id",
                   "offer_name", "country_code", "visits", "clicks", "conversions", "impressions", "revenue", "cost",
                   "profit", "ctr", "cr", "cpa", "cpc", "ecpm"], vl_rows))

# Detalhe de conversoes: so 2026-11-08, coerente com o report desse dia.
LAST = DAYS[-1]
conv_rows, n = [], 0
for name, *_ in VL:
    src, offer, cc, conv, cost, clicks, payout = vl_meta[(LAST, name)]
    for _ in range(conv):
        n += 1
        postback = datetime(LAST.year, LAST.month, LAST.day, rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59))
        # visita ate 3 dias antes do postback: conversoes chegam depois (ver provider_notes.md)
        visit = postback - timedelta(hours=rng.choice([0, 0, 1, 2, 5, 20, 30, 50]), minutes=rng.randint(0, 59))
        unit_cost = round(cost / clicks, 4)
        conv_rows.append((f"cv-{LAST:%Y%m%d}-{n:04d}", uid("campaign", name), name, src, offer, cc,
                          visit.isoformat(sep=" "), postback.isoformat(sep=" "), float(payout), unit_cost,
                          round(payout - unit_cost, 4), rng.choice(["Sale", "Lead"])))
out.append(insert("raw.voluum_conversions",
                  ["conversion_id", "campaign_id", "campaign_name", "traffic_source_name", "offer_name",
                   "country_code", "visit_timestamp", "postback_timestamp", "revenue", "cost", "profit",
                   "conversion_type"], conv_rows))

path = Path(__file__).resolve().parent.parent / "sql" / "04_seed_raw.sql"
path.write_text("\n".join(out), encoding="utf-8")
print(f"{path.name}: {len(eb_creative)} erobella, {len(tj_rows)} trafficjunky, {len(vl_rows)} voluum, "
      f"{len(conv_rows)} conversions")
