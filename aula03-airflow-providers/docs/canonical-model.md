# O modelo canónico

> **Contrato do provider ≠ contrato interno.**

Um *canonical model* é o modelo **interno** para onde convergem fontes diferentes.
Cada provider tem o seu schema; depois de uma transformação **específica** de cada
um, todos produzem o mesmo registo. É o que a base de dados e as análises conhecem.

```
contrato EXTERNO               transformação                  contrato INTERNO
(do provider)                  (específica de cada provider)  (nosso)

TrafficJunky  ──► validate_source ──► transform ──┐
  uma linha por campanha                          ├──► validate_canonical ──► CampaignDailyStat
Erobella      ──► validate_source ──► transform ──┘
  uma linha por creative; campanha num link
```

## De onde nasce

Não nasce de uma abstração por abstração. Nasce de uma **necessidade**:

1. Com **um** provider (TrafficJunky) tudo cabe numa tabela e não há nada a unificar.
2. Chega a **Erobella**, com um schema completamente diferente (três partes, creatives,
   campanha escondida num link). Sem um modelo comum teríamos duas tabelas, duas
   análises e duas definições de "custo por campanha".
3. A pergunta passa a ser: *que registo é igual nos dois, e o que é específico de cada
   um?* A resposta é o `CampaignDailyStat`.

## O modelo

```python
class CampaignDailyStat(BaseModel):          # contracts/canonical.py
    date: date
    provider: Provider                       # trafficjunky | erobella
    campaign_id: UUID                        # SEMPRE o nosso campaign_id
    source_specific_id: str | None           # TrafficJunky: None · Erobella: label do creative
    currency: str                            # ISO 4217
    impressions: int                         # >= 0
    clicks: int                              # >= 0
    cost: Decimal                            # >= 0, até 4 casas
```

**Grain:** `1 linha = 1 dia + 1 provider + 1 campanha + 1 source_specific_id`.

Duas fontes com grains de **origem** diferentes (campanha vs creative) convergem
neste grain comum: o que difere cabe numa coluna opcional. O TrafficJunky não tem o
nível do creative, por isso `source_specific_id` é `NULL`; a Erobella usa-o.

## Decisões do modelo

### Só métricas base

`impressions`, `clicks` e `cost` são aditivas e são a fonte de verdade. **CPC, CPM e
CTR não se guardam**: calculam-se em [sql/analytics.sql](../sql/analytics.sql):

| Métrica | Fórmula | Nota |
|---|---|---|
| CPC | `cost / clicks` | `NULLIF` evita divisão por zero |
| CPM | `cost / impressions × 1000` | |
| CTR | `clicks / impressions` | fração: `0.02` = 2 % |

**Rácios reportados pelo provider vs recalculados.** Os providers enviam `ecpc`,
`ecpm` e `ctr`, e os contratos de origem aceitam-nos. Não os guardamos porque:

* vêm **arredondados** (2 casas) e por isso não batem com `cost / clicks`;
* vêm em **unidades diferentes** (`ctr` em percentagem; o nosso, em fração);
* **não se somam**: ao agregar duas campanhas com o mesmo nome, o rácio de uma delas
  deixa de fazer sentido (no sistema real, a linha agregada herda os rácios da
  *primeira*, o que está errado depois de somar). Recalculados a partir das métricas
  base, são sempre coerentes.

Regra de ouro: **soma primeiro, divide depois**. O CPC de uma campanha com vários
creatives não é a média dos CPC dos creatives (`test_creatives_are_summed_before_dividing`).

### `currency` é obrigatória

Um custo sem moeda é um número sem significado. **Custos de moedas diferentes nunca
se agregam diretamente sem conversão.** As views agrupam por `currency`, e a
reconciliação compara por `currency`.

Nesta aula os dois providers faturam em **EUR**. É uma **simplificação pedagógica**:
permite mostrar o campo sem introduzir conversão cambial. Não é o que se assume na
realidade.

### A chave de idempotência e o `NULL`

```sql
CONSTRAINT uq_campaign_daily
    UNIQUE NULLS NOT DISTINCT (date, provider, campaign_id, source_specific_id)
```

Numa unique constraint **tradicional**, `NULL` nunca é igual a `NULL`: duas linhas
`(dia, 'trafficjunky', campanha, NULL)` são consideradas *diferentes*, o
`ON CONFLICT` nunca dispara e cada recarga **duplica** o TrafficJunky, **sem nenhum
erro**. `NULLS NOT DISTINCT` (PostgreSQL 15+) trata os `NULL` como iguais.

Não se usa uma string vazia como sentinela: `NULL` significa "não há" e deve continuar
a ser `NULL`. A base de dados e o contrato recusam `''`.

Ver `tests/test_load_db.py` e a demo `scripts/demo_idempotency.py`.

### `extra="forbid"` no canónico, `extra="ignore"` na origem

| | Contrato de origem | Contrato canónico |
|---|---|---|
| De quem é | do **provider** | **nosso** |
| Campo desconhecido | ignora (o provider acrescenta campos quando quer) | **erro** |
| Campo que consumimos em falta | **erro** | erro |

## Duas validações, duas perguntas

| | `validate_source` | `validate_canonical` |
|---|---|---|
| Pergunta | o payload do **provider** tem a forma esperada? | o registo **transformado** respeita o **nosso** modelo? |
| Falha quando | campo obrigatório em falta, tipo errado, campo renomeado | valor impossível (custo negativo, moeda inválida...) ou bug do transform |
| Contrato | `contracts/trafficjunky.py`, `contracts/erobella.py` | `contracts/canonical.py` |

## O que é rejeitado onde

| Situação | Onde | O que acontece |
|---|---|---|
| Campo obrigatório do provider em falta ou renomeado | `validate_source` | **a task falha** |
| TrafficJunky: campanha sem correspondência em `dim_campaign` | `transform` | linha **descartada e registada** |
| Erobella: creative sem link, ou link sem UUID | `transform` | linha **descartada e registada** |
| Registo transformado inválido no modelo canónico | `validate_canonical` | **a task falha** |
| Total na base de dados ≠ total da API | `reconcile` | **a task falha** |

A separação é deliberada. Uma campanha que não sabemos mapear é um dado *válido*, mas
*impossível de mapear para o nosso domínio*: não é um erro do contrato. É descartada
(com log e contagem), e é a **reconciliação** que revela o impacto potencial dessa
perda. Não há quarentena nesta versão.
