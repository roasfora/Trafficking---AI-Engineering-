# Modelo de dados

O modelo parte da **estrutura real** dos dados ([data-structure-reference.md](../data-structure-reference.md))
e usa o *dataset sintético mínimo* da sua secção 6. Tem **4 dimensões e 3 facts**.

Na origem os dados vivem em dois sítios, e isso aparece no modelo:

```
Mongo     Conversion, CampaignTrafficSourceData  ──►  fact_conversions, fact_campaign_costs
Postgres  Campaign, TrafficSource, Workspace     ──►  dim_campaign, dim_traffic_source, dim_workspace
Postgres  DailyControl                           ──►  fact_daily_control
Voluum    Offer                                  ──►  dim_offer
```

```
   dim_workspace            dim_traffic_source              dim_offer
   PK workspace_id          PK traffic_source_id            PK offer_id
        ▲                          ▲   ▲                         ▲
        │ FK                       │FK │ FK                      │ FK
        └────────── dim_campaign ──┘   │                         │
                    PK campaign_id     │                         │
                      ▲   ▲   ▲        │                         │
              ┌───────┘   │   └────────┼─────────────────┐       │
              │ FK        │ FK         │ FK              │ FK    │
   fact_campaign_costs    │    fact_conversions ──────────┴───────┘
   PK (datetime,          │    PK (click_id, conversion_type_id,
       campaign_id,       │        postback_timestamp)
       investment_provider)
                    fact_daily_control
                    PK (date, campaign_id)
```

## 1. Grain

> **Grain** = o que representa **uma linha** da tabela.
> É a primeira decisão de modelação e a que todas as outras dependem.

| Tabela | Grain |
|---|---|
| `fact_conversions` | **1 linha = 1 conversão** (um postback) |
| `fact_campaign_costs` | **1 linha = 1 campanha × 1 hora × 1 `investment_provider`** |
| `fact_daily_control` | **1 linha = 1 campanha × 1 dia** |
| `dim_workspace` / `dim_traffic_source` / `dim_campaign` / `dim_offer` | 1 linha = 1 entidade |

Repara que as três facts têm **grains diferentes** (um evento, uma hora, um dia).
Não se somam umas às outras sem cuidado; é por isso que as views agregam cada
fact separadamente antes de as juntar (ver §6).

## 2. Chaves compostas e naturais

A origem **não tem um ID por linha**. Não existe `conversion_id`, nem um ID para
uma hora de custo. A chave primária é, por isso, composta e natural:

| Tabela | PK | Porquê |
|---|---|---|
| `fact_conversions` | `(click_id, conversion_type_id, postback_timestamp)` | um click pode ter várias conversões: de tipos diferentes (lead, venda...) e em momentos diferentes. `click_id` sozinho não identifica uma conversão |
| `fact_campaign_costs` | `(datetime, campaign_id, investment_provider)` | uma campanha pode ser financiada por vários providers na mesma hora |
| `fact_daily_control` | `(date, campaign_id)` | |

Nos dados sintéticos, 10 % dos clicks convertidos têm uma segunda conversão
(tipo 2) mais tarde: o mesmo `click_id` aparece em duas linhas.

A PK é também o que torna a carga **idempotente**: `ON CONFLICT (todas as colunas
da chave)`. Ver README, secção 12.

**Foreign keys:**

| Tabela | FKs |
|---|---|
| `dim_campaign` | `traffic_source_id`, `workspace_id` |
| `fact_conversions` | `campaign_id`, `traffic_source_id`, `offer_id` |
| `fact_campaign_costs` | `campaign_id` |
| `fact_daily_control` | `campaign_id` |

A hierarquia da origem é `Workspace 1─* TrafficSource 1─* Campaign`; a campanha
guarda a sua fonte e o seu workspace.

`fact_conversions` também traz `traffic_source_id`, tal como o documento `Conversion`
do Mongo. É redundante (dá para chegar lá pela campanha), e por isso o
`quality_check` verifica que as duas coincidem.

## 3. Facts vs dimensions

| | Dimensions | Facts |
|---|---|---|
| Respondem a | quem, o quê, onde | o que aconteceu |
| Tamanho | poucas linhas | muitas linhas, só crescem |
| Mudam | devagar (por substituição, SCD tipo 1) | um evento passado não muda |
| Contêm | atributos descritivos | chaves estrangeiras + métricas + contexto |

## 4. Métricas aditivas vs derivadas

**Aditivas** (guardadas nas facts): somam-se por qualquer dimensão.

| Métrica | Onde | Nota |
|---|---|---|
| `cost` | `fact_campaign_costs` | USD |
| `clicks` | `fact_campaign_costs` | **os clicks só existem agregados por hora**, dentro do custo |
| `impressions` | `fact_campaign_costs` | nulo em alguns providers |
| `revenue` | `fact_conversions` | USD (`revenue_original_currency` na moeda da oferta) |
| conversions | `count(*)` de `fact_conversions` | |

