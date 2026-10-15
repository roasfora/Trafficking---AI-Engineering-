# Observability roadmap

> **Estado: apenas documentação.** Nada do que está aqui está instalado.
> Esta versão da formação ensina conceitos de orquestração e de dados; a
> observabilidade é a evolução natural, e fica como roteiro para a próxima fase.

## Três tipos de observabilidade

Uma pipeline pode falhar em três sítios diferentes, e cada um precisa do seu tipo
de visibilidade. Misturá-los é a causa mais comum de "o dashboard está verde mas
os números estão errados".

| | Pipeline observability | Source observability | Data observability |
|---|---|---|---|
| Pergunta | O **job** correu? | A **fonte** está bem? | Os **dados** estão bem? |
| Observa | o Airflow | a API (o producer) | o conteúdo das tabelas |
| Sinais | sucesso/falha de DAG e tasks, retries, duração, atraso do scheduler | disponibilidade, latência, códigos HTTP | volume, freshness, duplicados, falhas de validação, schema |
| Falha típica | task em `failed`, DAG sem correr | API em 500, lenta, 429 | tabela vazia, dados de ontem, `revenue` com unidade errada |
| Pode estar tudo verde quando... | os dados estão errados (o job correu bem a carregar lixo) | a API responde 200 com campos mudados | o job falhou e nunca chegou a escrever |

A lição: **o job ter corrido com sucesso não diz nada sobre os dados.** É por
isso que o `quality_check` existe dentro do DAG, e é por isso que a
observabilidade de dados é uma camada própria.

### Onde cada cenário da formação aparece

| Cenário | Quem o vê primeiro |
|---|---|
| 2. API devolve 500 | source (probe falha) e pipeline (`check_api` em retry) |
| 3. API lenta | source (latência sobe); **o `/health` continua verde**, só um probe a um endpoint de dados o vê |
| 4. API devolve 429 | source (status 429) e pipeline (retries) |
| 5. `schema_drift` | pipeline (`validate` falhou). A source observability **não** vê nada: a API responde 200 em tempo normal |
| 6. `revenue` negativo | pipeline (`validate` falhou). Idem |
| 7. evento repetido | data (contagem de duplicados e de `updated` vs `inserted`) |
| (reconciliação a falhar) | data: dois sistemas discordam sobre o mesmo número; nenhuma monitorização de job ou de API o vê |

Dois dos cenários passam despercebidos a qualquer monitorização de
disponibilidade. Esse é o argumento para ter os três níveis.

## Fase 1: observar a API (source)

```
 API ──► Blackbox Exporter ──► Prometheus ──► Grafana
 (/health, /conversions)  (sonda HTTP)    (guarda séries)   (painéis e alertas)
```

O **Blackbox Exporter** testa a API *por fora*, como um cliente: faz um pedido
HTTP e devolve métricas sobre a resposta. A API não precisa de saber que está
a ser observada.

Métricas relevantes: `probe_success` (disponibilidade), `probe_duration_seconds`
(latência), `probe_http_status_code` (200, 429, 500...).

Esboço da configuração (ilustrativo):

```yaml
# prometheus.yml
scrape_configs:
  - job_name: tracking-api
    metrics_path: /probe
    params: { module: [http_2xx] }
    static_configs:
      - targets:
          - http://api:8000/health
          - http://api:8000/conversions?limit=1     # um endpoint de DADOS, não só o /health
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: blackbox-exporter:9115
```

Dois pormenores que vale a pena ensinar:
* Sondar só `/health` não deteta o modo `slow` (o `/health` fica rápido). Sonda-se
  também um endpoint de dados.
* O *observer effect*: uma sonda é um pedido como outro qualquer. No modo
  `rate_limit` consome a quota de 429. É por isso que o healthcheck do Docker
  desta formação aponta para `/admin/mode` e não para `/health`.

**O que se quer ver:** disponibilidade (%), latência (p50/p95), distribuição de
status HTTP.

## Fase 2: observar o Airflow (pipeline)

```
 Airflow ──► (métricas) ──► Prometheus ──► Grafana
```

O Airflow emite métricas (StatsD ou OpenTelemetry, conforme a versão e a
configuração); o caminho habitual para o Prometheus é através de um exporter
intermédio (por exemplo, `statsd-exporter`). Os detalhes dependem da versão do
Airflow, por isso verifica a documentação oficial na altura de implementar.

**O que se quer ver:** DAG runs com sucesso/falha, número de retries por task,
duração de cada task (e a sua tendência), tasks em `upstream_failed`, atraso
entre a hora agendada e o arranque (scheduler lag).

## Fase 3: observar os dados

```
 PostgreSQL (analytics) ──► Grafana (datasource PostgreSQL)
          ▲
 tabela de métricas de run, escrita pela pipeline
```

As métricas de dados não vêm do Airflow nem da API: vêm dos próprios dados. Duas
opções:

1. **Consultar as tabelas** que já existem (o Grafana lê PostgreSQL diretamente):
   `count(*)` por dia, `max(event_ts)`, duplicados.
2. **Registar métricas por run** numa tabela dedicada (por exemplo,
   `pipeline_run_log`: `run_id`, janela, linhas extraídas/validadas/carregadas,
   inseridas vs atualizadas, resultados dos checks, duração). A pipeline já
   produz estes números (estão nos XComs e nos logs); falta guardá-los.

| Métrica | Origem | Alerta típico |
|---|---|---|
| Record count por dia | `count(*)` nas facts | cai > 50 % face à mediana dos últimos 7 dias |
| Freshness | `now() - max(event_ts)` | > 6 h (o mesmo limiar do `quality_check`) |
| Duplicados | `quality_check` | > 0 |
| Reconciliação (eventos vs `daily_control`) | `v_reconciliation_daily` | qualquer linha não manual fora da tolerância |
| Falhas de validação | task `validate` (nº de registos inválidos) | > 0 |
| Inserted vs updated | `load_facts` | muitos `updated` num dia que devia ser novo = reprocessamento |
| Linhas órfãs | `quality_check` | > 0 |

## Alertas: o princípio

Alertar sobre **sintomas** que alguém tem de resolver, não sobre tudo o que se
consegue medir. Uma task que falhou e recuperou ao segundo retry não acorda
ninguém; um DAG que falhou *depois* de todos os retries, ou dados com mais de
6 horas, sim.

## O que mudaria no repositório

Três serviços novos no `docker-compose.yml` (`blackbox-exporter`, `prometheus`,
`grafana`), uma pasta `observability/` com os ficheiros de configuração e,
mais tarde, um `statsd-exporter`. O código da pipeline fica praticamente igual;
o que muda é que passa a ser *visível*.
