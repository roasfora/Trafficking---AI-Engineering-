"""DAG `trafficjunky_daily`: TrafficJunky -> PostgreSQL.

    check_api >> extract >> validate_source >> transform
              >> validate_canonical >> load >> reconcile

Este ficheiro so ORQUESTRA: decide a ordem, o dia a processar, os retries e os
timeouts. O trabalho real vive em Python puro, testavel sem Airflow:

    providers/trafficjunky.py   o que e ESPECIFICO deste provider
    pipeline/validate.py        validacao do modelo canonico   (comum)
    pipeline/load.py            carga idempotente              (comum)
    pipeline/reconcile.py       reconciliacao                  (comum)

"O Airflow nao faz a transformacao. O Airflow orquestra a transformacao."

Ha DOIS DAGs com a mesma forma (este e o erobella_daily) e nao ha DAG factory:
de proposito. Primeiro ve-se o que se repete; so depois se abstrai.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, Asset
from airflow.timetables.interval import CronDataIntervalTimetable

# NOTA: os modulos do pipeline importam-se DENTRO das funcoes. O Airflow re-le este
# ficheiro a cada poucos segundos; imports pesados (pandas) ao nivel do modulo
# seriam pagos em cada leitura.


# --------------------------------------------------------------------------
# ASSETS: os DADOS que as tasks produzem ou atualizam.
#
#   Task  = processamento (o que a pipeline FAZ)
#   Asset = dado produzido/atualizado (o que a pipeline DEIXA)
#
# So extract, transform e load publicam Assets. check_api, validate_source,
# validate_canonical e reconcile produzem estado/decisoes, nao datasets.
#
# Um Asset e o dataset LOGICO inteiro (a pasta), nao um dia: a data processada
# viaja no `extra` de cada evento. `fact_campaign_daily` e partilhado pelos dois DAGs.
# --------------------------------------------------------------------------
RAW = Asset(name="raw_trafficjunky", uri="file:///opt/airflow/project/data/raw/trafficjunky/")
CANONICAL = Asset(name="canonical_trafficjunky", uri="file:///opt/airflow/project/data/staging/trafficjunky/")
FACT = Asset(name="fact_campaign_daily", uri="postgres://postgres:5432/analytics/public/fact_campaign_daily")


# --------------------------------------------------------------------------
# Callables das tasks. Sao finos de proposito.
#
# * O que uma task RETORNA vai para o XCom; a seguinte le-o com xcom_pull. So
#   viajam METADADOS (caminhos, contagens), nunca dados.
# * `data_interval_start` e a fatia de tempo a que a run diz respeito. Runs
#   disparadas a mao nao a tem: ver pipeline/window.py.
# --------------------------------------------------------------------------

def _check_api():
    from providers import trafficjunky

    return trafficjunky.check_api()


def _extract(dag_run, outlet_events, data_interval_start=None):
    from pipeline.window import resolve_day
    from providers import trafficjunky

    day = resolve_day(data_interval_start, dag_run.run_after, dag_run.conf)
    meta = trafficjunky.extract(day)
    outlet_events[RAW].extra = {"provider": meta["provider"], "date": meta["date"], "raw_path": meta["raw_path"]}
    return meta


def _validate_source(ti):
    from providers import trafficjunky

    return trafficjunky.validate_source(ti.xcom_pull(task_ids="extract"))


def _transform(ti, outlet_events):
    from providers import trafficjunky

    meta = trafficjunky.transform(ti.xcom_pull(task_ids="validate_source"))
    outlet_events[CANONICAL].extra = {
        "provider": meta["provider"], "date": meta["date"],
        "staging_path": meta["staging_path"], "row_count": meta["counts"]["saved"],
    }
    return meta


def _validate_canonical(ti):
    from pipeline import validate

    return validate.validate_canonical(ti.xcom_pull(task_ids="transform"))


def _load(ti, outlet_events):
    from pipeline import load

    meta = load.run_load(ti.xcom_pull(task_ids="validate_canonical"))
    outlet_events[FACT].extra = {
        "provider": meta["provider"], "date": meta["date"],
        "inserted": meta["loaded"]["inserted"], "updated": meta["loaded"]["updated"],
    }
    return meta


def _reconcile(ti):
    from pipeline import reconcile
    from providers import trafficjunky

    meta = ti.xcom_pull(task_ids="load")
    api_total, api_currency = trafficjunky.fetch_api_total(meta)  # total INDEPENDENTE do detalhe
    return reconcile.run_reconcile(meta, api_total, api_currency)


# --------------------------------------------------------------------------
# O DAG
# --------------------------------------------------------------------------

default_args = {
    # RETRIES: quantas vezes o Airflow volta a tentar uma task que falhou.
    "retries": 2,
    # RETRY_DELAY: espera entre tentativas. 30 s so para a aula; em producao seriam
    # minutos (idealmente com retry_exponential_backoff=True).
    "retry_delay": timedelta(seconds=30),
    # TIMEOUT: se uma tentativa demora mais do que isto, o Airflow mata-a e conta
    # como falha. Sem timeout, uma API pendurada deixava a task a correr para sempre.
    "execution_timeout": timedelta(minutes=2),
}

with DAG(
    dag_id="trafficjunky_daily",
    description="TrafficJunky -> source contract -> canonical model -> PostgreSQL -> reconcile",
    # SCHEDULING: uma run por dia, com DATA INTERVAL: a run do dia 20 processa o dia
    # 20 e so arranca quando esse dia ACABA. (O "@daily" simples do Airflow 3 nao cria
    # intervalos: por isso o timetable explicito.)
    schedule=CronDataIntervalTimetable("@daily", timezone="UTC"),
    start_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
    # CATCHUP: False => ao ativar o DAG nao corre os dias em falta. Para reprocessar o
    # passado: backfill explicito, ou --conf '{"date": "YYYY-MM-DD"}'.
    catchup=False,
    # Uma run de cada vez: duas a escrever as mesmas linhas seria pedir problemas.
    max_active_runs=1,
    default_args=default_args,
    tags=["formacao", "aula03", "trafficjunky"],
    doc_md=__doc__,
) as dag:
    check_api = PythonOperator(
        task_id="check_api", python_callable=_check_api,
        execution_timeout=timedelta(seconds=30),  # a verificacao de saude tem de ser rapida
    )
    extract = PythonOperator(task_id="extract", python_callable=_extract, outlets=[RAW])

    # RETRIES NAO RESOLVEM ERROS DETERMINISTICOS. Um 500 ou um timeout podem passar
    # sozinhos; um campo renomeado, um valor impossivel ou um total que nao bate
    # estarao la igual daqui a 30 segundos. Retentar so atrasa a falha: retries=0.
    validate_source = PythonOperator(task_id="validate_source", python_callable=_validate_source, retries=0)
    transform = PythonOperator(task_id="transform", python_callable=_transform, outlets=[CANONICAL])
    validate_canonical = PythonOperator(task_id="validate_canonical", python_callable=_validate_canonical, retries=0)
    load = PythonOperator(task_id="load", python_callable=_load, outlets=[FACT])
    reconcile = PythonOperator(task_id="reconcile", python_callable=_reconcile, retries=0)

    # DEPENDENCIAS: uma task so arranca quando a anterior teve SUCESSO. Se
    # `validate_source` falha, o resto fica "upstream_failed" e nunca corre.
    (check_api >> extract >> validate_source >> transform >> validate_canonical >> load >> reconcile)