**Derivadas** (calculadas em [sql/analytics.sql](../sql/analytics.sql); **nunca**
guardadas por linha):

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

Todas as divisões usam `NULLIF(denominador, 0)`: um dia sem conversões tem CPA
*indefinido* (NULL), não um erro.

(A estrutura real guarda `cost`, `profit` e `roi` também em cada `Conversion`. Não
os copiamos: é exatamente o que **não** se deve guardar por linha.)

> **Soma primeiro, divide depois.** O ROAS de uma semana não é a média dos ROAS
> diários. Soma-se a receita, soma-se o custo, e divide-se. Há um teste que o
> mostra (`tests/test_analytics.py::test_ratios_are_not_additive`).

## 5. Nulos não são zeros

`clicks` e `impressions` são opcionais: alguns providers (`pushground`,
`reactiveclicks`) não reportam impressions. Um `NULL` significa "não sei", e é
diferente de `0`.

Isto tem consequências nas métricas. Se uma campanha tem 150 clicks, dos quais 50
vêm de um provider sem impressions, o CTR *não* é `150 / impressions`; seria
inflacionado. As views usam apenas os clicks das linhas que **têm** impressions
(`clicks_with_impressions`). Há um teste que o mostra
(`test_ctr_and_cpm_ignore_rows_without_impressions`).

## 6. A armadilha do fan-out

Nunca juntar `fact_conversions` com `fact_campaign_costs` e somar a seguir: cada
custo seria repetido por cada conversão. As views agregam **cada fact
separadamente**, ao grain pretendido, e só depois juntam os resultados (por
`FULL JOIN` das chaves conformes: dia + campanha, por exemplo).

## 7. Decisões de modelação (e porquê)

**Sem fact de clicks.** Na origem os clicks não são guardados um a um; só chegam
como `clicks` agregado por hora em `CampaignTrafficSourceData`. Modelamos o que
existe.

**Duas datas numa conversão.** `visit_timestamp` (o utilizador clicou) e
`postback_timestamp` (a conversão foi reportada). Servem a fins diferentes:
* a **extração** é janelada por `postback_timestamp`: é quando *nós* ficamos a saber;
* os **relatórios** agrupam por `visit_date`: assim a receita cai no mesmo dia do
  custo do click que a gerou.

Nos dados sintéticos o postback chega sempre no mesmo dia da visita. Na realidade
pode chegar dias depois (*late-arriving data*), e então o dia da visita vai
sendo **atualizado** por runs posteriores; o upsert idempotente trata disso.

**`affiliate_network` dentro de `dim_offer`.** A estrutura real tem uma entidade
`AffiliateNetwork`. Aqui é um par de atributos da oferta (`affiliate_network_id`,
`affiliate_network_name`), sem dimensão própria: ainda não tem atributos que o
justifiquem. Passa a `dim_affiliate_network` quando os tiver.

**`investment_provider` como coluna simples.** São 16 valores (um enum no
contrato). Passa a dimensão (com `fee`, como o `Provider` do Postgres real) quando
for preciso analisar por atributos do provider.

**Workspaces.** Sem os dados pessoais (`memberships`) da estrutura real.

**Soft delete.** `deleted` em `dim_traffic_source` e `dim_offer` vem da origem.
Mantemos as linhas apagadas (as facts históricas ainda as referenciam).

**SCD tipo 1.** Se o nome ou o estado de uma campanha mudar, o valor novo
substitui o antigo (`ON CONFLICT DO UPDATE`). Perde-se o histórico. Para guardar
"qual era o estado na altura" seria preciso SCD tipo 2 (fora do âmbito).

**`fact_daily_control` é uma fact de outro sistema.** Vem do Postgres, agregada
por dia. Não é derivada dos eventos que carregamos: é uma segunda fonte sobre os
mesmos números. É por isso que serve de **reconciliação**: onde as duas
discordam (e `is_manual` é falso), há um problema. Onde `is_manual` é verdadeiro,
um humano escreveu os números e a discordância é esperada.

**Sem custo por oferta.** `fact_campaign_costs` não tem `offer_id`, e a campanha
não o tem na dimensão. Logo `v_offer_daily` só tem conversões e receita; não há
CPA nem profit por oferta. Uma métrica só existe ao grain em que todos os seus
ingredientes existem.

## 8. Camada analítica

| View | Grain |
|---|---|
| `v_campaign_daily` | 1 campanha × 1 dia |
| `v_traffic_source_daily` | 1 fonte × 1 dia |
| `v_offer_daily` | 1 oferta × 1 dia (só conversões e receita) |
| `v_reconciliation_daily` | 1 campanha × 1 dia do daily control: eventos vs daily control |

Streamlit ou Power BI podem ligar-se diretamente a estas views. Quando agregarem
(semana, mês...), devem voltar a somar `clicks`, `cost`, `revenue`... e
recalcular o rácio, nunca fazer `AVG(roas)`.
