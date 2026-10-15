# Data catalog · Tracking Pipeline

Inventário de tudo o que a base de dados `analytics` contém: o que cada tabela
representa, o que cada coluna significa, de onde vem e que transformação sofre.
Serve também de **resumo do projeto**, pensado como material de partida para os
slides (ver secção 9).

> Todos os dados são **100 % sintéticos**, gerados por uma API fictícia com seed.
> A estrutura segue a de uma plataforma de tracking real
> ([data-structure-reference.md](../data-structure-reference.md)).
> Documentos relacionados: [data-model.md](data-model.md) (porquê do modelo),
> [data-contract.md](data-contract.md) (regras de entrada),
> [observability-roadmap.md](observability-roadmap.md) (próxima fase).

---

## 1. Resumo do projeto

**Objetivo.** Uma pipeline de dados pequena, de ponta a ponta, que ensina
conceitos (modelação dimensional, data contracts, ETL, orquestração, retries,
idempotência, qualidade de dados) e depois a parte de propósito para mostrar como
cada conceito a protege.

**Stack.** Python · Pandas · FastAPI · Pydantic · Apache Airflow · PostgreSQL ·
Docker Compose. (Sem dbt, Spark, medallion, Kafka, Celery nem Kubernetes.)

**Fluxo.**

```
Synthetic Tracking API  ──►  Apache Airflow  ──►  PostgreSQL (analytics)  ──►  views analíticas
   (producer, FastAPI)        check_api
                              extract            (ficheiros JSON temporários)
                              validate           (Pydantic = data contract)
                              transform          (Pandas)
                              load_dimensions    (upsert)
                              load_facts         (upsert)
                              quality_check      (SQL)
```

**Ambiente.** 3 containers: `postgres` (duas bases: `analytics` e `airflow`),
`api` (porta 8000) e `airflow` (porta 8080, modo `standalone`).

**Volume de dados (por dia).** ≈ 170 conversões · ≈ 190 linhas de custo horário ·
6 linhas de daily control · 8 campanhas (6 ativas, 2 pausadas).

---

## 2. Fontes de dados

Na realidade os dados vivem em sistemas diferentes. A API sintética expõe-os num
só serviço, gerados de forma **coerente** entre si.

| Fonte real | Conteúdo | Aparece aqui como |
|---|---|---|
| Mongo · `Conversion` | uma conversão por documento | `fact_conversions` |
| Mongo · `CampaignTrafficSourceData` | custo, clicks e impressions por hora | `fact_campaign_costs` |
| Postgres · `DailyControl` | agregado diário por campanha (pode ser editado à mão) | `fact_daily_control` |
| Postgres · `Campaign`, `TrafficSource`, `Workspace` | entidades de gestão | `dim_campaign`, `dim_traffic_source`, `dim_workspace` |
| Voluum · `Offer` | ofertas e rede de afiliação | `dim_offer` |

Endpoints da API:

| Endpoint | Dataset | Janela temporal sobre |
|---|---|---|
| `/workspaces` · `/traffic-sources` · `/campaigns` · `/offers` | dimensões (sempre completas) | |
| `/conversions` | `fact_conversions` | `postback_timestamp` |
| `/campaign-costs` | `fact_campaign_costs` | `datetime` |
| `/daily-control` | `fact_daily_control` | `date` |

---

## 3. Visão geral das tabelas

| Tabela | Tipo | Grain (1 linha =) | Chave primária | Linhas/dia |
|---|---|---|---|---|
| `dim_workspace` | dimensão | 1 workspace | `workspace_id` | estática (2) |
| `dim_traffic_source` | dimensão | 1 fonte de tráfego | `traffic_source_id` | estática (6) |
| `dim_campaign` | dimensão | 1 campanha | `campaign_id` | estática (8) |
| `dim_offer` | dimensão | 1 oferta | `offer_id` | estática (7) |
| `fact_conversions` | fact (evento) | **1 conversão** (um postback) | `(click_id, conversion_type_id, postback_timestamp)` | ≈ 170 |
| `fact_campaign_costs` | fact (periódica, horária) | **1 campanha × 1 hora × 1 `investment_provider`** | `(datetime, campaign_id, investment_provider)` | ≈ 190 |
| `fact_daily_control` | fact (periódica, diária) | **1 campanha × 1 dia** | `(date, campaign_id)` | 6 |

