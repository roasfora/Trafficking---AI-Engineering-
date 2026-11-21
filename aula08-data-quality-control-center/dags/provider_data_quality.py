"""DAG `provider_data_quality`: pipeline educacional com quality gates.

    ingestion        simulate_erobella | simulate_trafficjunky | simulate_voluum  ->  load_bronze
    quality_bronze   bronze_quality     (a Bronze foi recebida corretamente?)
    transform        normalize
    quality_silver   silver_quality     (os dados normalizados fazem sentido?)
    quality_gold     semantic_quality   (as metricas publicadas merecem confianca?)
    publish          notify -> publish

"Airflow orchestrates and reacts; it is not the Data Quality system."
Este ficheiro so decide a ORDEM e como reagir a uma falha. Os checks vivem em quality/runner.py e a sua
configuracao em config/quality_checks.yaml. As tasks chamam funcoes de quality/pipeline.py: as mesmas que o
fallback `python -m quality.demo_dag` usa sem Airflow.

Reagir a uma falha:
  * uma quality gate com FAIL falha a task (modo strict) -> as tasks seguintes ficam `upstream_failed`;
  * `notify` corre sempre (trigger_rule=all_done): regista a decisao e resume os alertas;
  * `publish` so corre se a gate semantica passou. FAIL nunca apaga Bronze nem Silver: so impede o publish.

Trigger manual com parametros:
  airflow dags trigger provider_data_quality --conf '{"scenario": "broken", "gate_mode": "strict"}'
"""

from __future__ import annotations

import re
from datetime import datetime

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, Param, TaskGroup

# Os modulos do projeto importam-se DENTRO das funcoes: o Airflow re-le este ficheiro com frequencia.


def _context(**ctx):
    """Constroi o RunContext a partir dos params do DAG. O run_id do Airflow identifica o run nas tabelas."""
    from quality.pipeline import RunContext

    params = ctx["params"]
    run_id = re.sub(r"[^A-Za-z0-9_-]", "-", ctx["run_id"])
    return RunContext.create(scenario=params["scenario"], gate_mode=params["gate_mode"], run_id=run_id)


def _simulate(provider: str, **ctx):
    from quality.pipeline import simulate_provider
    return simulate_provider(_context(**ctx), provider)


def _load_bronze(**ctx):
    from quality.pipeline import load_bronze
    return load_bronze(_context(**ctx))


def _gate(layer: str, **ctx):
    from quality.pipeline import quality_gate
    quality_gate(_context(**ctx), layer)     # levanta GateFailed em modo strict -> a task falha


def _normalize(**ctx):
    from quality.pipeline import normalize
    return normalize(_context(**ctx))


def _notify(**ctx):
    from quality.pipeline import notify
    return notify(_context(**ctx))


def _publish(**ctx):
    from quality.pipeline import publish
    return publish(_context(**ctx))          # levanta PublishBlocked se houver FAIL


with DAG(
    dag_id="provider_data_quality",
    description="Erobella + TrafficJunky + Voluum simulados -> Bronze -> Silver -> Gold, com quality gates",
    schedule=None,                            # so manual: e uma demo
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,                        # a Silver e reconstruida por provider a cada run: runs nao podem sobrepor-se
    default_args={"retries": 0},              # um FAIL de qualidade nao se resolve repetindo a task
    params={
        "scenario": Param("healthy", enum=["healthy", "broken"], description="Cenario simulado"),
        "gate_mode": Param("strict", enum=["strict", "observe"], description="strict: um FAIL para o pipeline"),
    },
    tags=["aula08", "data-quality"],
) as dag:

    with TaskGroup("ingestion") as ingestion:
        simulate = [
            PythonOperator(task_id=f"simulate_{p}", python_callable=_simulate, op_kwargs={"provider": p})
            for p in ("erobella", "trafficjunky", "voluum")
        ]
        load_bronze = PythonOperator(task_id="load_bronze", python_callable=_load_bronze)
        simulate >> load_bronze

    with TaskGroup("quality_bronze") as quality_bronze:
        bronze_quality = PythonOperator(task_id="bronze_quality", python_callable=_gate, op_kwargs={"layer": "bronze"})

    with TaskGroup("transform") as transform:
        normalize = PythonOperator(task_id="normalize", python_callable=_normalize)

    with TaskGroup("quality_silver") as quality_silver:
        silver_quality = PythonOperator(task_id="silver_quality", python_callable=_gate, op_kwargs={"layer": "silver"})

    with TaskGroup("quality_gold") as quality_gold:
        semantic_quality = PythonOperator(task_id="semantic_quality", python_callable=_gate, op_kwargs={"layer": "semantic"})

    with TaskGroup("publish") as publish_group:
        notify = PythonOperator(task_id="notify", python_callable=_notify, trigger_rule="all_done")
        publish = PythonOperator(task_id="publish", python_callable=_publish)   # all_success: bloqueado se a gate falhar
        notify >> publish

    ingestion >> quality_bronze >> transform >> quality_silver >> quality_gold >> publish_group
    semantic_quality >> publish      # publish depende tambem da gate: se ela falhar, publish fica upstream_failed
