FROM python:3.12-slim

WORKDIR /app
COPY docker/requirements-mock.txt /tmp/requirements-mock.txt
RUN pip install --no-cache-dir -r /tmp/requirements-mock.txt

COPY mock_api/ /app/mock_api/
# a lista de campanhas (a mesma que a pipeline carrega em dim_campaign) e
# montada por volume - ver docker-compose.yml

EXPOSE 8000
CMD ["uvicorn", "mock_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
