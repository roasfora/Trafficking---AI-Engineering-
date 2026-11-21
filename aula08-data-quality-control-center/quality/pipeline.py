"""O pipeline em etapas (stages) + o grafo de tasks.

As MESMAS funcoes sao usadas por tres executores:
    * dags/provider_data_quality.py   (Airflow real, opcional)
    * quality.demo_dag / demo_run     (executor minimo, sem Airflow)
    * dashboard (botoes "Run healthy/broken scenario")

Regra: o orquestrador so decide a ORDEM e reage a falhas. Os checks vivem em quality/runner.py.

    simulate_* -> load_bronze -> bronze_quality -> normalize -> silver_quality -> semantic_quality -> notify -> publish
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from psycopg.types.json import Jsonb

from config import Settings, get_settings
from db import connect
from ingestion.bronze_loader import load_bronze as _load_bronze, load_control, read_payload, write_payload
from ingestion.normalize import normalize_provider
from quality.models import GateResult
from quality.notifier import get_notifier
from quality.runner import run_quality_gate
from simulators import erobella_api, trafficjunky_api, voluum_api
from simulators.scenarios import Scenario, control_rows, load_scenario, simulated_now

SIMULATORS = {"erobella": erobella_api, "trafficjunky": trafficjunky_api, "voluum": voluum_api}
LAYER_LABEL = {"bronze": "BRONZE", "silver": "SILVER", "semantic": "SEMANTIC"}


class GateFailed(Exception):
    """Uma quality gate deu FAIL em modo strict: o pipeline para aqui."""


class PublishBlocked(Exception):
    """Ha FAIL nos checks deste run: nada e publicado para os consumidores."""


@dataclass
class RunContext:
    run_id: str
    scenario: Scenario
    gate_mode: str
    settings: Settings
    notifier: object = None
    log: Callable[[str], None] = print
    gates: dict = field(default_factory=dict)

    @classmethod
    def create(cls, scenario: str | None = None, providers: tuple | None = None, gate_mode: str | None = None,
               run_id: str | None = None, notifier=None, log: Callable[[str], None] = print) -> "RunContext":
        settings = get_settings()
        name = scenario or settings.scenario
        chosen = tuple(providers) if providers else settings.providers
        run_id = run_id or f"{name}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}"
        return cls(run_id=run_id, scenario=load_scenario(name, chosen), gate_mode=gate_mode or settings.gate_mode,
                   settings=settings, notifier=notifier, log=log)

    @property
    def payload_dir(self) -> Path:
        return self.settings.payload_dir / self.run_id


# ------------------------------------------------------------------ pipeline_runs
def ensure_run(rc: RunContext) -> None:
    with connect(rc.settings) as conn:
        conn.execute(
            """INSERT INTO data_quality.pipeline_runs (run_id, scenario, gate_mode, started_at, status)
               VALUES (%s, %s, %s, now(), 'RUNNING') ON CONFLICT (run_id) DO NOTHING""",
            (rc.run_id, rc.scenario.name, rc.gate_mode))


def _update_run(rc: RunContext, **fields) -> None:
    sets = ", ".join(f"{k} = %s" for k in fields)
    with connect(rc.settings) as conn:
        conn.execute(f"UPDATE data_quality.pipeline_runs SET {sets} WHERE run_id = %s", (*fields.values(), rc.run_id))


def _record_gate(rc: RunContext, layer: str, status: str) -> None:
    rc.gates[layer] = status
    with connect(rc.settings) as conn:
        conn.execute("UPDATE data_quality.pipeline_runs SET gates = gates || %s WHERE run_id = %s",
                     (Jsonb({layer: status}), rc.run_id))


# ------------------------------------------------------------------ stages
def simulate_provider(rc: RunContext, provider: str) -> str:
    """Chama a API simulada e aterra a resposta em ficheiro (so metadados viajam entre tasks)."""
    ensure_run(rc)
    if provider not in rc.scenario.providers:
        return f"{provider}: not selected, nothing to do"
    payload = SIMULATORS[provider].fetch(rc.settings.as_of_date, rc.settings.window_days, rc.scenario,
                                         simulated_now(rc.settings.as_of_date))
    path = rc.payload_dir / f"{provider}.json"
    write_payload(path, payload)
    return f"{provider}: {len(payload['rows'])} rows landed in {path.name}"


def load_bronze(rc: RunContext) -> str:
    """Bronze preserves what the provider said. Nada e convertido nem corrigido."""
    ensure_run(rc)
    parts = []
    with connect(rc.settings) as conn:
        for provider in rc.scenario.providers:
            counts = _load_bronze(conn, provider, read_payload(rc.payload_dir / f"{provider}.json"),
                                  rc.run_id, rc.settings.as_of_date, rc.scenario.name)
            parts.append(f"{provider}={counts['rows']}")
        load_control(conn, control_rows(rc.settings.as_of_date, rc.settings.window_days, rc.scenario))
    return "bronze rows: " + ", ".join(parts)


def quality_gate(rc: RunContext, layer: str) -> GateResult:
    """Corre os checks da camada, persiste, notifica. Em modo strict, um FAIL para o pipeline."""
    ensure_run(rc)
    with connect(rc.settings) as conn:
        notifier = rc.notifier or get_notifier(conn)
        gate = run_quality_gate(layer, rc.run_id, conn=conn, providers=rc.scenario.providers, notifier=notifier)
    _record_gate(rc, layer, gate.status)
    rc.log(f"{LAYER_LABEL[layer]} GATE: {gate.status}")
    if gate.status == "FAIL" and rc.gate_mode == "strict":
        raise GateFailed(f"{LAYER_LABEL[layer]} gate failed ({gate.counts['FAIL']} FAIL): pipeline stopped")
    if gate.status == "FAIL":
        rc.log(f"  (observe mode: {LAYER_LABEL[layer]} FAIL would stop a strict pipeline; continuing to expose every issue)")
    return gate


def normalize(rc: RunContext) -> str:
    """Silver interprets: nomes canonicos, EUR via exchange_rate, grain date+provider+campaign_id."""
    ensure_run(rc)
    parts = []
    with connect(rc.settings) as conn:
        for provider in rc.scenario.providers:
            parts.append(f"{provider}={normalize_provider(conn, provider, rc.run_id)}")
    return "silver rows: " + ", ".join(parts)


def _count_fails(rc: RunContext) -> int:
    with connect(rc.settings) as conn:
        return conn.execute("SELECT count(*) AS n FROM data_quality.check_results WHERE run_id = %s AND status = 'FAIL'",
                            (rc.run_id,)).fetchone()["n"]


def notify(rc: RunContext) -> str:
    """Decide se o publish e permitido (a partir dos resultados PERSISTIDOS) e resume os alertas."""
    ensure_run(rc)
    fails = _count_fails(rc)
    with connect(rc.settings) as conn:
        counts = {r["status"]: r["n"] for r in conn.execute(
            "SELECT status, count(*) AS n FROM data_quality.check_results WHERE run_id = %s GROUP BY status", (rc.run_id,))}
        alerts = conn.execute("SELECT count(*) AS n FROM data_quality.alerts WHERE run_id = %s", (rc.run_id,)).fetchone()["n"]
    allowed = fails == 0
    _update_run(rc, publish_allowed=allowed, **({} if allowed else {"status": "BLOCKED", "finished_at": datetime.now(timezone.utc)}))
    msg = (f"checks: {counts.get('PASS', 0)} PASS, {counts.get('WARN', 0)} WARN, {counts.get('FAIL', 0)} FAIL; "
           f"{alerts} alert(s) sent")
    rc.log(f"NOTIFY: {msg}")
    return msg


def publish(rc: RunContext) -> str:
    """Consumer layer: so recebe dados se nao houver FAIL. Bronze e Silver nunca sao apagadas."""
    ensure_run(rc)
    if _count_fails(rc):
        _update_run(rc, publish_allowed=False, status="BLOCKED", finished_at=datetime.now(timezone.utc))
        rc.log("PUBLISH: BLOCKED")
        raise PublishBlocked("publish blocked: this run has FAIL checks")
    with connect(rc.settings) as conn, conn.cursor() as cur:
        for provider in rc.scenario.providers:
            cur.execute("DELETE FROM analytics.published_campaign_performance_daily WHERE provider = %s", (provider,))
            cur.execute("""INSERT INTO analytics.published_campaign_performance_daily
                              (date, provider, campaign_id, campaign_name, traffic_source, country, impressions, clicks,
                               conversions, cost, revenue, currency, source_currency, fx_rate, run_id, loaded_at)
                           SELECT date, provider, campaign_id, campaign_name, traffic_source, country, impressions, clicks,
                                  conversions, cost, revenue, currency, source_currency, fx_rate, run_id, loaded_at
                           FROM analytics.campaign_performance_daily WHERE provider = %s AND run_id = %s""",
                        (provider, rc.run_id))
    _update_run(rc, publish_allowed=True, status="PUBLISHED", finished_at=datetime.now(timezone.utc))
    rc.log("PUBLISH: ALLOWED")
    return "published"


# ------------------------------------------------------------------ grafo de tasks
@dataclass
class TaskSpec:
    id: str
    group: str
    fn: Callable[[RunContext], object]
    upstream: tuple = ()
    trigger_rule: str = "all_success"   # all_success | all_done


def build_tasks() -> list[TaskSpec]:
    sims = [TaskSpec(f"simulate_{p}", "ingestion", (lambda rc, p=p: simulate_provider(rc, p))) for p in SIMULATORS]
    return [
        *sims,
        TaskSpec("load_bronze", "ingestion", load_bronze, tuple(t.id for t in sims)),
        TaskSpec("bronze_quality", "quality_bronze", lambda rc: quality_gate(rc, "bronze"), ("load_bronze",)),
        TaskSpec("normalize", "transform", normalize, ("bronze_quality",)),
        TaskSpec("silver_quality", "quality_silver", lambda rc: quality_gate(rc, "silver"), ("normalize",)),
        TaskSpec("semantic_quality", "quality_gold", lambda rc: quality_gate(rc, "semantic"), ("silver_quality",)),
        TaskSpec("notify", "publish", notify, ("semantic_quality",), trigger_rule="all_done"),
        TaskSpec("publish", "publish", publish, ("semantic_quality", "notify")),
    ]


@dataclass
class PipelineResult:
    run_id: str
    states: dict
    errors: dict
    gates: dict
    publish_allowed: bool
    published: bool


def run_graph(rc: RunContext, tasks: list[TaskSpec] | None = None) -> PipelineResult:
    """Executor minimo, com a semantica de estados do Airflow: success | failed | upstream_failed."""
    tasks = tasks or build_tasks()
    states: dict[str, str] = {}
    errors: dict[str, str] = {}
    for t in tasks:
        up = [states[u] for u in t.upstream]
        if t.trigger_rule == "all_success" and any(s != "success" for s in up):
            states[t.id] = "upstream_failed"
            continue
        try:
            t.fn(rc)
            states[t.id] = "success"
        except Exception as exc:
            states[t.id] = "failed"
            errors[t.id] = f"{type(exc).__name__}: {exc}"
    with connect(rc.settings) as conn:
        row = conn.execute("SELECT publish_allowed, status FROM data_quality.pipeline_runs WHERE run_id = %s",
                           (rc.run_id,)).fetchone()
    return PipelineResult(run_id=rc.run_id, states=states, errors=errors, gates=dict(rc.gates),
                          publish_allowed=bool(row and row["publish_allowed"]), published=bool(row and row["status"] == "PUBLISHED"))


def run_pipeline(scenario: str | None = None, providers: tuple | None = None, gate_mode: str | None = None,
                 notifier=None, log: Callable[[str], None] = print) -> PipelineResult:
    rc = RunContext.create(scenario=scenario, providers=providers, gate_mode=gate_mode, notifier=notifier, log=log)
    ensure_run(rc)
    return run_graph(rc)
