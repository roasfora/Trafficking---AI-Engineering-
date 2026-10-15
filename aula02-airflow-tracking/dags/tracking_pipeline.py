"""DAG `tracking_pipeline`: Synthetic Tracking API -> PostgreSQL.

    check_api >> extract >> validate >> transform >> load_dimensions
              >> load_facts >> quality_check

Este ficheiro so ORQUESTRA: decide a ordem, as janelas, os retries e os
timeouts. O trabalho real vive em pipeline/*.py, em Python puro e testavel
sem Airflow. Se este ficheiro tiver logica de negocio, esta mal.

Conceitos que o DAG demonstra (procura-os abaixo):
    DAG, tasks, dependencias (>>), scheduling, data interval, retries,
    retry_delay, execution_timeout, catchup, backfill, idempotencia.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG
from airflow.timetables.interval import CronDataIntervalTimetable

# NOTA: os modulos do pipeline importam-se DENTRO das funcoes. O Airflow
# re-le este ficheiro a cada poucos segundos para ver se mudou; imports pesados
# (pandas) ao nivel do modulo seriam pagos em cada leitura.


# --------------------------------------------------------------------------
# Callables das tasks. Sao finos de proposito.
#
# * `data_interval_start/end` sao injetados pelo Airflow: a janela [start, end)
#   que ESTA run tem de processar. Nao e "agora": e a fatia de tempo a que a
#   run diz respeito. E isto que torna backfills possiveis.
#   (Runs disparadas a mao nao tem data interval: ver pipeline/window.py.)
# * `ti` e a task instance. O que uma task RETORNA vai para o XCom; a seguinte
#   le-o com xcom_pull. So viajam metadados (caminhos, contagens), nunca dados.
# --------------------------------------------------------------------------

def _check_api():
    from pipeline import extract

    return extract.check_api()


def _extract(dag_run, data_interval_start=None, data_interval_end=None):
    from pipeline import extract
    from pipeline.window import resolve_window

    start, end = resolve_window(data_interval_start, data_interval_end, dag_run.run_after, dag_run.conf)
    return extract.run_extract(start, end)


def _validate(ti):
    from pipeline import validate

    return validate.run_validate(ti.xcom_pull(task_ids="extract"))


def _transform(ti):
    from pipeline import transform

    return transform.run_transform(ti.xcom_pull(task_ids="validate"))


def _load_dimensions(ti):
    from pipeline import load

    return load.run_load_dimensions(ti.xcom_pull(task_ids="transform"))


def _load_facts(ti):
    from pipeline import load

    return load.run_load_facts(ti.xcom_pull(task_ids="load_dimensions"))


def _quality_check(ti):
    from pipeline import quality

    return quality.run_quality_check(ti.xcom_pull(task_ids="load_facts"))


# --------------------------------------------------------------------------
# O DAG
# --------------------------------------------------------------------------

default_args = {
    # RETRIES: quantas vezes o Airflow volta a tentar uma task que falhou.
    "retries": 2,
    # RETRY_DELAY: espera entre tentativas. 30 s so para a aula; em producao
    # seriam minutos (idealmente com retry_exponential_backoff=True).
    "retry_delay": timedelta(seconds=30),
    # TIMEOUT: se uma tentativa demora mais do que isto, o Airflow mata-a e
    # conta como falha (que entao pode ser retentada). Sem timeout, uma API
    # pendurada deixava a task a correr para sempre.
    "execution_timeout": timedelta(minutes=2),
}

with DAG(
    dag_id="tracking_pipeline",
    description="Synthetic Tracking API -> Pydantic -> Pandas -> PostgreSQL",
    # SCHEDULING: uma run por dia, com DATA INTERVAL: a run de 2026-10-03
    # processa [2026-10-03 00:00, 2026-10-04 00:00) e so arranca quando esse dia
    # ACABA. (O "@daily" simples do Airflow 3 nao cria intervalos: por isso o
    # timetable explicito.)
    schedule=CronDataIntervalTimetable("@daily", timezone="UTC"),
    start_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
    # CATCHUP: False => ao ativar o DAG nao corre os dias em falta desde
    # start_date. Para recuperar o passado, faz-se um BACKFILL explicito (README).
    catchup=False,
    # Uma run de cada vez: duas a escrever as mesmas tabelas seria pedir problemas.
    max_active_runs=1,
    default_args=default_args,
    tags=["formacao", "aula02"],
    doc_md=__doc__,
) as dag:
    check_api = PythonOperator(
        task_id="check_api",
        python_callable=_check_api,
        # a verificacao de saude tem de ser rapida
        execution_timeout=timedelta(seconds=30),
    )
    extract = PythonOperator(task_id="extract", python_callable=_extract)
    # RETRIES NAO RESOLVEM ERROS DETERMINISTICOS. Um 500 ou um timeout podem
    # passar sozinhos; um campo renomeado ou um revenue negativo vao estar la
    # igual daqui a 30 segundos. Retentar so atrasa a falha. Por isso retries=0
    # em validate e quality_check: falham logo, e quem os le ve o erro mais cedo.
    validate = PythonOperator(task_id="validate", python_callable=_validate, retries=0)
    transform = PythonOperator(task_id="transform", python_callable=_transform)
    load_dimensions = PythonOperator(task_id="load_dimensions", python_callable=_load_dimensions)
    load_facts = PythonOperator(task_id="load_facts", python_callable=_load_facts)
    quality_check = PythonOperator(task_id="quality_check", python_callable=_quality_check, retries=0)

    # DEPENDENCIAS: uma task so arranca quando a anterior teve SUCESSO.
    # Se `validate` falha, `transform`, `load_*` e `quality_check` ficam
    # "upstream_failed" e nunca correm: dados maus nao chegam ao destino.
    (check_api >> extract >> validate >> transform >> load_dimensions >> load_facts >> quality_check)
