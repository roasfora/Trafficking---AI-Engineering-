# Imagem oficial do Airflow + as bibliotecas do nosso ETL (pandas, psycopg).
# O codigo do projeto NAO e copiado: monta-se por volume (ver docker-compose.yml),
# por isso editar um DAG ou um modulo nao exige rebuild.
FROM apache/airflow:3.3.2-python3.12

COPY docker/requirements-airflow.txt /tmp/requirements-airflow.txt
RUN pip install --no-cache-dir -r /tmp/requirements-airflow.txt
