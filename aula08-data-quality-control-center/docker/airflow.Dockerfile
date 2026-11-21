# Imagem oficial do Airflow (a mesma da Aula 03) + as bibliotecas da PoC.
# O codigo NAO e copiado: monta-se por volume (docker-compose.yml).
FROM apache/airflow:3.3.2-python3.12
RUN pip install --no-cache-dir "psycopg[binary]>=3.2,<4.0" "PyYAML>=6.0"
