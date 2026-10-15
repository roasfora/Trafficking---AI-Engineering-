# Tracking Pipeline · Apache Airflow

> Uma pipeline de dados pequena, do princípio ao fim, para ensinar **conceitos**,
> não ferramentas.
> **Python · Pandas · FastAPI · Pydantic · Apache Airflow · PostgreSQL · Docker Compose**

Projeto do Módulo 02 do AI Engineering Course. O modelo de dados segue a estrutura
real de uma plataforma de tracking ([data-structure-reference.md](data-structure-reference.md)).
O foco é o **Apache Airflow** e
tudo o que o rodeia: modelação dimensional, data contracts, ETL, retries,
idempotência e os primeiros passos de observabilidade.

> Todos os dados são **100 % sintéticos** (gerados por uma API fictícia, com seed).
> Nenhum dado é real.

**Deliberadamente fora de âmbito:** dbt, Spark, arquitetura medallion
(bronze/silver/gold), lakehouse, Great Expectations, Kafka, Celery, Kubernetes e
a stack Prometheus/Grafana (que fica só no [roadmap](docs/observability-roadmap.md)).

---

## Índice

1. [O problema](#1-o-problema)
2. [Arquitetura](#2-arquitetura)
3. [Tracking domain](#3-tracking-domain)
4. [Data model](#4-data-model)
5. [Grain](#5-grain)
6. [Facts vs dimensions](#6-facts-vs-dimensions)
7. [A API](#7-a-api)
8. [Data contract com Pydantic](#8-data-contract-com-pydantic)
9. [ETL](#9-etl)
10. [Airflow](#10-airflow)
11. [Retries e failures](#11-retries-e-failures)
12. [Idempotency](#12-idempotency)
13. [Data quality](#13-data-quality)
14. [Observability](#14-observability)
15. [Exercícios](#15-exercícios)

Anexos: [A. Arrancar, URLs e reset](#anexo-a--arrancar-urls-e-reset) ·
[B. Simplificações pedagógicas](#anexo-b--simplificações-pedagógicas) ·
[C. Troubleshooting](#anexo-c--troubleshooting)

---

## 1. O problema

Uma plataforma de performance marketing regista **clicks** e **conversões**. Quem
gere campanhas quer saber coisas simples: quanto gastámos, quanto ganhámos, qual
a campanha que dá lucro. Os dados nascem noutro sistema (a plataforma de tracking)
e têm de chegar, **todos os dias, de forma fiável**, a uma base de dados onde se
possam analisar.

"Fiável" é a palavra difícil. Na vida real:

* a API cai, fica lenta, limita-nos o ritmo;
* o producer muda um campo sem avisar;
* chegam valores impossíveis (receita negativa);
* a pipeline corre duas vezes sobre o mesmo dia e duplica tudo;
* dois sistemas discordam sobre o mesmo número.

Esta formação constrói a pipeline e depois **parte-a de propósito**, sete vezes,
para ver como cada conceito a protege.

## 2. Arquitetura

```
 Synthetic Tracking API          (FastAPI, o producer)
          │
          ▼
    Apache Airflow               (orquestra; corre diariamente)
          │
   check_api ─► extract ─► validate ─► transform ─► load_dimensions ─► load_facts ─► quality_check
                   │          │            │               └──────────────┬──────────────┘
                   │      Pydantic      Pandas                        PostgreSQL
                   ▼                                                  (analytics)
        ficheiros temporários                                              │
        (só o caminho viaja no XCom)                                       ▼
                                                                  views analíticas
                                                           (Streamlit / Power BI, mais tarde)
```

**Três containers:**

| Container | Papel | Porta |
|---|---|---|
| `postgres` | UM servidor, DUAS bases de dados (ver abaixo) | 5432 |
| `api` | o producer (FastAPI) | 8000 |
| `airflow` | o orquestrador, em modo `standalone` | 8080 |

**Duas bases de dados, dois propósitos.** Esta distinção apanha toda a gente:

| | Base `analytics` | Base `airflow` |
|---|---|---|
| Para quê | os **dados do negócio**: `dim_*`, `fact_*`, views | o **estado do Airflow**: runs, tasks, retries, XComs |
| Quem escreve | o nosso ETL | só o Airflow |
| Variável | `DATABASE_URL` | `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` |
| Em produção | PostgreSQL no Render (por exemplo) | servidor próprio, isolado |

Para apontar a pipeline a outro PostgreSQL (o do Render, por exemplo), muda-se
**só** `DATABASE_URL`. Nunca há credenciais no código; ver `.env.example`.

**Mapa do código** (por ordem de leitura sugerida):

| Ficheiro | O que mostra |
|---|---|
| [data-structure-reference.md](data-structure-reference.md), [docs/data-model.md](docs/data-model.md), [sql/schema.sql](sql/schema.sql) | a estrutura real, o modelo, o grain, as chaves |
| [api/schemas.py](api/schemas.py) | o **contrato** |
| [api/generator.py](api/generator.py) | dados sintéticos determinísticos |
| [api/main.py](api/main.py), [api/faults.py](api/faults.py) | a API e a injeção de falhas |
| [pipeline/extract.py](pipeline/extract.py) → [validate.py](pipeline/validate.py) → [transform.py](pipeline/transform.py) → [load.py](pipeline/load.py) → [quality.py](pipeline/quality.py) | o ETL, em Python puro |
| [dags/tracking_pipeline.py](dags/tracking_pipeline.py) | o DAG: **só** orquestração |
| [sql/analytics.sql](sql/analytics.sql) | métricas derivadas |
| [scripts/demo_idempotency.py](scripts/demo_idempotency.py) | a demo de idempotência |

O pipeline em `pipeline/` **não importa o Airflow**. Isto é intencional: o código
de negócio testa-se sem Airflow, e o DAG fica fino. Se um DAG tem lógica de
negócio, está mal desenhado.

## 3. Tracking domain

Uma plataforma de performance marketing compra tráfego e ganha dinheiro quando
esse tráfego converte. O ciclo, tal como aparece nos dados reais
([data-structure-reference.md](data-structure-reference.md)):

1. Uma **campanha** (de um **workspace**) compra tráfego numa **fonte de tráfego**
   (ExoClick, TrafficStars...). O tráfego é pago por um **provider de
   investimento**; o custo e os clicks chegam **agregados por hora**.
2. Quando um visitante converte, uma rede de afiliação envia um **postback**: é
   uma **conversão** de uma **oferta**, com a sua receita (`revenue`).
3. Um sistema de backoffice mantém o **daily control**: o agregado diário
   (receita e investimento) por campanha. É uma **segunda fonte** sobre os mesmos
   números, e por vezes é editada à mão (`is_manual`).

Na realidade estes dados vivem em dois sítios (Mongo e Postgres). A nossa API
sintética expõe os dois lados num só serviço, e gera-os de forma **coerente**
(o daily control de um dia é a soma dos eventos desse dia, exceto nas linhas
manuais). Essa coerência é o que permite a reconciliação da secção 13.

| Conceito | No modelo |
|---|---|
| Workspace, TrafficSource, Campaign, Offer | dimensões |
| Conversion, CampaignTrafficSourceData (custo horário), DailyControl | facts |
| `investment_provider` (16 valores) | coluna simples (ainda não é dimensão) |
| Métricas base | `cost`, `clicks`, `impressions`, `revenue` |
| Métricas derivadas | conversions, CPC, CPM, CTR, CR, CPA, EPC, ROAS, profit, ROI |

## 4. Data model

```
dim_workspace(workspace_id PK, name)
dim_traffic_source(traffic_source_id PK, name, currency_code, deleted)
dim_campaign(campaign_id PK, name, geo, traffic_source_id FK, workspace_id FK, is_paused, created)
dim_offer(offer_id PK, name, country_code?, affiliate_network_id, affiliate_network_name,
          payout, currency_code, deleted)

fact_conversions(PK click_id + conversion_type_id + postback_timestamp,
                 visit_timestamp, visit_date,
                 campaign_id FK, traffic_source_id FK, offer_id FK, country_code,
                 revenue, revenue_original_currency)

fact_campaign_costs(PK datetime + campaign_id + investment_provider,
                    cost_date, campaign_id FK, cost, clicks?, impressions?)

fact_daily_control(PK date + campaign_id, campaign_id FK, revenue, investment, is_manual)
```

(`?` = opcional/nulo.) Detalhe e justificação das decisões em
[docs/data-model.md](docs/data-model.md). O DDL está em [sql/schema.sql](sql/schema.sql),
com o grain escrito nos comentários.

Três coisas que distinguem este modelo de um exemplo de manual, e que vêm dos
dados reais:

* **Não há ID por linha.** As chaves primárias são **compostas** e naturais.
* **Não há fact de clicks.** Os clicks só existem agregados por hora, dentro do custo.
* **Há uma fact vinda de outro sistema** (`fact_daily_control`), que serve para reconciliar.

## 5. Grain

> **Grain** = o que representa **uma linha**.

| Tabela | Grain |
|---|---|
| `fact_conversions` | **1 linha = 1 conversão** (um postback) |
| `fact_campaign_costs` | **1 linha = 1 campanha × 1 hora × 1 investment_provider** |
| `fact_daily_control` | **1 linha = 1 campanha × 1 dia** |

É a primeira decisão de modelação, porque tudo o resto depende dela: o que a PK
identifica, o que `count(*)` conta, o que se pode somar sem erro. Aqui há **três
grains diferentes**: por isso não se juntam as facts umas às outras antes de
agregar (secção 6).

Um caso para discutir: o mesmo `click_id` pode aparecer em **duas linhas** de
`fact_conversions` (uma conversão de tipo 1 e outra, mais tarde, de tipo 2).
`click_id` sozinho não é chave; o grain é a conversão, não o click.

## 6. Facts vs dimensions

* **Dimensions** descrevem (*quem, o quê, onde*). Poucas linhas, mudam devagar.
* **Facts** registam o que aconteceu. Muitas linhas, só crescem.
* **Métricas aditivas** (`cost`, `clicks`, `impressions`, `revenue`) guardam-se nas
  facts: somam-se por qualquer dimensão.
* **Métricas derivadas** (CPC, CPM, CTR, CR, CPA, EPC, ROAS, profit, ROI) **não** se
  guardam por linha. Calculam-se depois, em [sql/analytics.sql](sql/analytics.sql).

> **Soma primeiro, divide depois.** O ROAS da semana não é a média dos ROAS
> diários. Soma-se a receita, soma-se o custo, e divide-se.

Todas as divisões usam `NULLIF(denominador, 0)`: um dia sem conversões tem CPA
indefinido (`NULL`), não um erro de divisão por zero.

| Métrica | Fórmula |
|---|---|
| CPC | `cost / clicks` |
| CPM | `cost / impressions × 1000` |
| CTR | `clicks / impressions` |
| CR | `conversions / clicks` |
| CPA | `cost / conversions` |
| EPC | `revenue / clicks` |
| ROAS | `revenue / cost` |
| profit | `revenue - cost` |
| ROI | `profit / cost` |

**Nulos não são zeros.** Alguns providers não reportam `impressions` (`NULL`).
Se somássemos todos os clicks e dividíssemos pelas impressions que existem, o CTR
seria inflacionado; a view usa só os clicks das linhas que reportam impressions.

**A armadilha do fan-out.** `fact_conversions` e `fact_campaign_costs` têm grains
diferentes. Juntá-las e somar repetiria cada custo por cada conversão. As views
agregam cada fact **separadamente** e só depois juntam os resultados.

**Sem custo por oferta.** O custo não tem `offer_id`, por isso `v_offer_daily` só
tem conversões e receita. Uma métrica só existe ao grain em que todos os seus
ingredientes existem.

## 7. A API

Uma API fictícia em FastAPI ([api/main.py](api/main.py)). Documentação interativa
em <http://localhost:8000/docs>.

| Endpoint | O que devolve | Janela sobre |
|---|---|---|
| `GET /health` | `{"status": "ok"}` | |
| `GET /workspaces`, `/traffic-sources`, `/campaigns`, `/offers` | dimensões | |
| `GET /conversions` | conversões | `postback_timestamp` |
| `GET /campaign-costs` | custo por hora | `datetime` |
| `GET /daily-control` | agregado diário | `date` |

**Filtros dos factos:** `start_date`, `end_date`, `campaign_id`,
`traffic_source_id`, `limit` (1-1000, default 100), `offset`.

* O intervalo é **`[start_date, end_date)`**: início inclusivo, fim exclusivo, em
  UTC. É o mesmo desenho dos *data intervals* do Airflow; dois dias seguidos
  nunca partilham nem perdem um registo na fronteira.
* **Paginação com `limit`/`offset`**, num envelope:

  ```json
  { "data": [...], "count": 100, "total": 437, "limit": 100, "offset": 0 }
  ```

  `total` existe para o consumer detetar **truncagem**: sem ele, uma extração
  parcial parece completa, o pior tipo de bug em dados.
* **Determinismo.** A mesma seed (`API_SEED`) dá os mesmos dados, com os mesmos
  IDs. Não é um detalhe: é o que permite repetir uma demo, reprocessar um dia
  (backfill) e demonstrar idempotência.
* **Volume.** Cerca de 170 conversões, 190 linhas de custo horário e 6 linhas de
  daily control por dia.

Experimenta:

```bash
curl "localhost:8000/campaigns?limit=3"
curl "localhost:8000/campaign-costs?start_date=2026-10-01&end_date=2026-10-01T06:00:00&limit=3"
curl "localhost:8000/conversions?start_date=2026-10-01&end_date=2026-10-02&limit=3"
```

## 8. Data contract com Pydantic

> **A API é o producer.**
> **A pipeline é o consumer.**
> **O Pydantic representa o contrato entre ambos.**

O contrato é código executável: [api/schemas.py](api/schemas.py). Os campos vêm da
estrutura real, e o `?` dessa estrutura é aqui um campo opcional. O contrato mostra,
lado a lado, o que é obrigatório e opcional, os tipos (IDs estritos, em formato
UUID), os enums (16 `investment_provider`), as constraints (`cost >= 0`,
`revenue >= 0`, `country_code` com 2 letras maiúsculas, timestamps com timezone), uma
regra personalizada (o `datetime` do custo tem de ser uma hora certa) e os erros
que cada violação produz.

Documentação completa, com a tabela de erros reais:
[docs/data-contract.md](docs/data-contract.md).

**Producer-side vs consumer-side validation** é a ideia a levar daqui:

* A API valida o que **emite** (cada resposta passa pelos modelos).
* A pipeline valida o que **recebe** (task `validate`), mesmo que a API diga que
  está tudo bem.

Porquê as duas? Porque o producer pode estar errado sem o saber. No modo
`schema_drift` a API devolve o payload cru, sem o validar, como um producer que
mudou sem avisar. Só o consumer o apanha.

## 9. ETL

Cada passo é um módulo de Python puro, em [pipeline/](pipeline/):

| Passo | Módulo | O que faz |
|---|---|---|
| check_api | [extract.py](pipeline/extract.py) | `GET /health`; falha cedo se a API está mal |
| extract | [extract.py](pipeline/extract.py) | descarrega as 4 dimensões e as 3 facts da janela, **com paginação**, para ficheiros JSON |
| validate | [validate.py](pipeline/validate.py) | valida cada registo contra o contrato Pydantic |
| transform | [transform.py](pipeline/transform.py) | Pandas: UTC, strings, datas calculadas, tipos, duplicados |
| load | [load.py](pipeline/load.py) | upsert em PostgreSQL |
| quality_check | [quality.py](pipeline/quality.py) | verifica o conjunto de dados já carregado |

**Transformações** (Pandas, uma especificação por dataset em `SPECS`):
timestamps para UTC, strings limpas (`" pt "` → `"PT"`, `"ExoClick"` → `"exoclick"`),
datas calculadas (`visit_date`, `cost_date`), tipos garantidos (inteiros que
**aceitam NULL**, booleanos, decimais), duplicados removidos **pela chave
composta**. **Não** se calculam CPC nem ROAS aqui.

**Como é que os dados passam de uma task para a seguinte?** Não passam pelo XCom.
O XCom vive na base de dados do Airflow e serve para mensagens pequenas. Cada task
escreve ficheiros em `data/staging/<janela>/` e devolve só **caminhos e
contagens**:

```
data/staging/20261003T000000/
├── raw_conversions.json            ← extract
├── transformed_conversions.csv     ← transform
└── ...                             (um par por dataset: 7)
```

A pasta é determinada pela *janela*, não pela hora a que a run arrancou: voltar a
correr o mesmo dia reescreve os mesmos ficheiros, nunca acumula lixo.

Cada módulo pode correr sem Airflow (é assim que os testes funcionam):

```python
meta = extract.run_extract("2026-10-01T00:00:00+00:00", "2026-10-02T00:00:00+00:00")
meta = validate.run_validate(meta)
meta = transform.run_transform(meta)
```

## 10. Airflow

O DAG ([dags/tracking_pipeline.py](dags/tracking_pipeline.py)) é linear:

```
check_api >> extract >> validate >> transform >> load_dimensions >> load_facts >> quality_check
```

Dimensões antes de facts (as FKs apontam para elas); dentro das dimensões,
`workspaces` e `traffic_sources` antes de `campaigns` (que os referencia).

### Conceitos, onde os ver no código

| Conceito | No DAG |
|---|---|
| **DAG** | `with DAG(...)`: o grafo de tasks e as suas regras |
| **Task** | cada `PythonOperator` |
| **Dependencies** | o `>>` |
| **Scheduling** | `schedule=CronDataIntervalTimetable("@daily")`: uma run por dia |
| **Data interval** | uma run é uma *fatia de tempo*, não um instante. A run do dia 3 processa `[3 out, 4 out)` e só arranca quando esse dia acaba |
| **Retries** | `retries=2` |
| **retry_delay** | `timedelta(seconds=30)` (curto, só para a aula) |
| **Timeout** | `execution_timeout`: o Airflow mata uma tentativa que demore demais |
| **Logs** | UI → run → task → *Logs* |
| **Task failure** | estado `failed` / `upstream_failed` |
| **Catchup** | `catchup=False` |
| **Backfill** | reprocessar o passado sob comando (abaixo) |
| **Idempotency** | secção 12 |

### Data interval

Uma run **agendada** conhece a sua janela (`data_interval_start/end`) e passa-a ao
`extract`, que a envia à API como `start_date`/`end_date`. Por isso o DAG não
processa "o que houver agora": processa **um dia concreto**, e esse dia pode ser
reprocessado a qualquer momento com o mesmo resultado.

Uma nota sobre o Airflow 3: um `schedule="@daily"` simples já não cria data
intervals; daí o `CronDataIntervalTimetable` explícito. E uma run disparada
**à mão** não tem data interval; [pipeline/window.py](pipeline/window.py) resolve
a janela por esta ordem: `conf.date` → data interval → dia anterior (UTC).

### Executar o DAG

O DAG começa **pausado**. Na UI (<http://localhost:8080>): ativá-lo (toggle) e
*Trigger*. Ou por linha de comandos:

```bash
docker compose exec airflow airflow dags unpause tracking_pipeline

# processar um dia à escolha
docker compose exec airflow airflow dags trigger tracking_pipeline --conf '{"date": "2026-10-03"}'
```

Ao ativar o DAG, o scheduler cria logo a run do último dia completo (porque
`catchup=False` só salta os anteriores).

### Catchup e backfill

* **`catchup=False`** (o que usamos): ao ativar o DAG, não corre os dias que
  ficaram para trás desde `start_date`.
* **`catchup=True`**: correria todos. Perigoso com um `start_date` longínquo.
* **Backfill**: pedir explicitamente o passado, num intervalo:

  ```bash
  docker compose exec airflow airflow backfill create \
      --dag-id tracking_pipeline --from-date 2026-10-01 --to-date 2026-10-05
  ```

  Cria uma run por dia (1, 2, 3, 4 e 5 de outubro; ambos os limites inclusivos).
  Só é seguro porque a carga é idempotente: se algum desses dias já estava
  carregado, não se duplica nada.

### `airflow standalone`: uma simplificação para a formação

Usamos `command: standalone`, que corre **num só container** o que em produção são
componentes distintos:

| Componente | Função | Em `standalone` |
|---|---|---|
| **Scheduler** | decide o que corre e quando | dentro do container |
| **API server / UI** | interface web e API REST | dentro do container |
| **DAG processor** | lê e interpreta os ficheiros dos DAGs | dentro do container |
| **Triggerer** | corre tasks assíncronas (deferrable) | dentro do container |
| **Workers / executor** | executam as tasks | `LocalExecutor`: processos no mesmo container |

Continuam a ser **conceitos separados**: aparecem separados nos logs
(`scheduler |`, `dag-processor |`...). Mas a topologia de produção é diferente:
componentes em processos ou máquinas distintas, um executor distribuído
(Celery, Kubernetes) em vez de `LocalExecutor`, base de dados de metadados
gerida e com backups, autenticação a sério. Aqui também **não há ecrã de
login** (`SIMPLE_AUTH_MANAGER_ALL_ADMINS=True`), o que nunca se faz fora de uma aula.

## 11. Retries e failures

### Retry é para erros transitórios

Um 500 pode desaparecer sozinho; um timeout também. Para isso servem `retries` e
`retry_delay`. Mas retentar um erro **determinístico** só adia a falha: um campo
renomeado vai continuar renomeado daqui a 30 segundos. Por isso `validate` e
`quality_check` têm `retries=0` e falham logo.

### Duas camadas de timeout

1. **HTTP** (`PIPELINE_HTTP_TIMEOUT_SECONDS`, 5 s): o pedido à API desiste.
2. **Task** (`execution_timeout`, 2 min): o Airflow mata a tentativa inteira.

A primeira apanha a API pendurada; a segunda apanha tudo o resto (um loop, um
bloqueio na base de dados). Convém que a primeira seja bastante menor.

### Os 7 cenários

Cada cenário: pôr a API num modo, disparar o DAG, ver, repor.

```bash
curl -X POST localhost:8000/admin/mode/<modo>        # 1. provocar a falha
docker compose exec airflow airflow dags trigger tracking_pipeline --conf '{"date": "2026-10-03"}'
#   ...observar na UI (http://localhost:8080)...
curl -X POST localhost:8000/admin/mode/healthy       # 3. repor
```

| # | Cenário | Modo | O que vês | Tempo |
|---|---|---|---|---|
| 1 | API funciona | `healthy` | as 7 tasks a verde | ~30 s |
| 2 | API devolve 500 | `http_500` | `check_api` falha 3 vezes (1 + 2 retries); resto `upstream_failed`; DAG `failed` | ~1 min |
| 3 | API lenta | `slow` | `check_api` passa (o `/health` é rápido!); `extract` esgota o timeout de 5 s, 3 tentativas, `failed` | ~1,5 min |
| 4 | API devolve 429 | `rate_limit` | `check_api` falha 2 vezes e **passa à 3.ª**; DAG `success` | ~1 min |
| 5 | Campo mudou de nome | `schema_drift` | `extract` OK, **`validate` falha**: `revenue`/`cost` em falta + `revenue_amount`/`cost_amount` desconhecidos | imediato |
| 6 | Revenue negativo | `invalid_payload` | **`validate` falha**: `revenue`/`cost` < 0, `clicks` < 0 e `country_code` inválido | imediato |
| 7 | Evento repetido | `healthy` | voltar a disparar o **mesmo dia**: sem duplicados (secção 12) | ~30 s |

Pormenores que dão boa conversa:

* **Cenário 3:** o `/health` está verde e o `extract` falha na mesma. Um health
  check não prova que os dados estão acessíveis.
* **Cenário 4:** `rate_limit` falha só as primeiras `fail_times` chamadas
  (`curl -X POST "localhost:8000/admin/mode/rate_limit?fail_times=2"`) e depois
  recupera. Com `fail_times=3`, os `retries=2` não chegam e o DAG falha.
  Experimenta.
* **Cenários 5 e 6:** a API respondeu **200**, a tempo, sem erros. Nenhuma
  monitorização de disponibilidade vê o problema; só a validação do contrato.
* Uma task a `upstream_failed` **nunca correu**: dados maus não chegam ao destino.
* Para repetir uma task falhada sem repetir o DAG inteiro: UI → *Clear* nessa task.

### Fault injection

```bash
curl -X POST localhost:8000/admin/mode/healthy
curl -X POST localhost:8000/admin/mode/http_500
curl -X POST localhost:8000/admin/mode/slow
curl -X POST "localhost:8000/admin/mode/rate_limit?fail_times=2"
curl -X POST localhost:8000/admin/mode/invalid_payload
curl -X POST localhost:8000/admin/mode/schema_drift
curl localhost:8000/admin/mode                       # ver o modo atual
```

> **Isto é apenas para formação.** Um endpoint que sabota o próprio serviço, sem
> autenticação e na mesma porta do tráfego normal, **não seria implementado assim
> em produção**. Em produção usam-se ferramentas de chaos engineering (Toxiproxy,
> Chaos Mesh, Gremlin...) em ambientes isolados, com autenticação, auditoria e um
> botão de "parar tudo". O estado é só em memória: reiniciar a API volta a
> `healthy`.

## 12. Idempotency

> Uma operação é **idempotente** se executá-la 1, 2 ou 10 vezes deixa o sistema no
> mesmo estado.

Não é um luxo. O Airflow **retenta** tasks e **reprocessa** o passado (backfill);
operadores clicam em *Clear* e voltam a correr. Se a carga não for idempotente, cada
um destes gestos duplica dados em silêncio.

### Como

1. A **primary key** identifica a linha. Aqui é **composta**, porque a origem não
   tem um ID por linha: uma conversão é `(click_id, conversion_type_id,
   postback_timestamp)`; um custo horário é `(datetime, campaign_id,
   investment_provider)`.
2. O `INSERT ... ON CONFLICT (chave inteira) DO UPDATE` ("upsert") diz ao PostgreSQL
   o que fazer quando a linha já existe: atualizar em vez de duplicar.
3. O gerador é determinístico: a mesma linha chega **sempre com a mesma chave**.

```sql
INSERT INTO fact_conversions (click_id, conversion_type_id, postback_timestamp, ...) VALUES (...)
ON CONFLICT (click_id, conversion_type_id, postback_timestamp)
DO UPDATE SET revenue = EXCLUDED.revenue, ..., updated_at = now();
```

Código: `upsert()` em [pipeline/load.py](pipeline/load.py). Cada carga regista
`{'inserted': N, 'updated': M}`: numa 1.ª execução `inserted` é N; numa 2.ª,
`updated` é N e `inserted` é 0.

Porque é que a chave importa: se a chave fosse só `click_id`, a segunda conversão
de um click (tipo 2) **sobrescreveria** a primeira, e perdia-se receita sem
nenhum erro. Escolher a chave é escolher o grain.

### Demonstração: ingénua vs idempotente

```bash
docker compose exec -w /opt/airflow/project airflow python -m scripts.demo_idempotency
```

```
          INGENUO (insert)             IDEMPOTENTE (upsert)
execucao  linhas / chaves distintas    linhas / chaves distintas    inseridas / atualizadas
----------------------------------------------------------------------------------------
run 1     172 / 172                    172 / 172                    172 / 0
run 2     344 / 172                    172 / 172                    0 / 172
run 3     516 / 172                    172 / 172                    0 / 172

Ingenuo:     172 conversoes aparecem 3 vezes. Receita: 13,595.40 USD (devia ser 4,531.80).
```

As mesmas conversões do mesmo dia, carregadas três vezes, em duas tabelas
idênticas: uma sem PK e com `INSERT` simples, outra com PK composta e upsert. A
ingénua triplica a receita. Olha para `loaded_at` (não muda) e `updated_at` (muda
a cada run) em `demo_idempotent_conversions`. A demo usa tabelas próprias e não toca
em `fact_conversions`.

### Cenário 7, no DAG

Dispara o DAG duas vezes para o mesmo dia e compara:

```bash
docker compose exec postgres psql -U tracking -d analytics \
  -c "SELECT visit_date, count(*) FROM fact_conversions GROUP BY 1 ORDER BY 1"
```

A contagem não muda. No log de `load_facts` vês `{'inserted': 0, 'updated': 175}`
(o número de conversões desse dia).

### Alternativas (para discussão)

* `ON CONFLICT DO NOTHING`: ignora o que já existe. Idempotente, mas não corrige
  uma linha que mudou na origem. (Repara que uma conversão **pode** mudar: o
  `revenue` de um postback pode ser corrigido.)
* *Delete-then-insert* da janela, numa transação: também idempotente; apaga e
  reinsere. Mais simples de entender, mais caro e mais difícil de fazer bem.
* Transações: `load_dimensions` e `load_facts` são, cada um, **uma transação**:
  falhar a meio não deixa meia carga.

## 13. Data quality

Dois portões, com responsabilidades diferentes:

| `validate` (antes do load) | `quality_check` (depois do load) |
|---|---|
| Pydantic | SQL |
| Este **registo** tem a forma certa? | Este **conjunto** faz sentido? |
| schema · campos obrigatórios e opcionais · tipos · enums · `revenue >= 0` · `cost >= 0` · formato de `country_code` · hora certa | row count > 0 · freshness · chaves únicas · FKs válidas · `postback_timestamp >= visit_timestamp` · fonte da conversão == fonte da campanha · **reconciliação** com o daily control |

Os checks estão em [pipeline/quality.py](pipeline/quality.py). Correm **todos**
(mesmo que o primeiro falhe) e a task falha no fim, com a lista completa.

* **Freshness:** a última hora de custo tem de estar a menos de
  `PIPELINE_FRESHNESS_MAX_LAG_HOURS` (6 h) do fim da janela. Apanha extrações
  truncadas ou dias a meio.
* **Constraints vs checks:** a PK e as FKs já impedem chaves repetidas e órfãos. Os
  checks repetem-nos de propósito: a constraint é a primeira linha de defesa, o
  check é a segunda (protege-te de um destino sem FKs, como um data warehouse) e dá
  uma métrica auditável.
* **Reconciliação, o check que mais vale a pena.** O `fact_daily_control` vem de
  *outro sistema* e as conversões e custos vêm de eventos. Os dois devem somar o
  mesmo por campanha e por dia (tolerância de 0,05). Nenhuma constraint apanha dois
  sistemas a discordar. As linhas `is_manual` ficam de fora: alguém escreveu
  aqueles números à mão, e a discordância é esperada. Podes ver o resultado na view
  `v_reconciliation_daily`.
* **O que fica de fora, e porquê:** uma regra como `conversions <= clicks` **não** é
  universal. Um click pode gerar várias conversões; os dados sintéticos geram até
  conversões de tipo 2 para o mesmo click. Seria legítimo acrescentá-la só num
  dataset onde se saiba que é verdade; ver [docs/data-model.md](docs/data-model.md).

### Provocar uma falha no `quality_check`

Nenhum modo da API a provoca (a API só parte o contrato, e isso falha no
`validate`). Adultera-se a base de dados e re-corre-se só essa task. Por exemplo,
faz-se com que o daily control discorde dos eventos:

```bash
docker compose exec postgres psql -U tracking -d analytics -c \
  "UPDATE fact_daily_control SET revenue = revenue + 100
   WHERE NOT is_manual AND date = '2026-10-03'
     AND campaign_id = (SELECT campaign_id FROM fact_daily_control
                        WHERE NOT is_manual AND date = '2026-10-03' LIMIT 1)"
```

Depois, na UI (<http://localhost:8080>), na run que carregou esse dia: abrir a task
`quality_check` → *Clear task* (só ela, sem as dependentes). Falha com
`reconciliacao: revenue (eventos vs daily control)`. Para curar, re-corre-se o DAG
inteiro desse dia: o upsert repõe o valor correto (idempotência a trabalhar a teu
favor). Outras adulterações para experimentar: `visit_timestamp` depois do
`postback_timestamp`, ou uma `traffic_source_id` diferente da da campanha.

**Evolução de produção (não implementada):** quarentena. Em vez de falhar tudo
por um registo inválido, mandá-lo para uma tabela `rejected_records` e falhar
apenas acima de um limiar. Ver [docs/data-contract.md](docs/data-contract.md).

## 14. Observability

Não está instalada, de propósito. Está **documentada** como próxima fase, em
[docs/observability-roadmap.md](docs/observability-roadmap.md):

```
API ─► Blackbox Exporter ─► Prometheus ─► Grafana
Airflow metrics ─────────► Prometheus ─► Grafana
```

Três tipos de observabilidade, que respondem a três perguntas diferentes:

| | Pergunta | Exemplo |
|---|---|---|
| **Pipeline** | O job correu? | DAG success/failure, retries, duração das tasks |
| **Source** | A fonte está bem? | disponibilidade, latência e status HTTP da API |
| **Data** | Os dados estão bem? | record count, freshness, duplicados, falhas de validação |

Uma pipeline pode estar **verde** e os dados errados (cenários 5 e 6 numa pipeline
sem `validate`). É por isso que os três níveis existem, e que o `quality_check`
vive dentro do DAG.

## 15. Exercícios

**Airflow**
1. Muda `retries` para 0 e repete o cenário 2. O que muda na UI e no tempo?
2. Põe `retry_exponential_backoff=True` e `retry_delay=timedelta(minutes=1)`. Calcula
   quanto demora o DAG a desistir.
3. Aumenta o timeout HTTP para 30 s (`PIPELINE_HTTP_TIMEOUT_SECONDS`) e repete o
   cenário 3. Que timeout apanha agora a API lenta?
4. Põe `catchup=True`, recria o DAG e vê quantas runs aparecem. Porque é perigoso?
5. Faz um backfill de uma semana. Depois repete-o. O que muda na base de dados?
6. Muda o `schedule` para de hora a hora. Que alterações são precisas no `extract`
   e nas views? (Pista: `fact_daily_control` é diário.)

**Modelo e SQL**
7. Cria `dim_affiliate_network(affiliate_network_id PK, name)` e passa
   `dim_offer.affiliate_network_id` a FK. Que mudanças tens de fazer no contrato, no
   transform e no load?
8. Escreve uma query que mostre o ROAS semanal por fonte de tráfego. Faz primeiro a
   versão errada (`AVG(roas)`) e compara.
9. Cria `dim_investment_provider(name, fee)` e usa-a para calcular o custo com fee
   por campanha.
10. Que campanhas dão prejuízo, e porquê? (Pista: CPC contra EPC, por fonte e por oferta.)

**Contrato e qualidade**
11. Muda `extra="forbid"` para `extra="ignore"`. O `schema_drift` continua a falhar?
    Porquê? E se o producer apenas *acrescentasse* um campo?
12. Acrescenta ao `quality_check` uma regra: cada campanha ativa tem custo nas 24
    horas do dia. Que dataset-specific assumes?
13. Implementa a quarentena: `rejected_records` e um limiar de rejeição.
14. Acrescenta uma tabela `exchange_rate` (moeda → USD, por dia) e usa-a no transform
    em vez da taxa fixa do gerador.
    Que muda no grain de `fact_conversions`?

**Idempotência**
15. Troca `DO UPDATE` por `DO NOTHING`. O que muda em `updated_at`? E se um postback
    fosse corrigido na origem (outro `revenue` para a mesma chave)?
    E se a chave de `fact_conversions` fosse só `click_id`?
16. Implementa a carga como *delete-then-insert* da janela. Compara.

**Ligar ao mundo**
17. Aponta `DATABASE_URL` para um PostgreSQL no Render (acrescenta `?sslmode=require`).
    O que continua local? (Pista: a base de metadados do Airflow.)
18. Liga o Power BI ou um Streamlit às views `v_*_daily`.
19. Mostra o CTR de `v_campaign_daily` para uma campanha com dois providers, um dos
    quais sem impressions. Compara com `sum(clicks) / sum(impressions)`.

---

## Anexo A · Arrancar, URLs e reset

**Pré-requisitos:** Docker com Compose v2. Para correr os testes no host,
Python 3.11+.

### Arrancar do zero

```bash
cd aula02-airflow-tracking
cp .env.example .env                 # não ponhas credenciais reais no .env.example
docker compose up -d --build         # 1.ª vez: ~2 min (build das imagens)
docker compose ps                    # os 3 serviços devem estar "running"
```

O Airflow demora ~30 s a arrancar depois dos containers estarem `running`. Segue
com `docker compose logs -f airflow`.

### URLs

| O quê | URL |
|---|---|
| Airflow UI (sem login) | <http://localhost:8080> |
| API · documentação interativa | <http://localhost:8000/docs> |
| API · health | <http://localhost:8000/health> |
| API · modo atual | <http://localhost:8000/admin/mode> |
| PostgreSQL (analytics) | `postgresql://tracking:tracking@localhost:5432/analytics` |

### Ver os dados

```bash
docker compose exec postgres psql -U tracking -d analytics
```
```sql
SELECT * FROM v_campaign_daily ORDER BY event_date DESC, profit DESC LIMIT 10;
\dt          -- tabelas
\dv          -- views
```

### Testes

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d postgres        # os testes de BD precisam dele
pytest                               # ~95 testes, 2-3 s
```

Os testes de base de dados correm num **schema temporário** (nunca tocam nas tabelas
reais) e são saltados se o PostgreSQL não estiver acessível.

### Reset

```bash
docker compose down -v               # apaga containers E volumes (as DUAS bases de dados)
rm -rf data/staging/*                # ficheiros temporários (o .gitkeep fica: é um ficheiro oculto)
docker compose up -d --build         # recomeçar
```

Para repor **só os dados de negócio** e manter o histórico de runs do Airflow:

```bash
docker compose exec postgres psql -U tracking -d analytics -c \
  "TRUNCATE fact_daily_control, fact_campaign_costs, fact_conversions, dim_campaign, dim_traffic_source, dim_workspace, dim_offer"
```

### Parar

```bash
docker compose stop                  # pára, mantém os dados
docker compose down                  # remove os containers, mantém os volumes
```

## Anexo B · Simplificações pedagógicas

Escolhas feitas para manter o foco nos conceitos. Nenhuma é o que se faria em
produção.

| Simplificação | Em produção |
|---|---|
| `airflow standalone` num container | componentes separados, executor distribuído |
| Sem login no Airflow | autenticação e RBAC |
| Um servidor PostgreSQL com duas bases | servidores separados |
| `/admin/mode` sem autenticação | chaos tooling dedicado, isolado, com auditoria |
| Contrato partilhado por pasta montada | pacote/schema versionado e registry |
| Ficheiros temporários num volume local | object storage (S3...) |
| `retry_delay` de 30 s | minutos, com backoff exponencial |
| SCD tipo 1 (sem histórico) | SCD tipo 2 onde o histórico importa |
| `validate` falha tudo se um registo é inválido | quarentena + limiar |
| Dimensões que nunca mudam | dimensões que mudam e precisam de SCD |
| `exchange_rate` fixo no gerador | tabela de taxas por dia |
| O postback chega sempre no dia da visita | *late-arriving data*: postbacks dias depois |
| `float` para dinheiro na API, `NUMERIC` na BD | `Decimal` ou inteiros em cêntimos de ponta a ponta |
| `affiliate_network` dentro de `dim_offer`; `investment_provider` como coluna | dimensões próprias quando tiverem atributos |

## Anexo C · Troubleshooting

**A UI do Airflow não abre.** Espera ~30 s depois do `docker compose up`. Vê
`docker compose logs airflow`.

**Disparei o DAG e a run fica `queued`.** O DAG está pausado: ativa-o
(`airflow dags unpause tracking_pipeline`, ou o toggle na UI).

**`port is already allocated` (5432).** Tens outro PostgreSQL local. Põe
`POSTGRES_HOST_PORT=5433` no `.env` e usa `localhost:5433` no host. Dentro do
Docker nada muda.

**Mudei o `.env` e nada mudou.** `docker compose up -d` (recria o que mudou).
Para a API, `--build` só é preciso se mudaste código.

**Mudei o código da API e nada mudou.** A API é copiada para a imagem:
`docker compose up -d --build api`. O código do `pipeline/` e o DAG são montados
por volume e não precisam de rebuild.

**Os testes de BD são todos saltados.** O PostgreSQL não está acessível:
`docker compose up -d postgres`. Se usas outra porta, define `TEST_DATABASE_URL`.

**Linux: `Permission denied` em `data/staging`.** O Airflow corre como o utilizador
`airflow` (uid 50000) e escreve na pasta montada: `chmod -R a+rwX data/staging`.

**O DAG não aparece.** `docker compose exec airflow airflow dags list-import-errors`.

**A API ficou num modo de falha.** `curl -X POST localhost:8000/admin/mode/healthy`
(ou reinicia o container: o estado é só em memória).
