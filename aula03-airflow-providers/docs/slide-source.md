# Aula 03 · Fonte para os slides

> **Documento intermédio.** Não são slides: é a fonte de verdade para os criar.
> Reflete o projeto **como ficou implementado**, verificado contra o código, a base de
> dados e o Airflow em execução. Onde algo não foi implementado ou não foi executado,
> está marcado. A secção 25 lista os factos verificados e as lacunas.

Convenções deste documento:

* `código` = nome real (DAG, task, ficheiro, tabela, variável, comando).
* **[EXECUTADO]** = corri no Airflow/Docker e vi o resultado.
* **[TESTADO]** = coberto por teste automático (104 testes), não executado no Airflow.
* **[DOCUMENTADO]** = descrito, não implementado ou não executado.

---

## 1. EXECUTIVE SUMMARY

Esta aula usa dois casos reais de performance marketing, **TrafficJunky** e **Erobella**,
para ensinar Apache Airflow através de um problema realista, mas deliberadamente
simplificado: levar os dados de **investimento** (quanto se gastou por campanha e por dia)
das APIs de dois providers de tráfego para o PostgreSQL, de forma fiável.

Cada provider tem um schema completamente diferente (o TrafficJunky devolve uma linha por
campanha; a Erobella, uma linha por *creative*, com a campanha escondida num link). Cada um
tem o seu DAG (`trafficjunky_daily`, `erobella_daily`), com as mesmas 7 tasks, e ambos
convergem num **modelo canónico** (`CampaignDailyStat`) e numa única tabela de factos
(`fact_campaign_daily`).

O que entra: respostas HTTP de uma mock API determinística (ou, com `USE_MOCK_API=false`, das
APIs reais, **não validado**). O que sai: linhas idempotentes em PostgreSQL, views com CPC,
CPM e CTR recalculados, e uma **reconciliação** diária que compara o total da API com
`SUM(cost)` na base de dados.

O aluno aprende: DAGs, tasks, dependências, data intervals, retries e timeouts, *backfill* e
reprocessamento, idempotência (incluindo a armadilha do `NULL` numa chave única), dois
níveis de data contract com Pydantic, o modelo canónico, e, sobretudo, que **sucesso
operacional não implica dados corretos**. Fecha com a pergunta que abre a aula de
observabilidade: *"Como saberíamos que isto aconteceu às 03:00, sem abrir o Airflow?"*

---

## 2. THE STORY OF THE PROJECT

A aula conta uma história em dez passos. A ordem não é a dos ficheiros: é a da **necessidade**.

| # | Passo | O que o aluno vê | Porquê neste ponto |
|---|---|---|---|
| 1 | Temos uma **fonte externa** | o TrafficJunky e a sua API (mock) | há um problema concreto antes de qualquer conceito |
| 2 | **Extraímos** | `extract`: paginação, raw em disco | primeiro os dados chegam |
| 3 | **Validamos o contrato** do provider | `validate_source` | não confiamos no que recebemos |
| 4 | **Transformamos** para um modelo interno | `transform`: deals, nomes, duplicados | as regras de negócio do provider |
| 5 | **Carregamos** | `load`: upsert | os dados chegam à base de dados |
| 6 | **Reprocessamos sem duplicar** | idempotência | o Airflow retenta e reprocessa |
| 7 | **Comparamos API vs base de dados** | `reconcile` | "carregou" não é "está certo" |
| 8 | Chega um **segundo provider** | a Erobella, schema completamente diferente | agora há duas formas de ver o mesmo dado |
| 9 | Percebemos que precisamos de um **modelo canónico** | `CampaignDailyStat` | a abstração nasce de uma necessidade, não de uma ideia |
| 10 | **Quebramos a pipeline** de propósito | 8 cenários, com o `partial_data` como clímax | cada conceito só se compreende quando falha |

**Por que esta sequência funciona pedagogicamente:**

* **Um provider primeiro.** Sem generalizar, o aluno percebe o fluxo completo (extract →
  reconcile) sem ruído. Um segundo provider só faz sentido depois do primeiro.
* **O modelo canónico aparece quando dói.** Com um só provider não há nada a unificar. Ao
  chegar a Erobella, a pergunta "que registo é igual nos dois?" é natural, e a resposta
  (o canónico) tem uma razão de existir.
* **As falhas vêm depois de haver o que partir.** Cada falha mostra um conceito: retry
  (500, 429), timeout, contrato (schema drift), idempotência (mesmo dia), reconciliação
  (`partial_data`).
* **O clímax é uma falha silenciosa.** As falhas ruidosas ensinam retries; a silenciosa
  (tudo verde até à reconciliação) ensina porque a observabilidade existe.

---

## 3. ARQUITETURA GERAL

```
   TrafficJunky                              Erobella
   GET /mock/trafficjunky/stats              GET /mock/erobella/stats
   GET /mock/trafficjunky/total              (o total vem na própria resposta: by_day)
          │                                          │
          └───────────────┬──────────────────────────┘
                          ▼
         mock-api (FastAPI, :8001)   ──  ou APIs reais  (USE_MOCK_API=false, NÃO validado)
                          │
                          ▼
   ┌───────────────── Apache Airflow (:8081) ──────────────────────────────────────┐
   │   trafficjunky_daily                    erobella_daily                         │
   │   check_api ► extract ► validate_source ► transform ► validate_canonical       │
   │                                                          ► load ► reconcile    │
   └────────────────────────────────────────────────────────────────────────────────┘
        │ específico de cada provider              │ comum aos dois
        ▼                                          ▼
   providers/trafficjunky.py                  pipeline/  (validate, load, reconcile, raw, http, config)
   providers/erobella.py
   contracts/trafficjunky.py   contracts/erobella.py        ← contratos de ORIGEM (do provider)
                          │
                          ▼
              contracts/canonical.py :: CampaignDailyStat   ← contrato INTERNO (nosso)
                          │
                          ▼
          PostgreSQL (:5433) · base `analytics`
          dim_campaign ◄── fact_campaign_daily      views: v_stat_ratios, v_campaign_daily
                          │
                          ▼
              reconcile:  total da API   vs   SUM(cost) por date + provider + currency
```