Todas as tabelas têm também `loaded_at` (primeira vez que a linha foi carregada;
não muda) e `updated_at` (última vez que foi recarregada; muda em cada upsert).
Não são mostradas nas tabelas de colunas abaixo.

### Relações (foreign keys)

```
dim_campaign.traffic_source_id      ──► dim_traffic_source
dim_campaign.workspace_id           ──► dim_workspace
fact_conversions.campaign_id        ──► dim_campaign
fact_conversions.traffic_source_id  ──► dim_traffic_source
fact_conversions.offer_id           ──► dim_offer
fact_campaign_costs.campaign_id     ──► dim_campaign
fact_daily_control.campaign_id      ──► dim_campaign
```

---

## 4. Dimensões

### `dim_workspace`
Equipa ou conta a que as campanhas pertencem. SCD tipo 1.

| Coluna | Tipo | Nulo? | Descrição | Origem |
|---|---|---|---|---|
| `workspace_id` | TEXT (UUID) | não | Identificador do workspace. **PK** | `Workspace.id` |
| `name` | TEXT | não | Nome do workspace | `Workspace.name` |

### `dim_traffic_source`
Plataforma onde o tráfego é comprado.

| Coluna | Tipo | Nulo? | Descrição | Origem |
|---|---|---|---|---|
| `traffic_source_id` | TEXT (UUID) | não | Identificador da fonte. **PK** | `TrafficSource.id` |
| `name` | TEXT | não | Nome (ExoClick, TrafficStars...) | `TrafficSource.name` |
| `currency_code` | CHAR(3) | não | Moeda em que a fonte fatura (ISO 4217) | `TrafficSource.currency` |
| `deleted` | BOOLEAN | não | *Soft delete*: a fonte existe mas já não está ativa. Mantém-se porque as facts históricas a referenciam | `TrafficSource.deleted` |

### `dim_campaign`
Campanha de tráfego. Hierarquia da origem: Workspace → TrafficSource → Campaign.

| Coluna | Tipo | Nulo? | Descrição | Origem |
|---|---|---|---|---|
| `campaign_id` | TEXT (UUID) | não | Identificador da campanha. **PK** | `Campaign.campaignId` |
| `name` | TEXT | não | Nome da campanha | `Campaign.name` |
| `geo` | CHAR(2) | não | País-alvo (ISO 3166-1 alpha-2) ou `WW` (worldwide) | `Campaign.geo` |
| `traffic_source_id` | TEXT | não | Fonte de tráfego. **FK** → `dim_traffic_source` | `Campaign.traffic_source` |
| `workspace_id` | TEXT | não | Workspace dono. **FK** → `dim_workspace` | `Campaign.workspace` |
| `is_paused` | BOOLEAN | não | Campanha pausada (sem tráfego) | `Campaign.is_paused` |
| `created` | TIMESTAMPTZ | não | Quando a campanha foi criada (UTC) | `Campaign.created` |

### `dim_offer`
Oferta (produto) à qual as conversões se referem. A rede de afiliação vive aqui
como atributos, sem dimensão própria.

| Coluna | Tipo | Nulo? | Descrição | Origem |
|---|---|---|---|---|
| `offer_id` | TEXT (UUID) | não | Identificador da oferta. **PK** | `Offer.id` |
| `name` | TEXT | não | Nome da oferta | `Offer.name` |
| `country_code` | CHAR(2) | **sim** | País da oferta. `NULL` = oferta global | `Offer.country.code` |
| `affiliate_network_id` | TEXT (UUID) | não | Rede de afiliação que paga a oferta | `Offer.affiliateNetwork.id` |
| `affiliate_network_name` | TEXT | não | Nome da rede | `AffiliateNetwork.name` |
| `payout` | NUMERIC(12,4) | não | Valor pago por conversão, na moeda da oferta (`>= 0`) | `Offer.payout` |
| `currency_code` | CHAR(3) | não | Moeda do `payout` | `Offer.currencyCode` |
| `deleted` | BOOLEAN | não | *Soft delete* | `Offer.deleted` |

---

## 5. Facts

### `fact_conversions`
**Grain: 1 linha = 1 conversão (um postback).** Não existe `conversion_id` na
origem; a chave é composta porque um mesmo click pode ter várias conversões
(tipos diferentes, momentos diferentes).

