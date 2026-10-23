# Provider Pipelines · Apache Airflow

> Dois providers reais de performance marketing, dois schemas completamente
> diferentes, **um só modelo interno**.
> **Python · Pandas · FastAPI (mocks) · Pydantic · Apache Airflow · PostgreSQL · Docker Compose**

Projeto do Módulo 03 do AI Engineering Course. Parte de dois casos reais
(**TrafficJunky** e **Erobella**) e ensina Airflow através de um problema realista,
mas **deliberadamente simplificado**.

> A mensagem central da aula:
>
> **contratos externos dos providers → transformação específica de cada um → contrato interno (canónico)**

> Os dados são **100 % sintéticos** (uma mock API determinística). Nenhum dado é real
> e não há tokens reais no repositório.

**Deliberadamente fora de âmbito:** dbt, Spark, Kafka, Celery, Kubernetes, S3 real,
MongoDB, Sentry, Slack, Great Expectations, e a stack Prometheus/Grafana (que é a aula
seguinte; esta aula prepara-a).

---

## Índice

1. [O problema](#1-o-problema)
2. [Arquitetura](#2-arquitetura)
3. [Primeiro provider: TrafficJunky](#3-primeiro-provider-trafficjunky)
4. [Chegou um segundo provider: Erobella](#4-chegou-um-segundo-provider-erobella)
5. [A necessidade do modelo canónico](#5-a-necessidade-do-modelo-canónico)
6. [Modelo de dados e grain](#6-modelo-de-dados-e-grain)
7. [Mock APIs e fault injection](#7-mock-apis-e-fault-injection)
8. [Airflow: dois DAGs](#8-airflow-dois-dags)
9. [Idempotency](#9-idempotency)
10. [Reconciliation](#10-reconciliation)
11. [Os oito cenários](#11-os-oito-cenários)
12. [O momento final: *partial data*](#12-o-momento-final-partial-data)
13. [Observability: a próxima aula](#13-observability-a-próxima-aula)
14. [Do caso real para a aula](#14-do-caso-real-para-a-aula)
15. [Limitações: as APIs reais](#15-limitações-as-apis-reais)
16. [Exercícios](#16-exercícios)

Anexos: [A. Arrancar, URLs e reset](#anexo-a--arrancar-urls-e-reset) ·
[B. Troubleshooting](#anexo-b--troubleshooting)

---

## 1. O problema

Uma equipa depende dos dados de **investimento** (quanto se gastou em cada campanha,
em cada fonte de tráfego) para o seu controlo diário. Esses dados vivem nas APIs dos
providers de tráfego. Hoje são recolhidos por jobs Celery; queremos passá-los para o
Airflow, onde **cada passo se vê e se repete**, e onde **cada dia guardado é
comparado com a API**.

Esta aula reproduz, em ponto pequeno, dois tickets reais:

* **ENG-387**, TrafficJunky: o *piloto*. Stats de campanhas por dia, paginadas.
* **ENG-392**, Erobella: o segundo provider, bloqueado pelo primeiro porque segue o
  mesmo fluxo.

"Fiável" é a palavra difícil. Na vida real o provider cai, fica lento, limita o ritmo,
muda um campo sem avisar, envia campanhas que não sabemos mapear, devolve respostas
**incompletas com HTTP 200**, e a pipeline corre duas vezes sobre o mesmo dia. A aula
constrói a pipeline e depois **parte-a de propósito**.

## 2. Arquitetura

```
 Mock APIs (ou APIs reais)
          │
          ▼
    Apache Airflow
          │
   check_api ─► extract ─► validate_source ─► transform ─► validate_canonical ─► load ─► reconcile
                  │              │                │               │                │        │
              data/raw/      contrato do      específico de    modelo           PostgreSQL  total da API
              (resposta      PROVIDER         cada provider    CANÓNICO                     vs
               tal como                                                                    SUM(cost)
               chegou)
```

**Três containers:**

| Container | Papel | Porta (host) |
|---|---|---|
| `postgres` | UM servidor, DUAS bases de dados | 5433 |
| `mock-api` | os dois providers falsos (FastAPI), com fault injection | 8001 |
| `airflow` | o orquestrador, em modo `standalone` | 8081 |

As portas do host são diferentes das da aula 02 (5432/8000/8080): podes ter as duas
aulas ligadas ao mesmo tempo.

**Duas bases de dados, dois propósitos:**

| | Base `analytics` | Base `airflow` |
|---|---|---|
| Para quê | os dados: `dim_campaign`, `fact_campaign_daily` | o estado do Airflow: runs, tasks, XComs |
| Variável | `DATABASE_URL` | `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` |

**Mapa do código:**

```
dags/        trafficjunky_daily.py   erobella_daily.py     só orquestração
providers/   trafficjunky.py         erobella.py           o que é ESPECÍFICO de cada provider
contracts/   trafficjunky.py         erobella.py           contratos de ORIGEM
             canonical.py                                  contrato INTERNO
pipeline/    config.py http.py raw.py validate.py          o que é COMUM
             load.py reconcile.py window.py
mock_api/    main.py faults.py datasets.py config.py       os providers falsos
sql/         schema.sql analytics.sql
data/        campaigns.csv  raw/  staging/
```

> **"O Airflow não faz a transformação. O Airflow orquestra a transformação."**
> Os DAGs só chamam funções Python puras, que se testam sem Airflow. Não há framework
> genérico de providers: há dois módulos, um por provider.

## 3. Primeiro provider: TrafficJunky

Começamos por **um** provider, sem ideias de generalização.

### O que o provider nos dá

* Stats de campanhas **por dia**: `GET stats?startDate=DD/MM/YYYY&endDate=DD/MM/YYYY`,
  **sem timezone**, **paginadas** (`limit`/`offset`).
* **Uma linha por campanha do provider**: nome, tipo, impressions, clicks, cost, e uns
  rácios (`ecpc`, `ecpm`, `ctr`).

### O que a pipeline faz

| Task | O que faz |
|---|---|
| `check_api` | `GET` ao health do provider (`/mock/<provider>/health`); falha cedo se o provider está mal. Sem `*_HEALTH_PATH` configurado, regista que não há health check e passa |
| `extract` | percorre **todas as páginas**, verifica `len(linhas) == total`, guarda a resposta **raw** em `data/raw/trafficjunky/date=YYYY-MM-DD/response.json` e devolve só **caminhos e contagens** (XCom) |
| `validate_source` | o payload tem a forma do **contrato do provider**? |
| `transform` | as regras do provider (abaixo) |
| `validate_canonical` | o resultado respeita o **nosso** modelo? |
| `load` | upsert idempotente em PostgreSQL |
| `reconcile` | o total na base de dados bate com o da API? |

### As regras do TrafficJunky (`providers/trafficjunky.py`)

1. **Ignorar** campanhas `campaign_type == "deal"`.
2. **Mapear** cada campanha do provider para a **nossa** (`dim_campaign`) **por nome**.
   Campanha **sem correspondência**: descartada e registada.
3. **Agregar** campanhas com o **mesmo nome** numa só linha (somam-se impressions,
   clicks e cost).

Log real de uma run (modo `dirty_data`):

```
CRITICAL trafficjunky: 1 campanhas sem correspondencia em dim_campaign (descartadas): ['TJ Unmapped Campaign Test']
CRITICAL trafficjunky: nomes de campanha duplicados (agregados): ['TJ DE Loans']
INFO     trafficjunky 2026-10-22: fetched=8 deals_skipped=1 dropped=1 merged=1 saved=5
```

(Nos tickets reais isto vai para o Sentry como *critical*; aqui, para o log. Cada run
regista quantas linhas foram guardadas, agregadas e descartadas.)

### Rejeitar uma linha ≠ falhar a task

Há duas coisas muito diferentes, e a separação é deliberada:

| | Onde | O que acontece |
|---|---|---|
| Payload estruturalmente quebrado (campo em falta, tipo errado, campo renomeado) | `validate_source` | **a task falha** |
| Linha válida mas **impossível de mapear** para o nosso domínio | `transform` | **a linha é descartada e registada**; a task continua |

Uma campanha que não sabemos mapear não é um erro do contrato: é um dado válido
fora do nosso domínio. Mas descartá-la tem um custo: o investimento dessa campanha não
chega à base de dados. Quem o revela é a [reconciliação](#10-reconciliation). Não há
quarentena nesta versão.

### Os dados chegam ao modelo

O resultado do transform é uma linha por campanha e dia, com o
`campaign_id` **nosso**, `source_specific_id = NULL` (o TrafficJunky não tem mais
nível de detalhe), a moeda, e só as métricas **base**: impressions, clicks, cost.
Funciona. Por agora, é só isto.

## 4. Chegou um segundo provider: Erobella

> *"Chegou um segundo provider, e o schema é completamente diferente."*

| | TrafficJunky | Erobella |
|---|---|---|
| Estrutura | uma lista paginada | **três partes**: `by_day_creative`, `by_creative`, `by_day` |
| Nível de detalhe | campanha | **creative** |
| Onde está a campanha | no **nome** | escondida num **link** do creative |
| Duplicados | agregam-se por nome | não há: cada creative é uma linha |
| Total do dia | endpoint à parte | `by_day`, na própria resposta |
| Moeda | não indicada | no nome do campo: `cost_eur` |

O desempenho está por *creative*. Para saber de que **campanha** é uma linha de
desempenho é preciso cruzar `by_day_creative` com `by_creative` pelo `label` e
**extrair o UUID do link** do creative:

```
https://trk.example/<uuid>?creative=x          UUID no caminho
https://trk.example/click?vcid=<uuid>&...      parâmetro vcid
```

Essa extração é **uma função pequena e testada** (`extract_campaign_id`, em
`providers/erobella.py`): dois formatos, maiúsculas, UUID truncado ou colado a mais
texto, `None`, `""`... Devolve `None` quando não há UUID, nunca levanta exceção.

**As regras da Erobella (`providers/erobella.py`):**

1. ler `by_day_creative`;
2. ir buscar o `link` do creative a `by_creative` (pelo `label`);
3. extrair o UUID da campanha do link;
4. creative **sem link**, ou cujo link **não tem UUID**, ou cujo UUID **não é uma campanha
   nossa**: descartado e registado;
5. `source_specific_id = label` do creative.

```
CRITICAL erobella: 2 creatives sem campanha identificavel (descartados): sem link=['orphan-no-link'], link sem UUID=['bad-link'], campanha desconhecida=[]
INFO     erobella 2026-10-24: fetched=9 dropped=2 saved=7
```

Repara no que **não** mudou: o DAG tem exatamente as mesmas 7 tasks, pela mesma ordem.
O que mudou foi o **schema**, e todo ele vive dentro de `providers/erobella.py`.

## 5. A necessidade do modelo canónico

Agora temos dois providers a produzir resultados semelhantes, mas vindos de formas
muito diferentes. Se não os juntarmos, teremos duas tabelas, duas análises e duas
definições de "custo por campanha".

O modelo canónico **nasce desta necessidade**, não de uma abstração:

```
contrato EXTERNO            transformação ESPECÍFICA        contrato INTERNO
(de cada provider)          (de cada provider)              (nosso)

TrafficJunky ──► validate_source ──► transform ──┐
Erobella     ──► validate_source ──► transform ──┴──► validate_canonical ──► CampaignDailyStat
```

```python
class CampaignDailyStat(BaseModel):              # contracts/canonical.py
    date: date
    provider: Provider                           # trafficjunky | erobella
    campaign_id: UUID                            # sempre o NOSSO campaign_id
    source_specific_id: str | None               # TrafficJunky: None · Erobella: label do creative
    currency: str                                # ISO 4217
    impressions: int
    clicks: int
    cost: Decimal
```

> **contrato do provider ≠ contrato interno**

| | `validate_source` | `validate_canonical` |
|---|---|---|
| Pergunta | o payload do **provider** tem a forma esperada? | o registo **transformado** respeita o **nosso** modelo? |
| Contrato | `contracts/trafficjunky.py`, `contracts/erobella.py` | `contracts/canonical.py` |
| Campos extra | **ignora** (o provider acrescenta campos quando quer) | **proíbe** (o modelo é nosso) |

Detalhe e justificação em [docs/canonical-model.md](docs/canonical-model.md); campo a
campo em [docs/provider-mapping.md](docs/provider-mapping.md).

## 6. Modelo de dados e grain

```
dim_campaign                          fact_campaign_daily
------------                          -------------------
campaign_id  PK (UUID)                date
campaign_name  (único)                provider
                                      campaign_id   FK
                                      source_specific_id  (NULL no TrafficJunky)
                                      currency
                                      impressions, clicks, cost
                                      loaded_at, updated_at
```

**Grain:**

> **1 linha = 1 dia + 1 provider + 1 campanha + 1 `source_specific_id`**

* TrafficJunky: `source_specific_id = NULL` → uma linha por campanha e dia.
* Erobella: `source_specific_id = label do creative` → uma linha por creative e dia.

Duas fontes com **grains de origem diferentes** (campanha vs creative) convergem
neste grain comum porque o que difere cabe numa **coluna opcional**.

### Só métricas base na fact

A fact guarda `impressions`, `clicks` e `cost`. **CPC, CPM e CTR não se guardam**:
derivam-se na view, com `NULLIF`:

| Métrica | Fórmula |
|---|---|
| CPC | `cost / NULLIF(clicks, 0)` |
| CPM | `cost / NULLIF(impressions, 0) × 1000` |
| CTR | `clicks / NULLIF(impressions, 0)` |

```sql
SELECT * FROM v_stat_ratios;       -- ao grain da fact
SELECT * FROM v_campaign_daily;    -- por campanha: os creatives somam-se ANTES de dividir
```

**Rácios do provider vs rácios recalculados.** Os contratos de origem *recebem*
`ecpc`/`ecpm`/`ctr` quando o provider os envia, mas o modelo analítico não os guarda:
vêm arredondados a 2 casas (não batem com `cost / clicks`), em unidades diferentes
(`ctr` em percentagem) e não se somam. Ao agregar duas campanhas com o mesmo nome, o
rácio reportado de uma delas deixa de fazer sentido; recalculado a partir das
métricas base é sempre coerente. Soma primeiro, divide depois.

### Moeda

`currency` está no modelo e na fact. **Custos de moedas diferentes nunca se agregam
diretamente sem conversão.** As views agrupam por `currency` e a reconciliação compara
por `currency`.

> **Simplificação pedagógica:** nesta aula os dois providers faturam em **EUR**
> (`TrafficJunky` = EUR, `Erobella` = EUR). Serve para mostrar o campo sem introduzir
> conversão cambial. Na realidade, os providers podem faturar em moedas diferentes.

### A chave de idempotência e o `NULL`

```sql
UNIQUE NULLS NOT DISTINCT (date, provider, campaign_id, source_specific_id)
```

Ver a [secção 9](#9-idempotency).

## 7. Mock APIs e fault injection

A aula não pode depender de APIs externas. Com `USE_MOCK_API=true` (por omissão), a
pipeline fala com uma **mock API** local, determinística (mesma seed e mesmo dia dão
os mesmos dados).

```
GET  /mock/trafficjunky/health
GET  /mock/trafficjunky/stats?startDate=DD/MM/YYYY&endDate=DD/MM/YYYY&limit=&offset=
GET  /mock/trafficjunky/total?date=YYYY-MM-DD          total de CONTROLO, independente do detalhe
GET  /mock/erobella/health
GET  /mock/erobella/stats?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD

POST /admin/<provider>/mode/<modo>          GET /admin/state        POST /admin/reset
```

O dataset do TrafficJunky tem de propósito um **deal**, um **nome duplicado** e (no
modo `dirty_data`) uma campanha **sem correspondência**. O da Erobella tem 7 creatives
de 3 campanhas, com os dois formatos de link.

### Modos de falha (por provider)

O modo de um provider **não afeta o outro**. É isso que permite ter um DAG a verde e
outro a vermelho ao mesmo tempo.

| Modo | O que simula |
|---|---|
| `healthy` | normal |
| `http_500` | todos os endpoints do provider respondem 500 |
| `timeout` | os endpoints de **dados** demoram mais do que o timeout HTTP (o health é rápido) |
| `rate_limit` | as primeiras `fail_times` chamadas levam **429** e depois recupera |
| `schema_drift` | o provider **renomeia** um campo que consumimos (`cost` → `spend`, `cost_eur` → `spend_eur`) |
| `partial_data` | o endpoint de **detalhe** devolve só ~60 %; o **total de controlo** continua correto |
| `dirty_data` | dados que **não sabemos mapear**: uma campanha sem correspondência / um creative sem link e outro sem UUID |

```bash
curl -X POST localhost:8001/admin/trafficjunky/mode/http_500
curl -X POST localhost:8001/admin/erobella/mode/schema_drift
curl -X POST "localhost:8001/admin/trafficjunky/mode/rate_limit?fail_times=2"
curl localhost:8001/admin/state          # modo de cada provider
curl -X POST localhost:8001/admin/reset  # tudo para healthy
```

> **Isto é apenas para formação.** Um endpoint que sabota o próprio serviço, sem
> autenticação e na mesma porta do tráfego normal, **não seria implementado assim em
> produção**: usa-se chaos engineering (Toxiproxy, Chaos Mesh...) em ambientes
> isolados, com autenticação e auditoria. O estado é só em memória.

### Mock ou API real

```env
USE_MOCK_API=true      # mock local (por omissão)
USE_MOCK_API=false     # URLs e tokens do ambiente (ver .env.example)
```

A pipeline recebe um `ProviderSettings` (URL base, caminhos, token, moeda) e não sabe
qual das duas está a usar. Os tokens vêm do ambiente; o `.env.example` só tem
placeholders. **Ver [as limitações](#15-limitações-as-apis-reais).**

## 8. Airflow: dois DAGs

Dois DAGs **independentes**, com a mesma forma:

```
check_api >> extract >> validate_source >> transform >> validate_canonical >> load >> reconcile
```

`trafficjunky_daily` e `erobella_daily`. **Não há DAG factory**: de propósito. Primeiro
vê-se o que se repete; só depois se abstrai (é o assunto de um exercício).

Abre os dois ficheiros lado a lado: são quase idênticos. O que muda está **dentro** de
`providers/*.py`.

| Conceito | No DAG |
|---|---|
| **Scheduling** | `CronDataIntervalTimetable("@daily")`: uma run por dia |
| **Data interval** | a run do dia 20 processa o dia 20 e só arranca quando esse dia acaba |
| **Retries** | `retries=2`, `retry_delay=30s` (curto, só para a aula) |
| **Timeout** | HTTP (5 s) e `execution_timeout` (2 min) |
| **Catchup / backfill** | `catchup=False`; o passado reprocessa-se sob comando |
| **XCom** | só caminhos e contagens, nunca dados |
| **Idempotency** | secção 9 |

**Retry é para erros transitórios.** Um 500 ou um timeout podem passar sozinhos. Um campo
renomeado, uma campanha sem correspondência ou um total que não bate estarão lá igual
daqui a 30 segundos. Por isso `validate_source`, `validate_canonical` e `reconcile` têm
`retries=0` e falham logo.

**Duas camadas de timeout:** o do **HTTP** (`PIPELINE_HTTP_TIMEOUT_SECONDS`, 5 s: o
pedido desiste) e o da **task** (`execution_timeout`, 2 min: o Airflow mata a tentativa).

### Executar

Os DAGs começam **pausados**. Ativa-os (toggle na UI, ou):

```bash
docker compose exec airflow airflow dags unpause trafficjunky_daily
docker compose exec airflow airflow dags unpause erobella_daily

# processar um dia à escolha
docker compose exec airflow airflow dags trigger trafficjunky_daily --conf '{"date": "2026-10-20"}'
docker compose exec airflow airflow dags trigger erobella_daily     --conf '{"date": "2026-10-20"}'

# reprocessar o passado
docker compose exec airflow airflow backfill create --dag-id trafficjunky_daily \
    --from-date 2026-10-15 --to-date 2026-10-20
```

Uma run disparada à mão **não tem data interval** (no Airflow 3); `pipeline/window.py`
resolve o dia por esta ordem: `conf.date` → data interval → dia anterior.

`airflow standalone` é uma simplificação para a formação: o scheduler, a UI, o DAG
processor e o triggerer correm no mesmo container; em produção são componentes
separados. Também não há ecrã de login.

### Tasks vs Assets

> Tasks mostram o que a pipeline **faz**.
> Assets mostram quais **dados** a pipeline produz ou atualiza.

```
check_api             = trabalho (decide se avança)
extract               = trabalho
data/raw/erobella/    = dataset      → Asset  raw_erobella
validate_source       = trabalho (decisão: o contrato do provider cumpre-se?)
transform             = trabalho
data/staging/erobella/ = dataset     → Asset  canonical_erobella
validate_canonical    = trabalho (decisão)
load                  = trabalho
fact_campaign_daily   = dataset analítico → Asset  fact_campaign_daily
reconcile             = trabalho (decisão: o total bate?)
```

**Nem toda task produz dados.** `check_api`, `validate_source`, `validate_canonical` e
`reconcile` produzem estado/decisões (passa, falha), por isso **não** publicam Assets.
`extract`, `transform` e `load` produzem ou atualizam datasets, por isso declaram
`outlets=[...]`.

| Task | Asset que atualiza | URI |
|---|---|---|
| `extract` | `raw_<provider>` | `file:///opt/airflow/project/data/raw/<provider>/` |
| `transform` | `canonical_<provider>` | `file:///opt/airflow/project/data/staging/<provider>/` |
| `load` | `fact_campaign_daily` | `postgres://postgres:5432/analytics/public/fact_campaign_daily` |

```
trafficjunky_daily ───┐
                      ├──► fact_campaign_daily
erobella_daily ───────┘
```

- **Um Asset é o dataset lógico inteiro, não um dia.** Os ficheiros continuam em
  `date=YYYY-MM-DD/`; a data processada vai no `extra` de cada *asset event*.
- **`fact_campaign_daily` é um só Asset**, atualizado pelos dois DAGs.
- Isto **não** é uma medallion architecture (por isso `canonical_*` e não `silver_*`) e
  **não** liga DAGs entre si: os Assets são só lineage visível. Nenhum DAG é agendado por Assets.

`extra` de cada evento:

| Asset | `extra` |
|---|---|
| `raw_*` | `provider`, `date`, `raw_path` |
| `canonical_*` | `provider`, `date`, `staging_path`, `row_count` |
| `fact_campaign_daily` | `provider`, `date`, `inserted`, `updated` |

#### Demo

1. Ativar e executar `erobella_daily` (`--conf '{"date": "2026-10-20"}'`).
2. Abrir o DAG → grafo: as 7 tasks; só `extract`, `transform` e `load` têm Asset associado.
3. Abrir **Assets** e mostrar `raw_erobella`, `canonical_erobella` e `fact_campaign_daily`; abrir um evento e ler o `extra` (data, caminho, `row_count`, `inserted`/`updated`).
4. Executar `trafficjunky_daily` para o mesmo dia.
5. Voltar a `fact_campaign_daily`: o grafo mostra os **dois** DAGs a convergir, e o histórico de eventos tem um evento por provider.

## 9. Idempotency

> Executar a mesma carga 1, 2 ou 10 vezes deixa o sistema no mesmo estado.

O Airflow **retenta** tasks e **reprocessa** o passado; operadores clicam em *Clear*.
Sem idempotência, cada gesto duplica dados em silêncio.

**Como:** uma chave única + `INSERT ... ON CONFLICT DO UPDATE` (upsert):

```sql
INSERT INTO fact_campaign_daily (date, provider, campaign_id, source_specific_id, ...) VALUES (...)
ON CONFLICT (date, provider, campaign_id, source_specific_id)
DO UPDATE SET impressions = EXCLUDED.impressions, ..., updated_at = now();
```

Cada carga regista `inserted` e `updated`: `{'inserted': 5, 'updated': 0}` na primeira
vez, `{'inserted': 0, 'updated': 5}` nas seguintes.

### A armadilha do `NULL`

O TrafficJunky tem `source_specific_id = NULL`. **Numa unique constraint tradicional,
`NULL` nunca é igual a `NULL`**: duas linhas `(dia, 'trafficjunky', campanha, NULL)` são
consideradas *diferentes*, o `ON CONFLICT` nunca dispara e **cada recarga acrescenta as
mesmas linhas, sem nenhum erro**.

A solução é `UNIQUE NULLS NOT DISTINCT` (PostgreSQL 15+), que trata os `NULL` como
iguais. Não se usa uma string vazia como sentinela: `NULL` significa "não há" e deve
continuar a ser `NULL` (e a base de dados e o contrato recusam `''`).

### Demonstração

```bash
docker compose exec -w /opt/airflow/project airflow python -m scripts.demo_idempotency
```

```
execucao  1. INSERT         2. UPSERT + unique normal   3. UPSERT + NULLS NOT DISTINCT
----------------------------------------------------------------------------------
run 1     5 linhas          5 linhas                    5 linhas
run 2     10 linhas         10 linhas                   5 linhas
run 3     15 linhas         15 linhas                   5 linhas
```

As **mesmas** 5 linhas TrafficJunky, carregadas três vezes:

1. `INSERT` simples, sem chave: duplica.
2. **`ON CONFLICT` com uma unique normal: também duplica, e sem nenhum erro.** É a
   armadilha.
3. `NULLS NOT DISTINCT`: uma linha por campanha e dia.

O teste específico é `test_trafficjunky_row_with_null_key_is_not_duplicated`
(`tests/test_load_db.py`).

## 10. Reconciliation

> Os dados que guardámos batem certo com o que o provider diz?

```
independent API total      vs      SUM(cost) em PostgreSQL
                                   para  date + provider + currency
```

Depois do `load`, a task `reconcile` obtém o total diário **da API**, consulta
`SUM(cost)` na base de dados e compara, com `Decimal` e uma tolerância pequena
(`RECONCILE_TOLERANCE`, por omissão `0.01`; nos tickets reais é 1 unidade). Se a
diferença a ultrapassa, a task **falha**. O log mostra tudo:

```
provider=trafficjunky date=2026-10-21 currency=EUR
    api_total=528.18  db_total=343.45  difference=184.73  tolerance=0.01  status=FAIL
```

Em caso de sucesso, `difference=0.00 ... status=PASS`.

### O total tem de ser **independente**

Se o "total de controlo" fosse calculado a partir **exatamente dos mesmos rows** que a
extração, um detalhe truncado truncaria também o controlo, e a falha passava
despercebida. Por isso:

* **Erobella:** o total é a parte `by_day` da própria resposta, que é independente de
  `by_day_creative`.
* **TrafficJunky:** o mock tem um **endpoint de totais** independente do detalhe.

Para a API real, a estratégia é **configurável** (`TRAFFICJUNKY_TOTAL_STRATEGY`):

| Estratégia | Independente do detalhe? |
|---|---|
| `summary_endpoint` | **sim** |
| `refetch_stats` (voltar a pedir as stats e somar; é o que os tickets descrevem) | **não**: se o detalhe está truncado, trunca os dois. Há um teste que o mostra |

### A moeda faz parte da comparação

A API reporta a moeda do total; se difere da que a pipeline carrega, a reconciliação
**falha** em vez de comparar moedas diferentes.

### Não implementado (comportamento de produção dos tickets)

* **apagar** o dia quando a base de dados tem **mais** do que a API;
* **reprocessar em loop** até não criar documentos novos (os relatórios do provider mudam);
* **alerta no Slack** se a diferença persistir.

Estão documentados como evolução, não implementados.

## 11. Os oito cenários

Para cada cenário: pôr o(s) provider(s) num modo, disparar o DAG, ver, repor.

```bash
curl -X POST localhost:8001/admin/<provider>/mode/<modo>
docker compose exec airflow airflow dags trigger <dag> --conf '{"date": "2026-10-22"}'
#   ...observar em http://localhost:8081...
curl -X POST localhost:8001/admin/reset
```

| # | Cenário | Modo | O que vês | Tempo |
|---|---|---|---|---|
| 1 | Ambos saudáveis | `healthy` | os dois DAGs: 7 tasks a verde, `reconcile ... PASS` | ~30 s |
| 2 | TrafficJunky em 500, Erobella saudável | `http_500` (só TJ) | `trafficjunky_daily` **failed** (`check_api` 3 tentativas); `erobella_daily` **success**, **ao mesmo tempo** | ~1,5 min |
| 3 | Timeout | `timeout` | `check_api` passa (o health é rápido!); `extract` esgota o timeout de 5 s, 3 tentativas, **failed** | ~1,5 min |
| 4 | 429 que recupera | `rate_limit` | `check_api` falha 2 vezes e **passa à 3.ª**; DAG **success** | ~1 min |
| 5 | Schema drift | `schema_drift` | `extract` OK, **`validate_source` falha**: o campo (`cost` / `cost_eur`) está em falta | imediato |
| 6 | *Partial data* | `partial_data` | tudo passa **até à `reconcile`, que falha** (ver secção 12) | ~30 s |
| 7 | Dados de negócio "sujos" | `dirty_data` | linhas descartadas e registadas (`CRITICAL`); load e canonical **passam**; `reconcile` falha | ~30 s |
| 8 | O mesmo dia duas vezes | `healthy` | sem duplicação: `inserted: 0, updated: N` | ~30 s |

Pormenores que dão boa conversa:

* **2:** os dois providers têm estado independente. Um DAG a vermelho não impede o outro.
* **3:** o `/health` está verde e o `extract` falha na mesma. Um health check não prova
  que os dados estão acessíveis.
* **4:** com `fail_times=3`, os `retries=2` não chegam e o DAG falha. Experimenta.
* **5:** a API respondeu **200**, a tempo, sem erros. Só o contrato do provider o apanha.
* **7:** repara na diferença entre *rejeitar uma linha* (o transform descarta e
  continua) e *falhar a task* (o `validate_source`). A reconciliação revela o que se perdeu.
* **8:** corre o mesmo dia duas vezes e compara `SELECT count(*) FROM fact_campaign_daily`.

## 12. O momento final: *partial data*

Este é o cenário da aula.

```bash
curl -X POST localhost:8001/admin/trafficjunky/mode/partial_data
docker compose exec airflow airflow dags trigger trafficjunky_daily --conf '{"date": "2026-10-21"}'
```

O provider devolve só **parte** das campanhas no endpoint de detalhe, mas a paginação
é coerente com o que devolve (por isso o `extract` não se queixa), e o total de controlo
continua correto. O que se vê na UI do Airflow:

```
HTTP 200                       ✔
source validation              ✔  PASS
transform                      ✔  PASS
canonical validation           ✔  PASS
load                           ✔  PASS
reconcile                      ✘  FAIL
```

```
provider=trafficjunky date=2026-10-21 currency=EUR
    api_total=528.18  db_total=343.45  difference=184.73  tolerance=0.01  status=FAIL
```

> ### Operational success does not imply data correctness.

Seis tasks verdes, e faltam 184,73 € de investimento na base de dados. Se a
pipeline **acabasse no `load`**, estaria tudo verde e o Daily Control mostraria um
investimento errado, para sempre, sem ninguém dar por isso.

Experimenta também com `refetch_stats` (secção 10): o total é calculado sobre o **mesmo**
detalhe truncado, e a `reconcile` passa. Um controlo que depende da mesma fonte que
verifica não controla nada.

E agora a pergunta que abre a próxima aula:

> ### "Como saberíamos que isto aconteceu às 03:00, sem abrir manualmente o Airflow?"

## 13. Observability: a próxima aula

Não está instalada, de propósito. A aula seguinte acrescenta Prometheus, Grafana e
Blackbox Exporter. O que esta aula já deixa **preparado**:

| Pergunta | O que já existe |
|---|---|
| A fonte está bem? *(source)* | `check_api`, os modos `http_500`/`timeout`/`rate_limit` |
| O job correu? *(pipeline)* | estados das tasks, retries, duração no Airflow |
| Os dados estão bem? *(data)* | `reconcile`: `api_total`, `db_total`, `difference`, `status` por provider, dia e moeda |
| Quantas linhas se perderam? | `saved`, `merged` e `dropped` em cada `transform` |

O primeiro passo natural é **persistir o resultado da reconciliação** (por exemplo,
uma tabela `reconciliation_result(date, provider, currency, api_total, db_total,
difference, status, checked_at)`) e fazer o Grafana lê-la. Nesta versão a reconciliação
só calcula, regista no log e falha a task: não persiste histórico, para não aumentar
a complexidade.

O cenário 6 é precisamente o que a observabilidade tem de apanhar sem ninguém olhar:
uma run **com todos os passos de carga verdes e dados errados**.

## 14. Do caso real para a aula

Os tickets são reais; a aula é uma **versão pedagógica**. O que se mudou e porquê:

| Nos tickets | Nesta aula | Porquê |
|---|---|---|
| MongoDB | PostgreSQL | a stack do curso |
| S3 (`raw/<provider>/date=.../`) | `data/raw/<provider>/date=.../` | sem S3 real; mesma convenção de pastas |
| Sentry (*critical*) | `log.critical` | sem Sentry |
| Slack | só log | sem Slack |
| Voluum (`Campaign` por nome) | `dim_campaign` com seed (`data/campaigns.csv`) | sem Voluum |
| várias contas por provider | **uma conta por provider** | evitar loops por conta e `expand()` |
| 3 schedules (today / yesterday / last 7 days) | 1 diário + `conf.date` | simplicidade; o reprocessamento mostra-se com backfill |
| check de investimento só no schedule dos 7 dias | `reconcile` em **cada** run | a reconciliação é o tema da aula |
| `datetime` = dia às 00:00 UTC | coluna `date` | o grain é diário |
| chave `(datetime, campaign_id, source_specific_id)` | `(date, provider, campaign_id, source_specific_id)` | uma tabela para dois providers |
| racios do provider guardados | só métricas base + view | rácios derivam-se |
| nomes de campanha repetidos: "a mais recente" | `campaign_name` **único** | simplificação |

**Evolução de produção, documentada e não implementada:**

* **Múltiplas contas** por provider: um DAG por conta, ou *dynamic task mapping* (`expand()`).
* **Apagar o dia** quando a base de dados tem mais do que a API.
* **Reprocessar em loop** até não criar documentos novos, porque os relatórios do provider mudam.
* **Alerta no Slack** quando a diferença persiste.
* **Quarentena** de linhas rejeitadas (`rejected_records`) em vez de só as registar.
* **Os 3 schedules** (today / yesterday / last 7 days), com o check só no último.
* **Conversão cambial** quando os providers faturam em moedas diferentes.

## 15. Limitações: as APIs reais

> **Leia isto antes de usar `USE_MOCK_API=false`.**

* Os tickets (PDFs) descrevem o **comportamento** e os **campos relevantes**, mas **não
  trazem os payloads completos** das APIs reais.
* Os mocks são **representações pedagógicas inferidas**: preservam as diferenças
  estruturais que importam (lista paginada vs três partes; campanha por nome vs num link),
  não copiam o formato exato.
* Os nomes dos parâmetros (`start_date`/`end_date` da Erobella), a forma das respostas, o
  formato de `ctr`, a existência de um health endpoint e do endpoint de totais do
  TrafficJunky são **suposições** deste projeto.
* **`USE_MOCK_API=false` precisa de ser validado contra a documentação e payloads
  reais** antes de ser considerado *production-ready*. Não foi testado contra nenhuma
  API real.

## 16. Exercícios

**Airflow**
1. Muda `retries` para 0 no `check_api` e repete o cenário 4. O que muda?
2. Põe `retry_exponential_backoff=True` e calcula quanto demora o DAG a desistir no cenário 2.
3. Aumenta o timeout HTTP para 30 s e repete o cenário 3. Que timeout apanha agora o provider lento?
4. Faz um backfill de uma semana. Depois repete-o. O que muda na base de dados?
5. Põe `catchup=True`. Quantas runs aparecem? Porque é perigoso?

**Contratos e modelo**
6. Muda `extra="ignore"` para `"forbid"` em `contracts/trafficjunky.py`. Que muda se o
   provider acrescentar um campo? E num contrato canónico, faz sentido `ignore`?
7. Acrescenta um terceiro provider. O que tens de escrever (contrato de origem, módulo
   `providers/`, DAG, mock) e o que **não** precisas de tocar (`load`, `reconcile`, `validate`,
   views)? Cuidado: o enum `Provider` e o `CHECK (provider IN (...))` do `schema.sql`
   também têm de ser alargados.
8. Põe `EROBELLA_CURRENCY=USD` e corre o DAG. O que acontece na reconciliação e nas views?
9. Acrescenta `account` à chave de idempotência. O que muda no `schema.sql` e no `ON CONFLICT`?

**Idempotência**
10. Troca `UNIQUE NULLS NOT DISTINCT` por uma `UNIQUE` normal e corre o teste
    `test_trafficjunky_row_with_null_key_is_not_duplicated`. O que acontece?
11. Troca `DO UPDATE` por `DO NOTHING`. O que muda em `updated_at`? E se o provider corrigisse o `cost`?

**Reconciliação**
12. Com `TRAFFICJUNKY_TOTAL_STRATEGY=refetch_stats`, corre o cenário 6. Porque passa?
13. Persiste o resultado da reconciliação numa tabela `reconciliation_result`. Que colunas?
14. Implementa o "apagar o dia quando a base de dados tem mais do que a API". Que riscos tem?

**Evolução**
15. Elimina a duplicação entre os dois DAGs com uma *DAG factory*. O que ganhas? O que perdes?
16. Suporta uma segunda conta TrafficJunky com *dynamic task mapping* (`expand()`).
17. Calcula CPC por campanha e provider, na semana, com a view. Porque é que `AVG(cpc)` está errado?

---

## Anexo A · Arrancar, URLs e reset

**Pré-requisitos:** Docker com Compose v2. Para correr os testes no host, Python 3.11+.

### Arrancar do zero

```bash
cd aula03-airflow-providers
cp .env.example .env                 # não ponhas credenciais reais no .env.example
docker compose up -d --build         # 1.ª vez: ~2 min (build das imagens)
docker compose ps                    # os 3 serviços devem estar "running"
```

O Airflow demora ~30 s a arrancar depois dos containers estarem `running`.

### URLs

| O quê | URL |
|---|---|
| Airflow UI (sem login) | <http://localhost:8081> |
| Mock API · documentação interativa | <http://localhost:8001/docs> |
| Mock API · estado dos providers | <http://localhost:8001/admin/state> |
| PostgreSQL (analytics) | `postgresql://providers:providers@localhost:5433/analytics` |

### Ver os dados

```bash
docker compose exec postgres psql -U providers -d analytics
```
```sql
SELECT * FROM v_campaign_daily ORDER BY date DESC, provider;
SELECT * FROM v_stat_ratios ORDER BY date DESC, campaign_name, source_specific_id;
```

### Testes

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d postgres        # os testes de BD precisam dele
pytest                               # ~105 testes, poucos segundos
```

Os testes de base de dados correm num **schema temporário** (nunca tocam nas tabelas
reais) e são saltados se o PostgreSQL não estiver acessível. O cliente HTTP é substituído
pela mock API **em memória**: os testes exercitam o código real sem rede nem Docker.

### Reset

```bash
curl -X POST localhost:8001/admin/reset            # tira os providers de um modo de falha
docker compose down -v                             # apaga containers E volumes (as DUAS bases de dados)
rm -rf data/raw/* data/staging/*                   # ficheiros gerados (o .gitkeep fica)
docker compose up -d --build
```

Para repor só os dados de negócio: `TRUNCATE fact_campaign_daily` (e `DELETE FROM dim_campaign`,
que se volta a carregar sozinha na próxima run).

## Anexo B · Troubleshooting

**Disparei o DAG e a run fica `queued`.** O DAG está pausado: `airflow dags unpause <dag>`.

**`port is already allocated`.** Outra coisa usa a porta. Muda `POSTGRES_HOST_PORT`,
`MOCK_API_HOST_PORT` ou `AIRFLOW_HOST_PORT` no `.env` e `docker compose up -d`.

**Mudei o código da mock API e nada mudou.** A mock é copiada para a imagem:
`docker compose up -d --build mock-api`. O código de `providers/`, `pipeline/`, `contracts/`
e os DAGs são montados por volume e não precisam de rebuild.

**Um provider ficou num modo de falha.** `curl -X POST localhost:8001/admin/reset`.

**`reconcile` falha e não sei porquê.** Lê o log da task: mostra `api_total`, `db_total` e
`difference`. Depois vê o log do `transform` (`dropped=...`) e do `extract` (quantas linhas).

**Os testes de BD são todos saltados.** O PostgreSQL não está acessível:
`docker compose up -d postgres`. Se usas outra porta, define `TEST_DATABASE_URL`.

**O DAG não aparece.** `docker compose exec airflow airflow dags list-import-errors`.
