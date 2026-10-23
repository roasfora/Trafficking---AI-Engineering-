# Mapeamento: provider → modelo canónico

> **Aviso.** Os tickets descrevem o comportamento e os campos relevantes, mas **não
> trazem os payloads completos** das APIs reais. Os formatos abaixo são
> **representações pedagógicas inferidas**. `USE_MOCK_API=false` tem de ser validado
> contra a documentação e payloads reais antes de ser considerado pronto para produção.

## TrafficJunky

Uma linha por **campanha do provider** e dia, paginada (`limit`/`offset`).
Pedido: `startDate = endDate = DD/MM/YYYY`, sem timezone.

| Campo do provider | Campo canónico | Regra |
|---|---|---|
| `campaign_type` | — | `"deal"` é **ignorada** |
| `campaign_name` | `campaign_id` | match **por nome** com `dim_campaign`; sem match → descartada e registada |
| `campaign_name` (repetido) | — | linhas com o mesmo nome **agregam-se** (soma de impressions, clicks e cost) |
| `impressions` | `impressions` | |
| `clicks` | `clicks` | |
| `cost` | `cost` | `Decimal`, 4 casas |
| `ecpc`, `ecpm`, `ctr` | — | **não se guardam** (recalculam-se na view) |
| — | `source_specific_id` | `NULL` |
| — | `provider` | `trafficjunky` |
| — | `currency` | configuração (`TRAFFICJUNKY_CURRENCY`, `EUR`) |
| — | `date` | o dia da run |

**Total de controlo** (reconciliação): endpoint de totais independente do detalhe,
ou, alternativamente, voltar a pedir as stats e somar o custo das campanhas não-deal.
Configurável em `TRAFFICJUNKY_TOTAL_STRATEGY`:

| Estratégia | Independente do detalhe? |
|---|---|
| `summary_endpoint` (usada no mock) | **sim**: apanha um detalhe truncado |
| `refetch_stats` (o que os tickets descrevem) | **não**: se o detalhe está truncado, trunca os dois; a falha passa despercebida (`test_refetch_strategy_is_NOT_independent_of_the_detail`) |

## Erobella

A resposta tem **três partes**. O desempenho está por **creative**, e a campanha só
aparece escondida no `link` do creative.

| Parte | O que é |
|---|---|
| `by_day_creative` | uma linha por dia e creative: impressions, clicks, ctr_pct, cost_eur, ecpm_eur |
| `by_creative` | uma linha por creative: label, partner, headline, text, tag, **link**, image |
| `by_day` | o total do dia |

| Campo do provider | Campo canónico | Regra |
|---|---|---|
| `by_creative.link` (cruzado por `label`) | `campaign_id` | UUID extraído do link; sem link / sem UUID / UUID desconhecido → descartada e registada |
| `label` | `source_specific_id` | o creative |
| `impressions`, `clicks` | idem | |
| `cost_eur` | `cost` | `Decimal`, 4 casas |
| `ctr_pct`, `ecpm_eur` | — | **não se guardam** |
| — | `provider` | `erobella` |
| — | `currency` | `EROBELLA_CURRENCY` (`EUR`, coerente com o nome `cost_eur`) |

**Extração do UUID** (`extract_campaign_id`, em `providers/erobella.py`): dois formatos,

```
https://trk.example/<uuid>?creative=x          UUID no caminho
https://trk.example/click?vcid=<uuid>&...      parâmetro vcid        (vence se houver os dois)
```

Devolve `None` para `None`, `""`, links sem UUID, UUID truncado ou colado a mais texto;
nunca levanta exceção para um link estranho.

**Total de controlo:** `by_day.cost_eur` da própria resposta, que é independente de
`by_day_creative`.

## Lado a lado

| | TrafficJunky | Erobella |
|---|---|---|
| Estrutura | lista paginada | 3 partes, sem paginação |
| Nível | campanha | creative |
| Campanha | por **nome** | escondida num **link** |
| Duplicados | agregam-se | não há (cada creative é uma linha) |
| Total do dia | endpoint à parte | `by_day`, na própria resposta |
| `source_specific_id` | `NULL` | label do creative |
| Moeda no payload | não indicada | no nome: `cost_eur` |
| O que a transformação rejeita | campanha sem match | creative sem link/UUID |
| Resultado | **o mesmo modelo canónico** | **o mesmo modelo canónico** |

## O que fica fora (comportamento de produção dos tickets)

| Nos tickets | Aqui |
|---|---|
| MongoDB | PostgreSQL |
| S3 | ficheiros em `data/raw/` |
| Sentry (nível *critical*) | `log.critical` |
| Slack | só log |
| Voluum | `dim_campaign` carregada de `data/campaigns.csv` |
| várias contas (`trafficjunkynewaccount`) | **uma conta por provider** |
| 3 schedules (today / yesterday / last 7 days) | 1 diário (+ `conf.date` para reprocessar) |
| check de investimento só no schedule dos 7 dias | `reconcile` em **cada** run |
| **apagar** o dia quando o Mongo tem mais do que a API | não implementado |
| **reprocessar em loop** até não criar documentos novos | não implementado |
| alerta no Slack se a diferença persiste | não implementado |
| "a campanha mais recentemente criada" com o mesmo nome | `campaign_name` **único** em `dim_campaign` |