| Coluna | Tipo | Nulo? | Descrição | Origem / transformação |
|---|---|---|---|---|
| `click_id` | TEXT | não | Identificador do click (32 hex). **PK (1/3)** | `Conversion.clickId` |
| `conversion_type_id` | INTEGER | não | Tipo de conversão (1 = principal, 2 = secundária...), `>= 1`. **PK (2/3)** | `Conversion.conversionTypeId` |
| `postback_timestamp` | TIMESTAMPTZ | não | Quando a conversão nos foi reportada (UTC). **PK (3/3)**. É a coluna da **janela de extração** | `Conversion.postbackTimestamp` → UTC |
| `visit_timestamp` | TIMESTAMPTZ | não | Quando o utilizador clicou (UTC) | `Conversion.visitTimestamp` → UTC |
| `visit_date` | DATE | não | Dia UTC da visita. É a data dos **relatórios** | **calculada** no `transform` a partir de `visit_timestamp` |
| `campaign_id` | TEXT | não | **FK** → `dim_campaign` | `Conversion.campaignId` |
| `traffic_source_id` | TEXT | não | **FK** → `dim_traffic_source`. Deve coincidir com a da campanha | `Conversion.trafficSourceId` |
| `offer_id` | TEXT | não | **FK** → `dim_offer` | `Conversion.offerId` |
| `country_code` | CHAR(2) | não | País do visitante (ISO-2, maiúsculas) | `Conversion.countryCode` → maiúsculas |
| `revenue` | NUMERIC(14,4) | não | Receita em **USD** (`>= 0`). Métrica **aditiva** | `Conversion.revenue` |
| `revenue_original_currency` | NUMERIC(14,4) | não | Receita na moeda da oferta (`>= 0`) | `Conversion.revenueInOriginalCurrency` |

Notas: duas datas, dois usos (extrai-se por `postback_timestamp`, reporta-se por
`visit_date`). Não se guardam `cost`, `profit` nem `roi` por conversão, embora
existam na origem: são derivadas.

### `fact_campaign_costs`
**Grain: 1 linha = 1 campanha × 1 hora × 1 `investment_provider`.** É aqui que
vivem os **clicks e as impressions**: na origem só chegam agregados por hora.

| Coluna | Tipo | Nulo? | Descrição | Origem / transformação |
|---|---|---|---|---|
| `datetime` | TIMESTAMPTZ | não | Início da hora (minutos e segundos a zero). **PK (1/3)**. Janela de extração | `CampaignTrafficSourceData.datetime` → UTC |
| `cost_date` | DATE | não | Dia UTC da hora. Data dos relatórios | **calculada** a partir de `datetime` |
| `campaign_id` | TEXT | não | **PK (2/3)**. **FK** → `dim_campaign` | `CampaignTrafficSourceData.campaign_id` |
| `investment_provider` | TEXT | não | Quem financiou o tráfego (16 valores possíveis: `exoclick`, `trafficstars`, `pushground`, ...). **PK (3/3)** | `investment_provider` → minúsculas |
| `cost` | NUMERIC(14,4) | não | Custo em **USD** (`>= 0`). Métrica **aditiva** | `cost` |
| `clicks` | BIGINT | **sim** | Clicks nessa hora. `NULL` = o provider não reporta | `clicks` |
| `impressions` | BIGINT | **sim** | Impressões nessa hora. `NULL` = o provider não reporta | `impressions` |

Notas: **`NULL` não é `0`**. Os providers `pushground` e `reactiveclicks` não
reportam impressions. Uma campanha pode ter 2 providers na mesma hora (2 linhas).

### `fact_daily_control`
**Grain: 1 linha = 1 campanha × 1 dia.** Agregado que vem de **outro sistema**
(backoffice). Não é derivado dos eventos que carregamos: é uma segunda fonte
sobre os mesmos números, e por isso serve para **reconciliar**.

| Coluna | Tipo | Nulo? | Descrição | Origem / transformação |
|---|---|---|---|---|
| `date` | DATE | não | Dia (UTC). **PK (1/2)**. Janela de extração | `DailyControl.date` |
| `campaign_id` | TEXT | não | **PK (2/2)**. **FK** → `dim_campaign` | `DailyControl.campaign` |
| `revenue` | NUMERIC(12,2) | não | Receita do dia (`>= 0`), arredondada a 2 casas | `DailyControl.revenue` |
| `investment` | NUMERIC(12,2) | não | Investimento do dia (`>= 0`) | `DailyControl.investment` |
| `is_manual` | BOOLEAN | não | `true` = alguém escreveu estes números à mão; podem não bater com os eventos | `DailyControl.is_manual` |