| Bloco | Em 1–3 frases |
|---|---|
| **mock-api** | FastAPI com os dois providers falsos, determinísticos (mesma seed e dia dão os mesmos dados), com *fault injection* por provider. Existe para a aula não depender de APIs externas. |
| **Airflow** | Orquestra. Os DAGs só decidem a ordem, o dia, os retries e os timeouts; chamam funções Python puras. Dois DAGs independentes, com a mesma forma. |
| **providers/** | Tudo o que é específico de um provider: o pedido, as regras de transformação, o total de controlo. Um módulo por provider, sem framework genérico. |
| **contracts/ (origem)** | Pydantic descreve o que o **provider** nos envia. Ignora campos extra, exige os que consumimos. |
| **contracts/canonical.py** | O contrato **nosso**: `CampaignDailyStat`. Proíbe campos extra. É o único que a base de dados conhece. |
| **PostgreSQL** | Uma dimensão e uma fact, com chave de idempotência `UNIQUE NULLS NOT DISTINCT`. |
| **reconcile** | Compara um total **independente** da API com o que ficou na base de dados. |

---

## 4. INFRAESTRUTURA LOCAL

```
Laptop (docker compose)
 ├── airflow    (:8081)   LocalExecutor, `airflow standalone`
 ├── mock-api   (:8001)   FastAPI, estado de falha em memória
 └── postgres   (:5433)   bases: analytics + airflow
```

| Container | Imagem / build | Porta (host→container) | Responsabilidade | Porque existe |
|---|---|---|---|---|
| `postgres` | `postgres:17` | `5433→5432` | UM servidor, **duas bases**: `analytics` e `airflow` | o destino dos dados e os metadados do Airflow |
| `mock-api` | `docker/mock.Dockerfile` (`python:3.12-slim`) | `8001→8000` | os dois providers falsos + `/admin` | a aula não depende de APIs externas |
| `airflow` | `docker/airflow.Dockerfile` (`apache/airflow:3.3.2-python3.12` + pandas, psycopg, httpx) | `8081→8080` | orquestração; `command: standalone` | ver e repetir cada passo |

As portas do host (5433, 8001, 8081) são diferentes das da aula 02 (5432, 8000, 8080): as
duas aulas podem estar ligadas ao mesmo tempo.

**Duas bases de dados, dois propósitos**

| | Base `analytics` | Base `airflow` |
|---|---|---|
| Conteúdo | `dim_campaign`, `fact_campaign_daily`, views | runs, task instances, XComs |
| Quem escreve | o nosso ETL | só o Airflow |
| Variável | `DATABASE_URL` | `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` |
| Criada por | `POSTGRES_DB=analytics` | `docker/postgres-init.sql` (`CREATE DATABASE airflow`) |

**O que persiste e onde**

| O quê | Onde | Sobrevive a `docker compose stop`? | Sobrevive a `down -v`? |
|---|---|---|---|
| Dados das duas bases | volume nomeado `pgdata` | sim | **não** |
| Respostas raw | `data/raw/<provider>/date=YYYY-MM-DD/response.json` (no host, via bind mount) | sim | sim (está no disco do host) |
| Ficheiros intermédios | `data/staging/<provider>/date=YYYY-MM-DD/canonical.json` | sim | sim |
| Estado dos modos de falha | memória do `mock-api` | **não** (volta a `healthy`) | não |

**Volumes de bind:** `.` → `/opt/airflow/project` (o projeto inteiro, por isso editar DAGs
e módulos não exige *rebuild*); `./data/campaigns.csv` → `/app/data/campaigns.csv:ro` no
mock (a mesma lista que a pipeline carrega em `dim_campaign`);
`docker/postgres-init.sql` → `/docker-entrypoint-initdb.d/01-airflow-db.sql:ro`.

`airflow standalone` corre scheduler, API server/UI, DAG processor e triggerer no mesmo
container. É uma **simplificação**: em produção são componentes separados. Não há ecrã de
login (`AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS=True`).

---

## 5. AS DUAS FONTES

| | **TrafficJunky** | **Erobella** |
|---|---|---|
| Origem | stats de **campanhas** | stats de **creatives** |
| **Grain da origem** | 1 linha = 1 campanha do provider e dia | 1 linha = 1 creative e dia (`by_day_creative`) |
| Estrutura recebida | uma lista paginada: `data`, `total`, `limit`, `offset` | **três partes**: `by_day_creative`, `by_creative`, `by_day` |
| Pedido | `startDate=endDate=DD/MM/YYYY`, sem timezone, `limit`/`offset` | `start_date`, `end_date` (`YYYY-MM-DD`) |
| Paginação | sim (`PIPELINE_PAGE_SIZE=5` → 2 páginas) | não (uma resposta) |
| **Como se encontra o `campaign_id`** | pelo **nome** (`campaign_name` → `dim_campaign`) | por um **UUID dentro do `link`** do creative (cruzando `by_day_creative` e `by_creative` pelo `label`) |
| Campos relevantes | `campaign_name`, `campaign_type`, `impressions`, `clicks`, `cost` | `label`, `impressions`, `clicks`, `cost_eur`, e `link` |
| Rácios enviados (não guardados) | `ecpc`, `ecpm`, `ctr` (em %) | `ctr_pct`, `ecpm_eur` (em %) |
| **`source_specific_id`** | `NULL` | o `label` do creative |
| Moeda | não indicada no payload; `TRAFFICJUNKY_CURRENCY` (`EUR`) | no nome do campo (`cost_eur`); `EROBELLA_CURRENCY` (`EUR`) |
| **Total para a reconciliação** | endpoint à parte: `GET /mock/trafficjunky/total` | a parte `by_day` da própria resposta |
| Problemas possíveis | `deal`; campanha sem correspondência; nomes duplicados; resposta truncada | creative sem link; link sem UUID; UUID que não é campanha nossa; resposta truncada |
| Transformação | ignorar `deal` → mapear por nome → agregar duplicados | cruzar com `by_creative` → extrair UUID do link → rejeitar o que não mapeia |
| Rejeições contadas | `deals_skipped`, `unmapped_dropped`, `merged` | `no_link_dropped`, `no_campaign_id_dropped`, `unknown_campaign_dropped` |

> **Atenção:** os formatos são **representações pedagógicas inferidas** dos tickets (os PDFs
> não trazem os payloads completos). Ver secção 19.

---

## 6. SOURCE CONTRACT VS CANONICAL CONTRACT

```
 External Provider Contract          Provider Transform            Internal Canonical Contract
 (do provider, não é nosso)          (específica de cada um)       (nosso)

 TJStatsPage / TJCampaignStat   ──►  providers/trafficjunky.py ─┐
                                                                 ├──►  CampaignDailyStat
 EroResponse / EroDayCreative   ──►  providers/erobella.py     ─┘
 / EroCreative / EroDay
```

**Porque não usamos o schema do provider diretamente no warehouse**

* O schema do provider **não é nosso** e muda quando o provider quer.
* Dois providers = dois schemas. Sem um modelo interno, teríamos duas tabelas e duas
  definições de "custo por campanha".
* O warehouse deve conhecer **um** contrato estável, que nós controlamos.

**Porque cada provider tem o seu contrato de origem:** descrevem formas diferentes (lista
paginada vs três partes), e a pergunta é "o que o provider nos enviou tem a forma esperada?".

**Porque o canónico é nosso:** descreve o que **nós** queremos guardar, venha de onde vier.

| | Contrato de origem | Contrato canónico |
|---|---|---|
| Ficheiros | `contracts/trafficjunky.py`, `contracts/erobella.py` | `contracts/canonical.py` |
| Pergunta | o payload do **provider** tem a forma esperada? | o registo **transformado** respeita o **nosso** modelo? |
| Task | `validate_source` | `validate_canonical` |
| Campos extra | **`extra="ignore"`** (o provider acrescenta campos quando quer) | **`extra="forbid"`** (o modelo é nosso) |
| Campo que consumimos em falta | **erro** | erro |
| Se falha | a **task falha** | a **task falha** |

**Onde entra o Pydantic.** Em três sítios: (1) os modelos de origem; (2) o modelo canónico;
(3) `validate_payload`, que valida **tudo** (não para no primeiro erro) e resume por
`(campo, tipo de erro)`, por exemplo `data.*.cost -> missing`, o que distingue "um registo
estragado" de "o schema mudou".

**Snippets representativos**

```python
# contracts/trafficjunky.py  : o que o PROVIDER envia
class TJCampaignStat(BaseModel):
    model_config = ConfigDict(extra="ignore")
    campaign_name: Annotated[str, Field(min_length=1)]
    campaign_type: str                      # "deal" é ignorado no transform
    impressions: Count
    clicks: Count
    cost: Decimal
    ecpc: Decimal | None = None             # rácios do provider: opcionais, não guardados
```

```python
# contracts/erobella.py  : três partes, a campanha só no link
class EroCreative(BaseModel):
    model_config = ConfigDict(extra="ignore")
    label: Annotated[str, Field(min_length=1)]
    link: str | None = None                 # OPCIONAL: o transform rejeita os sem link

class EroResponse(BaseModel):
    by_day_creative: list[EroDayCreative]
    by_creative: list[EroCreative]
    by_day: list[EroDay]                    # o total do dia (controlo da reconciliação)
```

```python
# contracts/canonical.py  : o contrato INTERNO
class CampaignDailyStat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: dt.date
    provider: Provider                      # trafficjunky | erobella
    campaign_id: UUID
    source_specific_id: Annotated[str, Field(min_length=1)] | None = None
    currency: Currency                      # ^[A-Z]{3}$
    impressions: Count                      # int estrito, >= 0
    clicks: Count
    cost: Money                             # Decimal, >= 0, até 4 casas
```

---

## 7. CANONICAL MODEL

`CampaignDailyStat` (`contracts/canonical.py`). **8 campos**, só métricas **base**.

| Canonical field | Significado | TrafficJunky | Erobella |
|---|---|---|---|
| `date` | o dia | o dia da run (`startDate = endDate`) | o dia da run (`by_day_creative.date`) |
| `provider` | quem forneceu (`trafficjunky` \| `erobella`) | constante `trafficjunky` | constante `erobella` |
| `campaign_id` | **a nossa** campanha (UUID) | `campaign_name` → `dim_campaign` | UUID extraído do `link` do creative |
| `source_specific_id` | nível de detalhe opcional | **`NULL`** | o `label` do creative |
| `currency` | moeda do custo (ISO 4217) | `TRAFFICJUNKY_CURRENCY` (`EUR`) | `EROBELLA_CURRENCY` (`EUR`) |
| `impressions` | impressões | `impressions` (somadas se o nome se repete) | `impressions` |
| `clicks` | cliques | `clicks` (somados se o nome se repete) | `clicks` |
| `cost` | custo, `Decimal` | `cost` (somado se o nome se repete) | `cost_eur` |

**O que não é guardado** (recebido mas descartado): `ecpc`, `ecpm`, `ctr` (TrafficJunky);
`ctr_pct`, `ecpm_eur` (Erobella); `campaign_type` e o id do provider (só para o transform).

Duas decisões do modelo para um slide:

* **Só métricas base.** CPC, CPM e CTR derivam-se na view. Os do provider vêm arredondados a
  2 casas, em percentagem, e não se somam.
* **`currency` obrigatória.** Custos de moedas diferentes **nunca** se somam sem conversão.
  Nesta aula os dois providers estão em EUR: é uma **simplificação pedagógica**.

---

## 8. DATA MODEL / POSTGRESQL

```
 dim_campaign                         fact_campaign_daily
 ------------                         -------------------
 campaign_id    UUID  PK  ◄─────────  campaign_id          UUID  FK
 campaign_name  TEXT  UNIQUE          date                 DATE
 loaded_at, updated_at                provider             TEXT  CHECK IN ('trafficjunky','erobella')
                                      source_specific_id   TEXT  NULL permitido; '' não
 8 linhas (data/campaigns.csv)        currency             CHAR(3)
                                      impressions, clicks  BIGINT >= 0
                                      cost                 NUMERIC(14,4) >= 0
                                      loaded_at, updated_at
                                      UNIQUE NULLS NOT DISTINCT
                                        (date, provider, campaign_id, source_specific_id)
```

Tabelas: `dim_campaign`, `fact_campaign_daily`. Views: `v_stat_ratios`, `v_campaign_daily`.
Não existe mais nenhuma tabela (confirmado na base de dados).

**Grain, tal como implementado**

> **1 linha = 1 dia + 1 provider + 1 campanha + 1 `source_specific_id`**

| Provider | `source_specific_id` | Resultado |
|---|---|---|
| TrafficJunky | `NULL` | 1 linha por campanha e dia |
| Erobella | label do creative | 1 linha por **creative** e dia |

Duas fontes com grains de **origem** diferentes (campanha vs creative) convergem neste
grain comum: o que difere cabe numa **coluna opcional**.

**Views**

| View | Grain | Para quê |
|---|---|---|
| `v_stat_ratios` | o da fact | CPC, CPM e CTR por linha, com `NULLIF` |
| `v_campaign_daily` | dia + provider + campanha + **moeda** | os creatives somam-se **antes** de dividir (não é `AVG(cpc)`) |

**A chave de idempotência e o `NULL`** *(slide técnico)*

| | |
|---|---|
| **O problema** | o TrafficJunky tem `source_specific_id = NULL`, e a chave inclui essa coluna. |
| **Porque o `NULL` quebra o upsert** | numa unique constraint **tradicional**, `NULL` nunca é igual a `NULL`: duas linhas `(dia, 'trafficjunky', campanha, NULL)` são consideradas *diferentes*, o `ON CONFLICT` nunca dispara e cada recarga **duplica** as linhas, **sem nenhum erro**. |
| **Como foi resolvido** | `UNIQUE NULLS NOT DISTINCT (...)` (PostgreSQL 15+) trata os `NULL` como iguais. Não se usa string vazia como sentinela: `NULL` significa "não há". A BD (`CHECK (source_specific_id <> '')`) e o Pydantic recusam `''`. |
| **Prova** | `test_trafficjunky_row_with_null_key_is_not_duplicated` e `scripts/demo_idempotency.py` |

---

## 9. O DAG

Os dois DAGs têm **exatamente a mesma arquitetura**; só o conteúdo de `providers/*.py` muda.
Não há *DAG factory*: de propósito.

```
trafficjunky_daily:  check_api ► extract ► validate_source ► transform ► validate_canonical ► load ► reconcile
erobella_daily:      check_api ► extract ► validate_source ► transform ► validate_canonical ► load ► reconcile
                       │           │            │               │                 │           │         │
                    provider   provider     provider        provider            comum       comum    comum*
                    específico específico   específico      específico        (pipeline/) (pipeline/) (pipeline/)
                                                            * o total de controlo vem do módulo do provider
```

Configuração (igual nos dois): `schedule=CronDataIntervalTimetable("@daily", timezone="UTC")`,
`start_date=2026-10-01`, `catchup=False`, `max_active_runs=1`, `retries=2`,
`retry_delay=30 s`, `execution_timeout=2 min` (e **30 s** no `check_api`). Os DAGs são
criados **pausados**. Os imports dos módulos estão **dentro** das funções (o Airflow relê o
ficheiro a cada poucos segundos).

| Task | What it does | Input | Output (XCom: só metadados) | Retry? | Reason |
|---|---|---|---|---|---|
| `check_api` | `GET` ao health do provider; sem `*_HEALTH_PATH` regista que não há e passa | — | `{"status": "ok"}` | **2** (30 s) | 500, 429 e timeouts podem passar sozinhos |
| `extract` | pede as stats do dia, **todas as páginas** (TJ), verifica `len(linhas) == total`, guarda o **raw** | o dia (`conf.date` → data interval → dia anterior) | `provider, date, raw_path, pages, rows_fetched, currency` | **2** | falhas HTTP e timeouts são transitórios |
| `validate_source` | valida o raw contra o contrato do **provider** | `raw_path` | idem + `source_valid` | **0** | um campo em falta continua em falta daqui a 30 s |
| `transform` | as regras do provider → linhas canónicas em `data/staging/` | `raw_path` | idem + `staging_path`, `counts` | 2 (por omissão) | lê `dim_campaign`; ver nota |
| `validate_canonical` | valida cada linha contra `CampaignDailyStat` | `staging_path` | idem + `canonical_valid` | **0** | um valor impossível é determinístico |
| `load` | upsert idempotente numa transação | `staging_path` | idem + `loaded: {inserted, updated}` | 2 (por omissão) | seguro: a carga é idempotente |
| `reconcile` | total da API vs `SUM(cost)`; falha acima da tolerância | `date`, `currency` | idem + `reconciliation: {api_total, db_total, difference, status}` | **0** | uma diferença não desaparece ao retentar |

**Notas honestas (para o professor)**

* `transform` e `load` ficam com os 2 retries por omissão: acedem à base de dados. Um bug
  determinístico no transform seria retentado inutilmente; não foi tratado de propósito.
* O `reconcile` tem `retries=0`, mas o do TrafficJunky faz uma chamada HTTP (ao endpoint
  de totais). Uma falha transitória *nessa* chamada falha a run sem retry.
* O `reconcile` e o `load` têm de correr **depois** do `validate_canonical` mesmo quando
  há linhas descartadas: o descarte não falha nenhuma task.

---

## 10. AIRFLOW CONCEPTS

| Conceito | Definição (1 frase) | Onde aparece | Demo |
|---|---|---|---|
| **DAG** | o grafo de tasks e as suas regras | `with DAG(dag_id="trafficjunky_daily", ...)` | abrir os dois ficheiros lado a lado |
| **Task** | uma unidade de trabalho | 7 `PythonOperator` por DAG | UI → grafo do DAG |
| **Dependency** | uma task só arranca depois de a anterior ter sucesso | `check_api >> extract >> ... >> reconcile` | falha no `validate_source` → as seguintes `upstream_failed` |
| **Schedule** | quando o DAG corre | `CronDataIntervalTimetable("@daily", timezone="UTC")` | UI → *Schedule* |
| **Data interval** | a run é uma **fatia de tempo**, não um instante | a run do dia 20 processa o dia 20 e só arranca quando esse dia acaba | explicar com o `@daily` |
| **Manual trigger** | disparar à mão, escolhendo o dia | `--conf '{"date": "2026-10-20"}'`; `pipeline/window.py` | todos os cenários **[EXECUTADO]** |
| **Retries / retry_delay** | repetir uma task que falhou, esperando entre tentativas | `retries=2`, `retry_delay=30 s` | `http_500` e `rate_limit` **[EXECUTADO]** |
| **Timeout** | desistir de uma tentativa demorada | HTTP 5 s (`PIPELINE_HTTP_TIMEOUT_SECONDS`) e `execution_timeout` | `timeout` **[EXECUTADO]** |
| **Logs** | o que cada tentativa escreveu | UI → run → task → *Logs* | ver `reconcile ... status=FAIL` |
| **`failed`** | a task esgotou as tentativas | `check_api failed try=3` | `http_500` |
| **`upstream_failed`** | a task nunca correu porque uma anterior falhou | tudo a jusante de uma falha | qualquer cenário com falha |
| **XCom** | mensagens pequenas entre tasks | `return` das tasks; só caminhos e contagens | UI → *XCom*; o dado vai em ficheiros |
| **Catchup** | correr os dias em atraso ao ativar | `catchup=False` | **[DOCUMENTADO]** |
| **Backfill / reprocessing** | reprocessar o passado sob comando | `airflow backfill create ...`; `--conf date` | `--conf date` **[EXECUTADO]**; `backfill create` **[DOCUMENTADO]** na aula 03 (executado na aula 02) |
| **Pause / unpause** | um DAG pausado não corre | criados pausados | `airflow dags unpause <dag>` **[EXECUTADO]** |
| **`max_active_runs`** | uma run de cada vez | `max_active_runs=1` | — |
| **Idempotency** | repetir não muda o resultado | `UNIQUE NULLS NOT DISTINCT` + upsert | mesmo dia duas vezes **[EXECUTADO]** |
| **Clear task** | repetir uma task na UI | — | **[DOCUMENTADO]**, não executado na aula 03 |
| **`airflow standalone`** | tudo num só container | `command: standalone` | simplificação |

---

## 11. DATA FLOW — ONE RECORD

Dados reais gerados pelo mock (seed `42`, dia `2026-10-20`).

### TrafficJunky: `TJ PT Casino Desktop`

```
 SOURCE JSON  (data/raw/trafficjunky/date=2026-10-20/response.json, página 0)
 {"campaign_id": 5000, "campaign_name": "TJ PT Casino Desktop", "campaign_type": "standard",
  "impressions": 24269, "clicks": 543, "cost": 162.28, "ecpc": 0.3, "ecpm": 6.69, "ctr": 2.24}
        │
        ▼  validate_source   (TJStatsPage → TJCampaignStat; cost vira Decimal('162.28'))
 VALIDATED SOURCE OBJECT
 TJCampaignStat(campaign_name='TJ PT Casino Desktop', campaign_type='standard',
                impressions=24269, clicks=543, cost=Decimal('162.28'), ecpc=Decimal('0.3'), ...)
        │
        ▼  transform   (não é deal; nome → dim_campaign; sem duplicados)
 CANONICAL RECORD  (data/staging/trafficjunky/date=2026-10-20/canonical.json)
 {"date": "2026-10-20", "provider": "trafficjunky",
  "campaign_id": "0b6116c0-9ed5-5398-8df0-72911f86933f", "source_specific_id": null,
  "currency": "EUR", "impressions": 24269, "clicks": 543, "cost": "162.2800"}
        │
        ▼  load   (upsert)
 POSTGRESQL ROW  (fact_campaign_daily)
 2026-10-20 | trafficjunky | 0b6116c0-… | NULL | EUR | 24269 | 543 | 162.2800
        │
        ▼  v_stat_ratios
 cpc = 0.2989     cpm = 6.6867     ctr = 0.022374
```

Repara: o provider reportou `ecpc = 0.3` e `ctr = 2.24` (arredondados, em %); recalculados
a partir das métricas base são `0.2989` e `0.022374` (fração). **Não guardamos os do provider.**

### TrafficJunky: duas campanhas com o mesmo nome (agregação)

```
 TJ DE Loans (id 5002):  impressions 15343   clicks 412   cost 146.39   ecpc 0.36
 TJ DE Loans (id 5003):  impressions 15590   clicks 386   cost 100.83   ecpc 0.26
        │  transform: mesmo campaign_id → agrega (merged=1), soma as métricas BASE
        ▼
 1 linha:  impressions 30933   clicks 798   cost 247.2200   → cpc recalculado = 0.3098
```

Os rácios de uma só das campanhas (por exemplo `ecpc = 0.36`) já não descrevem a linha somada.

### Erobella: `pt-casino-a`

```
 SOURCE JSON  (data/raw/erobella/date=2026-10-20/response.json)
 by_day_creative: {"date": "2026-10-20", "label": "pt-casino-a", "impressions": 20605,
                   "clicks": 504, "ctr_pct": 2.45, "cost_eur": 112.0, "ecpm_eur": 5.44}
        │            (o desempenho NÃO traz campanha)
        ▼  creative lookup  (cruzar com by_creative pelo label)
 by_creative:     {"label": "pt-casino-a", "partner": "EroPartner",
                   "link": "https://trk.example.test/85e7e1f3-64a2-50c6-a56a-5f6fa9915c19?creative=pt-casino-a"}
        │
        ▼  extract_campaign_id(link)  →  UUID('85e7e1f3-64a2-50c6-a56a-5f6fa9915c19')
           (existe em dim_campaign: "EB PT Casino Native")
 CANONICAL RECORD
 {"date": "2026-10-20", "provider": "erobella", "campaign_id": "85e7e1f3-64a2-50c6-a56a-5f6fa9915c19",
  "source_specific_id": "pt-casino-a", "currency": "EUR", "impressions": 20605, "clicks": 504,
  "cost": "112.0000"}
        │
        ▼  load (upsert)
 POSTGRESQL ROW
 2026-10-20 | erobella | 85e7e1f3-… | pt-casino-a | EUR | 20605 | 504 | 112.0000
        │
        ▼  v_stat_ratios
 cpc = 0.2222     cpm = 5.4356     ctr = 0.024460
```

---

## 12. RAW DATA

| | |
|---|---|
| **Porquê guardar o raw** | a resposta tal como chegou: inspecionar um erro e reprocessar sem voltar a chamar a API |
| **Onde** | `data/raw/<provider>/date=YYYY-MM-DD/response.json` |
| **Formato** | JSON válido `{"pages": [<página 1>, <página 2>, ...]}` |
| **Como a data entra no path** | a pasta é determinada pelo **dia** (`date=2026-10-20`), **não** pela hora a que a run arrancou |
| **Re-correr o mesmo dia** | **sobrescreve** o ficheiro (escrita atómica: tmp + rename), nunca acumula lixo |
| **Preserva a precisão** | cada página é inserida como texto, sem `json.loads/dumps`: `12.30` continua `12.30`. A leitura usa `parse_float=Decimal` |

Paths reais existentes:

```
data/raw/trafficjunky/date=2026-10-20/response.json     (2 páginas: 5 + 2 linhas)
data/raw/erobella/date=2026-10-20/response.json         (1 página, 3 partes)
data/staging/trafficjunky/date=2026-10-20/canonical.json
```

O TrafficJunky tem 2 páginas porque `PIPELINE_PAGE_SIZE=5` e a mock devolve 7 linhas.

**Porque isto NÃO é uma camada *bronze* (medallion):** não há camadas, nem tabelas bronze,
silver e gold, nem uma arquitetura em camadas. É só um ficheiro com a resposta tal como
chegou, mais um de intermédio, ambos para debug e reprocessamento. A tabela de destino
recebe diretamente o modelo canónico. Nos tickets reais isto vai para S3
(`raw/<provider>/date=.../`); aqui, para disco local.

Os dados **não** viajam por XCom: o XCom leva só o caminho (`raw_path`, `staging_path`).

---

## 13. IDEMPOTENCY

**O problema**

```
 mesmo dia (2026-10-20)
   run 1  ──►  5 linhas
   run 2  ──►  (retry? Clear task? backfill? re-trigger manual?)
   run 3  ──►
```

| | run 1 | run 2 | run 3 |
|---|---|---|---|
| **INSERT simples, sem chave** | 5 | 10 | 15 |
| **ON CONFLICT + unique normal** (NULL ≠ NULL) | 5 | 10 | 15 *(sem nenhum erro!)* |
| **ON CONFLICT + `NULLS NOT DISTINCT`** | 5 | 5 | 5 |

(Saída real do `scripts/demo_idempotency.py`: as **mesmas** 5 linhas TrafficJunky em três
execuções.)

**A chave real**

```sql
CONSTRAINT uq_campaign_daily
    UNIQUE NULLS NOT DISTINCT (date, provider, campaign_id, source_specific_id)
```

```sql
INSERT INTO fact_campaign_daily (...) VALUES (...)
ON CONFLICT (date, provider, campaign_id, source_specific_id)
DO UPDATE SET ..., updated_at = now()
RETURNING (xmax = 0) AS inserted        -- distingue inseridas de atualizadas
```

Cada carga devolve `{'inserted': 5, 'updated': 0}` na primeira vez e `{'inserted': 0, 'updated': 5}`
nas seguintes. `loaded_at` não muda; `updated_at` muda.

**Porque importa especificamente em Airflow**

* **retry**: o Airflow volta a correr uma task que falhou a meio;
* **re-run manual**: `airflow dags trigger ... --conf '{"date": ...}'` sobre um dia já carregado;
* **clear task** *(UI)*: operadores repetem uma task;
* **backfill / reprocessing**: o passado reprocessa-se sob comando.

Sem idempotência, cada um destes gestos duplica dados em silêncio.

**Demo e testes (comandos reais)**

```bash
docker compose exec -w /opt/airflow/project airflow python -m scripts.demo_idempotency
docker compose exec -w /opt/airflow/project airflow python -m scripts.demo_idempotency --cleanup
.venv/bin/pytest tests/test_load_db.py -k null_key        # test_trafficjunky_row_with_null_key_is_not_duplicated
```

A demo usa tabelas próprias (`demo_naive`, `demo_unique_plain`, `demo_nulls_not_distinct`) e
**não toca** em `fact_campaign_daily`. *Nota:* correr o mesmo dia duas vezes no DAG
**[EXECUTADO]** nos dois providers (contagens inalteradas, `reconcile ... PASS`).

---

## 14. RECONCILIATION

> **Os dados que guardámos batem certo com o que o provider diz?**

```
   detail API  ──►  pipeline (extract → transform → load)  ──►  database  ──►  SUM(cost)
                                                                                  │
   summary API  (independente do detalhe) ────────────────────────────────────────┤
                                                                                  ▼
                                                                          compare totals
                                                                                  │
                                  api_total · db_total · difference · tolerance · PASS / FAIL
```

**Fonte do total independente**

| Provider | De onde vem o `api_total` |
|---|---|
| TrafficJunky | `GET /mock/trafficjunky/total?date=...` (endpoint à parte; soma das campanhas **não-deal**) |
| Erobella | `by_day.cost_eur` da própria resposta (independente de `by_day_creative`) |

**Comparação:** `api_total` vs `SELECT COALESCE(SUM(cost), 0) FROM fact_campaign_daily WHERE date = ... AND provider = ... AND currency = ...`,
em `Decimal`, com tolerância `RECONCILE_TOLERANCE` (por omissão `0.01`; nos tickets reais é 1
unidade). Se a moeda da API difere da carregada, **falha** em vez de comparar.

**Log real (sucesso)**

```
provider=trafficjunky date=2026-10-20 currency=EUR
    api_total=651.17  db_total=651.17  difference=0.00  tolerance=0.01  status=PASS
```

**Exemplo numérico real**: `2026-10-20`, TrafficJunky, saudável. O mock devolve 7 linhas:

| Linha | cost |
|---|---|
| TJ PT Casino Desktop | 162.28 |
| TJ ES Sports Mobile | 74.58 |
| TJ DE Loans (id 5002) | 146.39 |
| TJ DE Loans (id 5003) | 100.83 |
| TJ FR Dating | 114.26 |
| TJ BR Keto | 52.83 |
| TJ Private Deal Q4 (**deal**, ignorado) | ~~226.41~~ |

`162.28 + 74.58 + 247.22 + 114.26 + 52.83 = 651.17` = `api_total` = `db_total`. → **PASS**.

**Porque a reconciliação é diferente de:**

| | Pergunta que responde | O que **não** vê |
|---|---|---|
| **HTTP health check** (`check_api`) | o provider está vivo? | dados incompletos com HTTP 200 |
| **Pydantic** (`validate_source`/`validate_canonical`) | cada **registo** tem a forma certa? | registos que **faltam** |
| **SQL constraint** (PK, FK, `CHECK`) | cada **linha** é válida? | linhas que **não existem** |
| **Reconciliação** | o **total** bate com uma fonte independente? | (é a rede de segurança dos anteriores) |

Os três primeiros verificam o que **existe**. Só a reconciliação deteta o que **falta**.

**Não implementado** (comportamento de produção dos tickets) **[DOCUMENTADO]**: apagar o dia
quando a BD tem mais do que a API; reprocessar em loop até não criar documentos novos;
alerta no Slack.

---

## 15. FAULT SCENARIOS

Sete modos implementados em `mock_api/faults.py`, **por provider** (o estado de um não afeta
o outro), mais o cenário "mesmo dia duas vezes".

| Scenario | Provider | Failure | Task | Retry? | Final result |
|---|---|---|---|---|---|
| `healthy` | ambos | nenhuma | — | — | 7 tasks verdes, `reconcile ... PASS` **[EXECUTADO]** |
| `http_500` | TrafficJunky **[EXECUTADO]**; Erobella **[TESTADO]** | todos os endpoints do provider respondem 500 | `check_api` | **sim**: 3 tentativas (1 + 2 retries) | DAG `failed`; resto `upstream_failed` |
| `timeout` | ambos **[EXECUTADO]** | os endpoints de **dados** demoram `MOCK_TIMEOUT_DELAY_SECONDS` (20 s) > timeout HTTP (5 s); o health é rápido | `extract` (o `check_api` **passa**) | **sim**: 3 tentativas | `extract failed try=3` |
| `rate_limit` | ambos **[EXECUTADO]** | as primeiras `fail_times` (2) chamadas levam **429** (`Retry-After: 5`) e depois recupera | `check_api` | **sim** | falha 2× e **passa à 3.ª**; DAG `success` |
| `schema_drift` | ambos **[EXECUTADO]** | o provider renomeia um campo que consumimos: TJ `cost`→`spend`; Erobella `cost_eur`→`spend_eur` | `validate_source` | **não** (`retries=0`) | `failed` à 1.ª tentativa |
| `partial_data` | ambos **[EXECUTADO]** | o endpoint de **detalhe** devolve ~60 %; o total de controlo continua correto | **`reconcile`** | não | tudo passa **até à `reconcile`, que falha** |
| `dirty_data` | ambos **[EXECUTADO]** | TJ: uma campanha sem correspondência; Erobella: um creative sem link e outro sem UUID | `transform` descarta (`CRITICAL`); **`reconcile`** falha | não | load e canonical **passam**; `reconcile` falha |
| mesmo dia 2× | ambos **[EXECUTADO]** | — | — | — | sem duplicação; `reconcile ... PASS` |

**O que cada cenário ensina**

| Cenário | O que é alterado | O que o Airflow vê | Onde falha | Conceito |
|---|---|---|---|---|
| `http_500` | o provider devolve 500 | 3 tentativas em `check_api`, depois `failed` | `check_api` | **retry** para erros transitórios; **independência** entre DAGs |
| `timeout` | os dados demoram mais do que o timeout | `check_api` verde, `extract` falha 3× | `extract` | **timeout**; um health check não prova que os dados estão acessíveis |
| `rate_limit` | 429 nas primeiras chamadas | `check_api failed try=1`, `try=2`, sucesso na 3.ª | `check_api` | **retries que recuperam**; `fail_times=3` esgota-os |
| `schema_drift` | um campo muda de nome | `extract` OK; `validate_source` falha logo | `validate_source` | **contrato**; erro **determinístico** não se retenta |
| `partial_data` | o detalhe vem truncado, o total não | **tudo verde até `reconcile`** | `reconcile` | **sucesso operacional ≠ dados corretos** |
| `dirty_data` | dados que não sabemos mapear | `transform` verde com `CRITICAL`; `reconcile` falha | `reconcile` | **rejeitar uma linha ≠ falhar a task**; a reconciliação revela a perda |
| mesmo dia 2× | — | duas runs `success` | — | **idempotência** |

**Números reais da reconciliação nos modos de falha**

| Provider | Dia | Modo | `api_total` | `db_total` | `difference` | Resultado |
|---|---|---|---|---|---|---|
| trafficjunky | 2026-10-21 | `partial_data` | 528.18 | 343.45 | 184.73 | FAIL |
| trafficjunky | 2026-10-22 | `dirty_data` | 606.25 | 493.33 | 112.92 | FAIL |
| erobella | 2026-10-24 | `partial_data` | 1049.20 | 592.71 | 456.49 | FAIL |
| erobella | 2026-10-24 | `dirty_data` | 1170.07 | 1049.20 | 120.87 | FAIL |

---

## 16. THE MOST IMPORTANT DEMOS

Preparação (uma vez):

```bash
cd aula03-airflow-providers
docker compose up -d --build
docker compose exec airflow airflow dags unpause trafficjunky_daily
docker compose exec airflow airflow dags unpause erobella_daily
# UI: http://localhost:8081      Mock: http://localhost:8001/docs      Estado: http://localhost:8001/admin/state
```

Ordem pedagógica: **caminho feliz → retry que recupera → retry que esgota → erro
determinístico → idempotência → linha descartada → falha silenciosa (herói)**.

### DEMO 1 — Healthy, os dois DAGs
* **Goal:** mostrar a forma comum (7 tasks) e dois providers diferentes a dar o mesmo resultado.
* **Setup:** `curl -X POST localhost:8001/admin/reset`
* **Airflow action:**
  ```bash
  docker compose exec airflow airflow dags trigger trafficjunky_daily --conf '{"date": "2026-10-20"}'
  docker compose exec airflow airflow dags trigger erobella_daily     --conf '{"date": "2026-10-20"}'
  ```
* **Expected:** 7 tasks verdes nos dois; `reconcile ... status=PASS` (`651.17` e `595.02`).
* **Explain:** os DAGs são quase iguais; o que muda está dentro de `providers/*.py`.

### DEMO 2 — Rate limit (429) que recupera
* **Goal:** mostrar **retry** a funcionar.
* **Setup:** `curl -X POST "localhost:8001/admin/trafficjunky/mode/rate_limit?fail_times=2"`
* **Airflow action:** `airflow dags trigger trafficjunky_daily --conf '{"date": "2026-10-22"}'`
* **Expected:** `check_api` falha 2× (`try=1`, `try=2`) e **passa à 3.ª** (`try=3`); DAG `success`. ~1 min.
* **Explain:** retry resolve falhas **transitórias**. Com `fail_times=3` os `retries=2` não chegam.

### DEMO 3 — HTTP 500 num provider, o outro saudável
* **Goal:** retries esgotados e **independência** entre providers.
* **Setup:** `curl -X POST localhost:8001/admin/trafficjunky/mode/http_500`
* **Airflow action:** disparar **os dois** DAGs para o mesmo dia.
* **Expected:** `trafficjunky_daily` **failed** (`check_api` 3 tentativas; resto `upstream_failed`);
  `erobella_daily` **success**, **ao mesmo tempo**. ~1,5 min.
* **Explain:** o estado de falha é por provider; um DAG a vermelho não impede o outro.

### DEMO 4 — Schema drift
* **Goal:** erro **determinístico** e contrato do provider.
* **Setup:** `curl -X POST localhost:8001/admin/erobella/mode/schema_drift`
* **Airflow action:** `airflow dags trigger erobella_daily --conf '{"date": "2026-10-24"}'`
* **Expected:** `check_api` e `extract` verdes; **`validate_source` falha à 1.ª tentativa** (`retries=0`);
  o resto `upstream_failed`. Imediato.
* **Explain:** a API respondeu 200. Retentar não adianta: o campo continua renomeado.

### DEMO 5 — Idempotência (a armadilha do NULL)
* **Goal:** repetir sem duplicar, e o `NULL` na chave.
* **Setup:** `curl -X POST localhost:8001/admin/reset`
* **Command:** `docker compose exec -w /opt/airflow/project airflow python -m scripts.demo_idempotency`
* **Expected:** `5/10/15` (INSERT), `5/10/15` (upsert + unique normal), `5/5/5` (`NULLS NOT DISTINCT`).
* **Explain:** o caso 2 duplica **sem erro**. Depois, no DAG: o mesmo dia duas vezes, contagem inalterada.

### DEMO 6 — Dirty data
* **Goal:** **rejeitar uma linha ≠ falhar a task.**
* **Setup:** `curl -X POST localhost:8001/admin/trafficjunky/mode/dirty_data`
* **Airflow action:** `airflow dags trigger trafficjunky_daily --conf '{"date": "2026-10-22"}'`
* **Expected:** `transform` verde, com `CRITICAL ... sem correspondencia ... ['TJ Unmapped Campaign Test']` e
  `fetched=8 deals_skipped=1 dropped=1 merged=1 saved=5`; `load` verde; **`reconcile` falha** (606.25 vs 493.33).
* **Explain:** descartar tem um custo (112.92 € de investimento não chegou à BD); a reconciliação revela-o.

### DEMO 7 — Partial data (HERO): ver secção 17.

---

## 17. PARTIAL DATA — HERO DEMO

```
 HTTP 200                        ✔   o provider respondeu, a tempo
        ↓
 source contract valid           ✔   validate_source PASS
        ↓
 transform valid                 ✔   transform PASS
        ↓
 canonical contract valid        ✔   validate_canonical PASS
        ↓
 load success                    ✔   load PASS (carregou o que recebeu)
        ↓
 reconciliation FAIL             ✘   reconcile FAIL
```

**Setup e comandos reais**

```bash
curl -X POST localhost:8001/admin/trafficjunky/mode/partial_data
docker compose exec airflow airflow dags trigger trafficjunky_daily --conf '{"date": "2026-10-21"}'
# ...mostrar na UI (http://localhost:8081): 6 tasks verdes, a última vermelha
curl -X POST localhost:8001/admin/reset
```

**Passo a passo**

1. **O que muda:** o endpoint de **detalhe** devolve só ~60 % das campanhas (5 de 7). O `total`
   da paginação é **coerente** com o que devolve, por isso o `extract` **não se queixa**.
2. **Porque nada falha antes:** o payload tem a forma certa (contrato), as linhas que chegaram
   são válidas (canónico), e a carga é correta **para o que recebeu**.
3. **O que o `reconcile` vê:** o total de controlo é independente do detalhe e continua
   completo.
   ```
   provider=trafficjunky date=2026-10-21 currency=EUR
       api_total=528.18  db_total=343.45  difference=184.73  tolerance=0.01  status=FAIL
   ```
4. **O que teria acontecido sem `reconcile`:** a pipeline acabaria no `load`, **tudo verde**, e
   a base de dados teria **184,73 € a menos**, para sempre, sem ninguém dar por isso.

> # "Operational success does not imply data correctness."

**Um controlo que depende da mesma fonte que verifica não controla nada.** Com
`TRAFFICJUNKY_TOTAL_STRATEGY=refetch_stats`, o total é calculado sobre o **mesmo** detalhe
truncado e a `reconcile` passa. *(Coberto pelo teste
`test_refetch_strategy_is_NOT_independent_of_the_detail` **[TESTADO]**; não foi executado no Airflow.)*

**Porque prepara a observabilidade:** esta falha **não aparece** em nenhum dos sinais
operacionais (estado das tasks, HTTP, duração) até à última task. Se a pipeline não tivesse
`reconcile`, **nenhuma** métrica de job ou de API a veria. É o argumento para observar também
os **dados**. E fecha com a pergunta:

> ### "Como saberíamos que isto aconteceu às 03:00, sem abrir manualmente o Airflow?"

---

## 18. OBSERVABILITY BRIDGE

> **Nada disto está implementado.** É o roadmap descrito no README (secção 13) para a aula
> seguinte (Prometheus, Grafana, Blackbox Exporter).

**Sinais que o sistema deveria expor**

| Tipo | Sinal | De onde já sai hoje |
|---|---|---|
| **PIPELINE** | DAG success / failure | estado da run no Airflow |
| | retries (ex.: `check_api` passou à 3.ª) | `try_number` das task instances |
| | duração das tasks | Airflow |
| **SOURCE** | disponibilidade | `check_api`; modos `http_500`/`timeout` |
| | HTTP status (200, 429, 500) | resposta do provider; `Retry-After` registado em log |
| | latência | `response.elapsed` no log do `check_api` (só TrafficJunky) |
| **DATA** | rows extraídas | `rows_fetched` / `pages` (metadados do `extract`) |
| | rows rejeitadas | `dropped`, `merged`, `deals_skipped` no `transform` (log e XCom) |
| | **reconciliation difference** | `api_total`, `db_total`, `difference`, `status` por provider/dia/moeda |
| | freshness | **[DOCUMENTADO]**, não existe como sinal |

**Arquitetura futura**

```
 Mock/API real ──► Blackbox Exporter ──┐   (disponibilidade, latência, HTTP status)
 Airflow ────────► métricas ───────────┼──► Prometheus ──► Grafana
 Data checks ────► métricas de dados ──┘   (reconcile: difference, rows, dropped)
```

O primeiro passo natural, **não implementado nesta aula** (a tabela
`reconciliation_result(date, provider, currency, api_total, db_total, difference, status,
checked_at)` fica como proposta): persistir o resultado da reconciliação, para o Grafana o
ler. Hoje a reconciliação só calcula, regista no log e falha a task.

A aula 02 tem um roadmap de observabilidade mais detalhado (`../aula02-airflow-tracking/docs/observability-roadmap.md`).
A aula 03 **não** tem um documento próprio de observabilidade: só a secção 13 do README.

---

## 19. REAL SYSTEM VS CLASSROOM VERSION

| Production case | Classroom project | Why simplified |
|---|---|---|
| MongoDB (`CampaignTrafficSourceData`) | PostgreSQL (`fact_campaign_daily`) | a stack do curso |
| S3 (`raw/<provider>/date=.../`) | `data/raw/<provider>/date=.../response.json` | sem S3 real; mesma convenção de pastas |
| Sentry (nível *critical*) | `log.critical` | sem Sentry |
| Slack (alerta de investimento em falta) | só log + falha da task `reconcile` | sem Slack |
| Voluum (`Campaign`, match por nome, "a mais recente") | `dim_campaign` carregada de `data/campaigns.csv`; `campaign_name` **UNIQUE** | sem Voluum |
| várias contas por provider (`trafficjunkynewaccount`) | **uma conta por provider** | evitar loops por conta e `expand()` |
| 3 schedules (today / yesterday / last 7 days) | **1** diário + `--conf date` | simplicidade |
| check de investimento só no schedule dos 7 dias | `reconcile` em **cada** run | a reconciliação é o tema da aula |
| apagar o dia se a BD tem mais do que a API | não existe | ficou como comportamento documentado |
| reprocessamento automático em loop | **manual** (`--conf date`) | idem |
| chave `(datetime, campaign_id, source_specific_id)` | `(date, provider, campaign_id, source_specific_id)` | uma tabela para dois providers |
| `datetime` = dia às 00:00 UTC | coluna `date` | o grain é diário |
| rácios do provider guardados | só métricas base + views | rácios derivam-se |
| moedas variadas | **ambos em EUR** | mostrar `currency` sem conversão cambial |
| tolerância de 1 unidade | `0.01` (configurável) | os dados sintéticos batem exatamente |
| APIs reais | **mock** determinística; `USE_MOCK_API=false` não testado | a aula não pode depender de APIs externas |
| total de controlo do TrafficJunky: voltar a pedir as stats e somar | endpoint de totais no mock (`summary_endpoint`); `refetch_stats` também implementado | demonstrar a falha de `partial_data` |
| `airflow standalone`, sem login | idem | simplificação de formação |
| `/admin/<provider>/mode/<modo>` | só para formação | em produção usa-se chaos engineering isolado |

**Limitação a dizer em voz alta:** os PDFs descrevem **comportamento e campos relevantes**, não
os payloads completos. Os mocks são representações pedagógicas **inferidas**. Os nomes dos
parâmetros da Erobella (`start_date`/`end_date`), as respostas, o formato de `ctr`, a existência
de um health endpoint e do endpoint de totais do TrafficJunky são **suposições**.
`USE_MOCK_API=false` precisa de ser validado contra a documentação real antes de ser
considerado pronto para produção.

---

## 20. KEY DESIGN DECISIONS

| # | Decision | Reason | Production evolution |
|---|---|---|---|
| 1 | **Dois DAGs, sem DAG factory** | ver primeiro o que se repete (os dois ficheiros são quase idênticos); só depois abstrair | uma *DAG factory* parametrizada por provider (exercício 15) |
| 2 | **Lógica de negócio fora do Airflow** (`providers/`, `pipeline/`) | testável sem Airflow; "o Airflow orquestra, não transforma" | manter; os módulos podem tornar-se um pacote |
| 3 | **Só metadados por XCom** | o XCom vive na BD do Airflow; serve para mensagens pequenas | object storage (S3) para os ficheiros |
| 4 | **`Decimal` para dinheiro** (`parse_float=Decimal`, `NUMERIC(14,4)`) | sem artefactos de `float` (`0.1 + 0.2`); o raw preserva o texto | manter |
| 5 | **Contrato de origem tolerante, canónico estrito** (`ignore` vs `forbid`) | o provider não é nosso; o modelo é | versionar contratos, com regras de compatibilidade |
| 6 | **Rejeição suave no `transform`; falha dura nas validações** | uma campanha sem mapeamento é um dado válido fora do domínio; um schema partido não | quarentena (`rejected_records`) com limiar |
| 7 | **Modelo canónico só com métricas base**; rácios na view | os do provider vêm arredondados, em %, e não se somam | manter; mais métricas derivadas nas views |
| 8 | **`currency` obrigatória** | um custo sem moeda não tem significado | conversão cambial e tabela de taxas |
| 9 | **`UNIQUE NULLS NOT DISTINCT`** | `NULL ≠ NULL` numa unique normal duplica o TrafficJunky sem erro | manter; documentar a regra de chaves com colunas opcionais |
| 10 | **Total de controlo independente do detalhe** | um controlo sobre a mesma fonte truncada não controla nada | persistir resultados e alertar; apagar/reprocessar o dia |
| 11 | **`retries=0` nos passos determinísticos** (`validate_source`, `validate_canonical`, `reconcile`) | um erro determinístico só atrasa a falha ao ser retentado | backoff exponencial, `retry_delay` em minutos |
| 12 | **Mocks antes das APIs reais** (`USE_MOCK_API`) | a aula não depende de nada externo; determinismo | validar contra a documentação e payloads reais |
| 13 | **Uma conta por provider** | evitar loops e `expand()` na primeira versão | *dynamic task mapping* ou um DAG por conta |

---

## 21. WHAT NOT TO TEACH IN THIS CLASS

| Fora de âmbito | Porquê fica para depois |
|---|---|
| *Dynamic task mapping* / `expand()` | só faz falta com várias contas; é uma evolução (exercício 16) |
| *DAG factory* | abstrair só depois de ver a repetição (exercício 15) |
| Kubernetes, Celery | `airflow standalone` + `LocalExecutor` bastam para ensinar conceitos |
| Spark, dbt, Kafka | não são necessários; o foco é orquestração e contratos |
| Great Expectations | o Pydantic e o `reconcile` cobrem o objetivo |
| S3 real, MongoDB, Sentry, Slack | substituídos por disco, PostgreSQL e logs |
| Medallion / bronze-silver-gold | o raw é só debug, não uma arquitetura em camadas |
| Quarentena (`rejected_records`) | as linhas rejeitadas só se registam; evolução documentada |
| Conversão cambial | os dois providers estão em EUR; a moeda no modelo basta |
| Os 3 schedules (today / yesterday / last 7 days) | um schedule diário chega para os conceitos |
| Apagar o dia / reprocessar em loop / alerta Slack | comportamento de produção, documentado e não implementado |
| Persistir resultados da reconciliação | é o primeiro passo da aula de observabilidade |
| Implementação de Prometheus, Grafana, Blackbox Exporter | é a aula seguinte |

---

## 22. SLIDE CANDIDATES

35 slides, a contar uma história: **problema → primeiro provider → pipeline → Airflow →
falhas → segundo provider → modelo canónico → idempotência → reconciliação → observabilidade**.

| # | Title | Main idea | Type |
|---|---|---|---|
| 1 | Provider Pipelines | dois providers reais, um modelo interno | CONCEPT |
| 2 | O problema | dados de investimento têm de chegar todos os dias, de forma fiável | CONCEPT |
| 3 | Dois tickets reais, uma aula | ENG-387 (TrafficJunky) e ENG-392 (Erobella), simplificados | CONCEPT |
| 4 | O que pode correr mal | cai, fica lento, limita, muda um campo, responde incompleto, corre duas vezes | DISCUSSION |
| 5 | Arquitetura | mock/API → Airflow → contratos → PostgreSQL → reconcile | ARCHITECTURE |
| 6 | A stack local | 3 containers, 2 bases de dados | ARCHITECTURE |
| 7 | Primeiro provider: TrafficJunky | uma linha por campanha, paginada, sem timezone | CONCEPT |
| 8 | As regras do TrafficJunky | ignorar deals, mapear por nome, agregar duplicados | CODE |
| 9 | O DAG: 7 tasks | `check_api` → … → `reconcile` | ARCHITECTURE |
| 10 | O Airflow orquestra, não transforma | os DAGs só chamam funções Python puras | CONCEPT |
| 11 | Conceitos de Airflow | DAG, task, dependency, data interval, retries, timeout | CONCEPT |
| 12 | Guardar o que chegou | raw por dia; só caminhos no XCom; não é *bronze* | CODE |
| 13 | O contrato do provider | Pydantic: o payload tem a forma esperada? | CODE |
| 14 | Rejeitar uma linha ≠ falhar a task | `validate_source` falha; o `transform` descarta e regista | DISCUSSION |
| 15 | DEMO: caminho feliz | 7 tasks verdes, `reconcile PASS` | DEMO |
| 16 | DEMO: 429 que recupera | retry a funcionar (`try=3`) | DEMO |
| 17 | DEMO: HTTP 500 | retries esgotados; o outro provider continua a verde | DEMO |
| 18 | DEMO: schema drift | erro determinístico, sem retry | DEMO |
| 19 | Retries resolvem falhas transitórias | o que se retenta e o que não | RECAP |
| 20 | Chegou um segundo provider | o schema da Erobella é completamente diferente | CONCEPT |
| 21 | Creative → link → UUID da campanha | a campanha escondida num link | CODE |
| 22 | O mesmo DAG, regras diferentes | dois DAGs quase idênticos; muda `providers/*.py` | ARCHITECTURE |
| 23 | Porque precisamos de um modelo canónico | a abstração nasce de uma necessidade | CONCEPT |
| 24 | Contrato do provider ≠ contrato interno | `extra="ignore"` vs `extra="forbid"` | CODE |
| 25 | Modelo de dados e grain | 1 dia + 1 provider + 1 campanha + 1 `source_specific_id` | ARCHITECTURE |
| 26 | Idempotência | mesmo dia × 3 sem duplicar | CONCEPT |
| 27 | A armadilha do NULL | `NULL ≠ NULL`; `NULLS NOT DISTINCT` | CODE |
| 28 | DEMO: dirty data | linhas descartadas, `reconcile` revela a perda | DEMO |
| 29 | Reconciliação | total independente da API vs `SUM(cost)` | CONCEPT |
| 30 | **DEMO HERO: partial data** | tudo verde até à `reconcile` | DEMO |
| 31 | Operational success ≠ data correctness | a frase da aula | CONCEPT |
| 32 | Como saberíamos às 03:00? | a pergunta que abre a observabilidade | DISCUSSION |
| 33 | A ponte para a observabilidade | pipeline, source e data; Prometheus + Grafana | ARCHITECTURE |
| 34 | Caso real vs aula | o que foi simplificado e porquê | CONCEPT |
| 35 | Recap | as mensagens-chave | RECAP |

---

## 23. HERO DIAGRAMS

### 1. Arquitetura geral
**Objetivo:** mostrar o sistema completo numa imagem. **Elementos:** 2 providers, mock-api, Airflow, `providers/`, contratos, PostgreSQL, reconcile.
```
 TrafficJunky ┐                                                       ┌► dim_campaign
              ├► mock-api / API real ► Airflow ► providers/ ► canonical ► PostgreSQL
 Erobella     ┘          :8001          :8081     (específico)  contract    :5433  └► fact_campaign_daily
                                                                                          │
                                                          API total  ───────────►  reconcile ◄─ SUM(cost)
```

### 2. Duas APIs → modelo canónico
**Objetivo:** a ideia central. **Elementos:** dois schemas distintos, duas transformações, um modelo.
```
 TrafficJunky                              Erobella
 ┌───────────────────────┐                 ┌───────────────────────────┐
 │ data[]  (por campanha)│                 │ by_day_creative[] (creative)│
 │ campaign_name         │                 │ by_creative[] → link        │
 │ cost, clicks, impr.   │                 │ by_day[] (total)            │
 └──────────┬────────────┘                 └──────────────┬─────────────┘
   deals ✗ · nome→campanha · agrega           label→link→UUID · sem link ✗
            └──────────────────┬───────────────────────────┘
                               ▼
                    CampaignDailyStat
        date · provider · campaign_id · source_specific_id · currency · impressions · clicks · cost
```

### 3. O DAG
**Objetivo:** a forma comum e quem é específico. **Elementos:** 7 tasks, retries, provider vs comum.
```
 check_api ─► extract ─► validate_source ─► transform ─► validate_canonical ─► load ─► reconcile
 retries 2    retries 2   retries 0          retries 2    retries 0              retries 2  retries 0
 └───── específico do provider ──────────────────────┘    └──────────── comum (pipeline/) ──────────┘
```

### 4. TrafficJunky mapping
**Objetivo:** as 3 regras do provider. **Elementos:** 7 linhas → 5 linhas, com números reais.
```
 7 linhas do provider                      deals ✗            nome → dim_campaign        agrega duplicados
 PT Casino   162.28   ─────────────────────────────────────────────────────────────────►  PT Casino   162.28
 ES Sports    74.58   ─────────────────────────────────────────────────────────────────►  ES Sports    74.58
 DE Loans    146.39 ┐
 DE Loans    100.83 ┴─────────────────────────────────────────────────────────────────►  DE Loans   247.22
 FR Dating   114.26   ─────────────────────────────────────────────────────────────────►  FR Dating   114.26
 BR Keto      52.83   ─────────────────────────────────────────────────────────────────►  BR Keto      52.83
 Private Deal 226.41  ✗ (deal)                                                      total = 651.17
```

### 5. Erobella: creative → link → UUID
**Objetivo:** o único passo realmente novo. **Elementos:** duas partes da resposta, o link, o UUID, a dimensão.
```
 by_day_creative                by_creative                               dim_campaign
 label: pt-casino-a   ─label─►  label: pt-casino-a                        85e7e1f3-… │ EB PT Casino Native
 cost_eur: 112.0                link: https://trk…/85e7e1f3-64a2-…?creative=pt-casino-a
                                                │ extract_campaign_id(link)
                                                ▼
                                    UUID 85e7e1f3-64a2-50c6-a56a-5f6fa9915c19 ──► campaign_id
 formatos:  …/<uuid>?creative=x      ou      …/click?vcid=<uuid>&…   (vcid ganha)
 sem link · link sem UUID · UUID desconhecido  ──►  descartado + CRITICAL
```

### 6. Idempotência
**Objetivo:** o antes/depois e a armadilha. **Elementos:** 3 execuções, 3 estratégias, linhas.
```
              run 1    run 2    run 3
 INSERT         5       10       15      ✗ duplica
 UPSERT +       5       10       15      ✗ duplica SEM ERRO   (NULL ≠ NULL)
  UNIQUE normal
 UPSERT +       5        5        5      ✔ UNIQUE NULLS NOT DISTINCT
  NULLS NOT DISTINCT         (date, provider, campaign_id, source_specific_id)
```

### 7. Reconciliação
**Objetivo:** dois caminhos independentes que se comparam. **Elementos:** detalhe, base de dados, total, tolerância.
```
 detail API ─► extract ─► transform ─► load ─► PostgreSQL ─► SUM(cost) = 343.45 ─┐
                                                                                  ├► difference = 184.73
 summary API ─────────────────────────────────────► api_total = 528.18 ──────────┘     tolerance 0.01
                                                                                        ► FAIL
```

### 8. Observabilidade futura
**Objetivo:** a ponte para a aula seguinte *(não implementado)*. **Elementos:** 3 fontes de sinais, Prometheus, Grafana.
```
 SOURCE    mock/API ─► Blackbox Exporter ─┐   disponibilidade · latência · HTTP status
 PIPELINE  Airflow ─► métricas ───────────┼─► Prometheus ─► Grafana ─► alerta "às 03:00"
 DATA      reconcile · rows · dropped ────┘   difference · rows_fetched · dropped
```

---

## 24. KEY MESSAGES

1. **"Airflow orchestrates the pipeline. It is not the pipeline."**
2. **"Provider contracts are external. The canonical contract is ours."**
3. **"A canonical model is born from a need, not from an abstraction."**
4. **"Retries solve transient failures, not deterministic bugs."**
5. **"HTTP 200 does not mean correct data."**
6. **"Reprocessing requires idempotency."**
7. **"In a unique key, NULL is not equal to NULL."**
8. **"Rejecting a row is not the same as failing a task."**
9. **"A control that reads the same source it checks controls nothing."**
10. **"Costs in different currencies are never added."**
11. **"Operational success does not imply data correctness."**
12. **"How would we know at 03:00, without opening Airflow?"**

---

## 25. ACCURACY CHECK

### Factos verificados no código

| Item | Valor verificado |
|---|---|
| DAGs | `trafficjunky_daily`, `erobella_daily` (`airflow dags list`) |
| Tasks (iguais nos dois) | `check_api`, `extract`, `validate_source`, `transform`, `validate_canonical`, `load`, `reconcile` (`airflow tasks list`) |
| Schedule | `CronDataIntervalTimetable("@daily", timezone="UTC")`, `start_date=2026-10-01`, `catchup=False`, `max_active_runs=1` |
| Retries | `retries=2`, `retry_delay=30 s`, `execution_timeout=2 min`; `check_api` 30 s; `retries=0` em `validate_source`, `validate_canonical`, `reconcile` |
| Tags | `["formacao", "aula03", "<provider>"]` |
| Containers | `postgres` (`postgres:17`, `5433→5432`), `mock-api` (`8001→8000`), `airflow` (`8081→8080`) |
| URLs | Airflow `http://localhost:8081`; mock `http://localhost:8001/docs`, `/admin/state`; PG `postgresql://providers:providers@localhost:5433/analytics` |
| Volume | `pgdata` (nomeado); binds: `.:/opt/airflow/project`, `./data/campaigns.csv:/app/data/campaigns.csv:ro`, `docker/postgres-init.sql` |
| Imagens | mock: `python:3.12-slim`; airflow: `apache/airflow:3.3.2-python3.12` |
| Variáveis (`.env.example`) | `USE_MOCK_API`, `MOCK_API_BASE_URL`, `MOCK_SEED`, `MOCK_TIMEOUT_DELAY_SECONDS`, `DATABASE_URL`, `POSTGRES_USER/PASSWORD/DB/HOST_PORT`, `MOCK_API_HOST_PORT`, `AIRFLOW_HOST_PORT`, `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN`, `TRAFFICJUNKY_{BASE_URL,BEARER_TOKEN,STATS_PATH,HEALTH_PATH,TOTAL_STRATEGY,TOTAL_PATH,CURRENCY}`, `EROBELLA_{BASE_URL,API_TOKEN,STATS_PATH,HEALTH_PATH,CURRENCY}`, `PIPELINE_HTTP_TIMEOUT_SECONDS` (5), `PIPELINE_PAGE_SIZE` (5), `RECONCILE_TOLERANCE` (0.01), `AIRFLOW__CORE__*` |
| Tabelas / views | `dim_campaign`, `fact_campaign_daily`; `v_stat_ratios`, `v_campaign_daily` (confirmado com `information_schema`) |
| Chave única | `uq_campaign_daily` = `UNIQUE NULLS NOT DISTINCT (date, provider, campaign_id, source_specific_id)` (confirmado com `pg_get_constraintdef`) |
| Modos de falha | `healthy`, `http_500`, `timeout`, `rate_limit`, `schema_drift`, `partial_data`, `dirty_data` |
| Endpoints do mock | `/mock/trafficjunky/{health,stats,total}`, `/mock/erobella/{health,stats}`, `/admin/state`, `/admin/reset`, `/admin/<provider>/mode/<modo>` |
| Paths | `data/raw/<provider>/date=YYYY-MM-DD/response.json`; `data/staging/<provider>/date=YYYY-MM-DD/canonical.json` |
| Contratos | `contracts/{trafficjunky,erobella,canonical}.py`; modelos `TJCampaignStat`, `TJStatsPage`, `TJTotal`, `EroDayCreative`, `EroCreative`, `EroDay`, `EroResponse`, `CampaignDailyStat` |
| Comandos | `airflow dags unpause\|trigger <dag> [--conf '{"date": ...}']`; `curl -X POST localhost:8001/admin/<provider>/mode/<modo>`; `python -m scripts.demo_idempotency [--cleanup]` |
| Dados do mock | TJ: 7 linhas/dia (5 campanhas, `TJ DE Loans` duas vezes, 1 deal); `dirty_data` → 8. Erobella: 7 creatives de 3 campanhas; `dirty_data` → 9. `dim_campaign`: 8 linhas |
| Testes | 104 passam (`tests/`: analytics 5, canonical 4, config 5, erobella 19, load_db 11, mock_erobella 10, mock_trafficjunky 15, trafficjunky 23) |

### Cenários executados no Airflow real

Executados: `healthy` (ambos), `http_500` (**só TrafficJunky**), `timeout`, `rate_limit`,
`schema_drift`, `partial_data`, `dirty_data` (todos nos **dois** providers), mesmo dia duas
vezes (ambos), e a **independência** (TrafficJunky em 500 enquanto a Erobella termina com sucesso).

### DOCUMENTED, NOT IMPLEMENTED

* **`reconciliation_result`** (tabela de histórico): proposta no README §13; não existe.
* **Persistência de qualquer sinal de observabilidade**, Prometheus, Grafana, Blackbox: não existem.
* **Apagar o dia, reprocessar em loop, alerta Slack, quarentena, conversão cambial, três schedules, várias contas, DAG factory, `expand()`**: descritos como evolução; não implementados.
* **`airflow backfill create`** e **"Clear task"** na UI: descritos no README e usados nos
  materiais, mas **não executados** na aula 03 (o backfill foi executado na aula 02).
* **`scripts/demo_idempotency.py` dentro do container** (`docker compose exec -w /opt/airflow/project airflow python -m scripts.demo_idempotency`): a saída `5/10/15` vs `5/5/5` é real, mas foi obtida a correr o script **no host** (venv, `DATABASE_URL` para `localhost:5433`); a invocação via `docker compose exec` não foi executada na aula 03.
* **`TRAFFICJUNKY_TOTAL_STRATEGY=refetch_stats`** no Airflow: implementado e **testado** (teste automático), não executado no Airflow.
* **`USE_MOCK_API=false`**: implementado na configuração, **nunca testado** contra APIs reais.
* **Freshness** como sinal: mencionado como futuro; não existe.
* **`http_500` na Erobella** no Airflow: só coberto por teste automático.

### IMPLEMENTED, NOT DOCUMENTED (no README)

* O **`transform` cria o schema** (`load.fetch_campaign_mapping`) se for a 1.ª run numa BD nova (corrige a ordem: o transform corre antes do load).
* O **upsert não apaga**: uma linha que o provider deixa de devolver **permanece** na tabela. Um dia re-corrido atualiza, mas nunca remove. (Relevante para `partial_data` seguido de re-execução saudável: as linhas em falta são repostas, mas linhas antigas nunca saem.)
* Contagens extra no `transform` da Erobella: `other_days_skipped` (a resposta pode trazer vários dias) e `unknown_campaign_dropped` (UUID válido que não é campanha nossa); `merged` existe nos contadores mas é sempre `0`.
* O **`extract` do TrafficJunky levanta `ExtractError`** se o `total` muda a meio da paginação ou se `len(linhas) != total`; se a resposta nem tem `data`/`total`, guarda o raw e deixa o `validate_source` explicar.
* **Limites do mock:** o TrafficJunky exige `startDate == endDate`; a Erobella aceita no máximo 7 dias; `limit` do TrafficJunky: 1–1000 (por omissão 50).
* O **`reconcile` falha se a moeda da API difere** da carregada (o README menciona-o; o comportamento está testado).
* **`transform` e `load` com 2 retries** (por omissão) e **`reconcile` com `retries=0`** mesmo quando o TrafficJunky faz nele uma chamada HTTP (ver nota na secção 9).
* O **`check_api` só regista latência** no TrafficJunky; no da Erobella não.

### Imprecisões do README corrigidas durante esta verificação

* `check_api` descrito como `GET /health` → corrigido: é o health do provider (`/mock/<provider>/health`), ou nada se `*_HEALTH_PATH` está vazio.
* Exercício 7 dizia que **não** era preciso tocar no modelo nem na base de dados para acrescentar um provider → corrigido: o enum `Provider` e o `CHECK (provider IN (...))` do `schema.sql` têm de ser alargados.