---

## 6. Camada analítica (views)

Aqui, e só aqui, calculam-se as métricas derivadas.

| View | Grain | Para quê |
|---|---|---|
| `v_campaign_daily` | 1 campanha × 1 dia | análise principal: todas as métricas |
| `v_traffic_source_daily` | 1 fonte de tráfego × 1 dia | comparar fontes |
| `v_offer_daily` | 1 oferta × 1 dia | só conversões e receita (o custo **não tem oferta**) |
| `v_reconciliation_daily` | 1 campanha × 1 dia do daily control | eventos vs daily control (usada pelo `quality_check`) |

Colunas comuns de `v_campaign_daily` e `v_traffic_source_daily`:
`report_date`, `clicks`, `impressions`, `conversions`, `cost`, `revenue` (aditivas) e
`cpc`, `cpm`, `ctr`, `cr`, `cpa`, `epc`, `roas`, `profit`, `roi` (derivadas).

---

## 7. Glossário de métricas

**Aditivas** (guardadas nas facts; podem ser somadas por qualquer dimensão):

| Métrica | Origem |
|---|---|
| `cost` | `fact_campaign_costs.cost` |
| `clicks` | `fact_campaign_costs.clicks` |
| `impressions` | `fact_campaign_costs.impressions` |
| `revenue` | `fact_conversions.revenue` |
| `conversions` | `count(*)` de `fact_conversions` |

**Derivadas** (calculadas nas views; **nunca** guardadas por linha):

| Métrica | Fórmula | Significado |
|---|---|---|
| CPC | `cost / clicks` | quanto custa cada click |
| CPM | `cost / impressions × 1000` | custo por mil impressões |
| CTR | `clicks / impressions` | fração de impressões que gera click |
| CR | `conversions / clicks` | conversion rate |
| CPA | `cost / conversions` | quanto custa cada conversão |
| EPC | `revenue / clicks` | receita por click |
| ROAS | `revenue / cost` | receita por unidade gasta |
| profit | `revenue - cost` | resultado |
| ROI | `profit / cost` | retorno sobre o investimento |

**Regras de cálculo:**
* **Soma primeiro, divide depois.** O ROAS da semana não é a média dos ROAS diários.
* **`NULLIF(x, 0)`** em todas as divisões: um dia sem conversões tem CPA `NULL`, não erro.
* **Nulos não são zeros.** O CTR e o CPM só usam as linhas que reportam impressions.
* **Fan-out.** As facts têm grains diferentes; agregam-se separadamente antes de se juntarem.
* **Datas.** O custo conta no dia da sua hora (`cost_date`); a conversão no dia da visita (`visit_date`).

---

## 8. Linhagem e qualidade

### Linhagem (de onde vem cada coisa)

```
API /conversions     ─► raw_conversions.json     ─► validate ─► transform ─► transformed_conversions.csv     ─► fact_conversions
API /campaign-costs  ─► raw_campaign_costs.json  ─► validate ─► transform ─► transformed_campaign_costs.csv  ─► fact_campaign_costs
API /daily-control   ─► raw_daily_control.json   ─► validate ─► transform ─► transformed_daily_control.csv   ─► fact_daily_control
API /campaigns ...   ─► (idem)                                                                               ─► dim_*
                                                                                    fact_* + dim_*  ─► v_campaign_daily, v_traffic_source_daily, v_offer_daily
                                                                                    fact_* + fact_daily_control ─► v_reconciliation_daily ─► quality_check
```

Os ficheiros intermédiários ficam em `data/staging/<janela>/`. Só os **caminhos**
viajam entre tasks (XCom), nunca os dados.

### Regras de qualidade por camada

| Camada | Quem verifica | O quê |
|---|---|---|
| Contrato (entrada) | task `validate` (Pydantic) | schema; campos obrigatórios e opcionais; tipos (UUID, IDs estritos); enums (16 providers); `cost`/`revenue` `>= 0`; `country_code` com 2 letras maiúsculas; timestamps com timezone; `datetime` do custo em hora certa |
| Base de dados | constraints | PKs compostas; FKs; `CHECK (>= 0)`; `NOT NULL` |
| Conjunto de dados | task `quality_check` (SQL) | row count > 0 · freshness (última hora de custo a < 6 h do fim da janela) · chaves únicas · FKs válidas · `postback_timestamp >= visit_timestamp` · fonte da conversão == fonte da campanha · **reconciliação** com o daily control (tolerância 0,05, exceto `is_manual`) |

### Como cada tabela é carregada

Todas por **upsert** (`INSERT … ON CONFLICT (chave inteira) DO UPDATE`), numa
transação por passo (`load_dimensions`, `load_facts`). Correr a mesma janela 1, 2
ou 10 vezes dá o mesmo resultado (**idempotência**). Cada carga regista
`{'inserted': N, 'updated': M}`.

---

## 9. Material para os slides

### Estrutura sugerida

| # | Bloco | Mensagem | Visual sugerido |
|---|---|---|---|
| 1 | O problema | os dados têm de chegar todos os dias, de forma fiável; na vida real tudo falha | lista de 5 falhas reais |
| 2 | Arquitetura | 3 containers; **duas bases de dados**, dois propósitos | diagrama do fluxo (secção 1) + tabela `analytics` vs `airflow` |
| 3 | O domínio | campanha → tráfego → conversão; e um segundo sistema (daily control) | ciclo em 3 passos |
| 4 | Modelo dimensional | 4 dimensões, 3 facts | diagrama de relações (secção 3) |
| 5 | **Grain** | a decisão central; 3 grains diferentes | tabela de grains |
| 6 | Chaves | não há ID por linha → chaves compostas; escolher a chave é escolher o grain | exemplo do click com 2 conversões |
| 7 | Métricas | aditivas vs derivadas; soma primeiro, divide depois | tabela da secção 7 + caso `AVG(roas)` vs `sum/sum` |
| 8 | Data contract | API = producer, pipeline = consumer, Pydantic = contrato | tabela de erros reais |
| 9 | Producer vs consumer validation | só o consumer apanha o `schema_drift` | diagrama de duas validações |
| 10 | Airflow | DAG, tasks, data interval, retries, timeout, catchup, backfill | DAG de 7 tasks |
| 11 | Falhas ao vivo | 7 cenários; retry só serve para erros transitórios | tabela de cenários + capturas da UI |
| 12 | Idempotência | PK composta + ON CONFLICT; ingénuo vs idempotente | 516 vs 172 linhas; receita 13 595 vs 4 532 USD |
| 13 | Data quality | `validate` vs `quality_check`; a **reconciliação** | tabela da secção 8 |
| 14 | Observabilidade (roadmap) | pipeline, source e data; verde ≠ dados certos | 3 colunas |
| 15 | Fecho e exercícios | o que ficou de fora de propósito e porquê | lista de simplificações |

### Os 7 cenários de demonstração

| # | Modo da API | O que se vê |
|---|---|---|
| 1 | `healthy` | as 7 tasks a verde |
| 2 | `http_500` | `check_api` falha 3 vezes (1 + 2 retries); resto `upstream_failed` |
| 3 | `slow` | `check_api` passa (o `/health` é rápido); `extract` esgota o timeout |
| 4 | `rate_limit` (429) | falha 2 vezes e passa à 3.ª tentativa |
| 5 | `schema_drift` | `validate` falha: campo renomeado |
| 6 | `invalid_payload` | `validate` falha: valores negativos e país inválido |
| 7 | (repetir o mesmo dia) | sem duplicados: `inserted: 0, updated: N` |

Mais uma demo possível: adulterar o `daily_control` e ver o `quality_check` falhar
na reconciliação (README, secção 13).

### Números verificados
* 95 testes automáticos a passar.
* ≈ 170 conversões, ≈ 190 linhas de custo e 6 de daily control por dia.
* ROAS por campanha entre 0,88 e 2,06, com uma campanha em prejuízo (DE Loans).
* Demo de idempotência: 516 linhas (ingénuo) contra 172 (idempotente) ao fim de 3 execuções.

### Frases que sintetizam o projeto
* *"A API é o producer. A pipeline é o consumer. O Pydantic é o contrato."*
* *"Escolher a chave primária é escolher o grain."*
* *"Retry é para erros transitórios; um erro determinístico só atrasa a falha."*
* *"Soma primeiro, divide depois."*
* *"Nulo não é zero."*
* *"A pipeline pode estar verde e os dados errados."*
