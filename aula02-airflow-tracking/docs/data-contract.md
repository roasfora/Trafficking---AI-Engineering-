# Data contract

> **A API é o producer.**
> **A pipeline é o consumer.**
> **O Pydantic representa o contrato entre ambos.**

Um *data contract* é o acordo explícito sobre a forma dos dados que um sistema
entrega a outro: que campos existem, de que tipo, o que é obrigatório, que
valores são válidos. Sem contrato, o acordo existe só na cabeça de quem
escreveu a API, e a primeira vez que alguém o quebra é descoberto quando um
dashboard mostra números errados.

O contrato vive em [`api/schemas.py`](../api/schemas.py), em código executável.
A documentação desse ficheiro **é** a especificação; não há um PDF paralelo que
possa ficar desatualizado. Os campos vêm da estrutura real
([data-structure-reference.md](../data-structure-reference.md)); um `?` ali é um
campo opcional aqui.

## Os modelos

| Tipo | Modelos |
|---|---|
| Dimensões | `Workspace`, `TrafficSource`, `Campaign`, `Offer` |
| Facts | `Conversion`, `CampaignCost`, `DailyControl` |
| Envelope | `Page` (paginação) |

### Campos obrigatórios e opcionais

Quase tudo é **obrigatório**. Os opcionais (o `?` da estrutura real):

| Modelo | Campo | Significado de ausente / `null` |
|---|---|---|
| `Offer` | `country_code` | oferta global, sem país |
| `CampaignCost` | `clicks` | o provider não reporta clicks |
| `CampaignCost` | `impressions` | o provider não reporta impressions |

```python
impressions: Annotated[int, Field(strict=True, ge=0)] | None = None   # opcional
```

Um campo opcional pode vir ausente **ou** `null`. Um obrigatório sem valor produz
`Field required`. Atenção: `null` quer dizer "não sei", e **não é o mesmo que `0`**.

### Tipos

| Campo | Tipo | Observação |
|---|---|---|
| `*_id` de entidade | `str`, **estrito**, padrão UUID em minúsculas | um `int` ou um UUID mal formado falha |
| `click_id` | `str`, 32 caracteres hexadecimais | |
| `conversion_type_id` | `int`, **estrito**, `>= 1` | `"1"` falha |
| `visit_timestamp`, `postback_timestamp`, `datetime`, `created` | `AwareDatetime` | tem de ter fuso horário |
| `date` | `date` | |
| `cost`, `revenue`, `revenue_original_currency`, `payout`, `investment` | `float`, `>= 0`, sem NaN/Infinity | |
| `clicks`, `impressions` | `int`, estrito, `>= 0` | opcionais |
| `is_paused`, `deleted`, `is_manual` | `bool` | |

**Modo estrito.** Por omissão o Pydantic é *lax*: converte `"12"` em `12`. Para um
contrato entre sistemas isso é simpático demais; se o producer passar a enviar
strings, queremos saber. Daí `Field(strict=True)`.

### Enums (conjuntos fechados)

`CampaignCost.investment_provider` é um enum de 16 valores (`exoclick`,
`trafficstars`, `reactiveclicks`, `clickemistry`, `dopaclicks`, `soladsmedia`,
`pushground`, `trafficgold`, `traffichunt`, `propellerads`, `adextrem`, `adness`,
`tacoloco`, `trafficjunky`, `trafficjunkynewaccount`, `pushub`), tal como na
estrutura real. Um valor novo (`facebook`) é uma violação do contrato até o
contrato ser atualizado.

### Constraints

* `cost >= 0`, `revenue >= 0`, `revenue_original_currency >= 0`, `investment >= 0`
* `country_code` e `geo`: exatamente 2 letras maiúsculas (`^[A-Z]{2}$`). `geo` aceita `WW` (worldwide)
* `currency_code`: 3 letras maiúsculas
* `clicks >= 0`, `impressions >= 0`

### Uma regra personalizada

`CampaignCost.datetime` tem de ser o **início de uma hora** (minutos e segundos a
zero), porque o custo é horário. É um `@field_validator`: o Pydantic não se limita
a tipos, aceita lógica própria.

### Campos desconhecidos: `extra="forbid"`

Um campo que o contrato não conhece é um erro. É a opção mais rígida: um campo
*novo* (mudança aditiva, normalmente inofensiva) também faz a pipeline falhar.
A alternativa, `extra="ignore"`, tolera campos novos e só falha quando algo
*desaparece* ou muda de tipo. Escolheu-se `forbid` porque torna a deriva
visível numa aula; muitos consumers reais preferem `ignore`.

## Erros de validação (reais)

| Payload | Erro do Pydantic |
|---|---|
| `revenue: -5` | `revenue` · `greater_than_equal` · *Input should be greater than or equal to 0* |
| `country_code: "PRT"` | `country_code` · `string_pattern_mismatch` · *String should match pattern '^[A-Z]{2}$'* |
| `visit_timestamp: "2026-10-01T10:00:00"` | `visit_timestamp` · `timezone_aware` · *Input should have timezone info* |
| `campaign_id: 123` | `campaign_id` · `string_type` · *Input should be a valid string* |
| `click_id: "abc"` | `click_id` · `string_pattern_mismatch` · *String should match pattern '^[0-9a-f]{32}$'* |
| `investment_provider: "facebook"` | `investment_provider` · `enum` · *Input should be 'exoclick', 'trafficstars', ...* |
| `datetime: "2026-10-01T10:30:00+00:00"` | `datetime` · `value_error` · *deve ser o inicio de uma hora* |
| `clicks: -5` | `clicks` · `greater_than_equal` |
| `revenue` renomeado para `revenue_amount` | `revenue` · `missing` **e** `revenue_amount` · `extra_forbidden` |

Todos eles têm um teste em [`tests/test_schemas.py`](../tests/test_schemas.py).

## Producer-side vs consumer-side validation

| | Producer-side | Consumer-side |
|---|---|---|
| Onde | na API, antes de enviar | na task `validate`, depois de receber |
| Pergunta | "eu cumpro o que prometi?" | "o que recebi cumpre o acordado?" |
| Apanha | bugs do próprio producer, **se** a validação existir | qualquer desvio, venha de onde vier |
| Falha quando | o producer valida mal ou não valida | nunca depende do producer |

Na resposta normal da API cada registo passa pelo modelo Pydantic antes de sair
(producer-side). Mas **a pipeline não assume que a API está certa**: valida de
novo (consumer-side). A diferença vê-se no modo `schema_drift` (ver
`api/faults.py`): a API devolve o payload *cru*, sem o passar pelo modelo, como
um producer que mudou sem avisar. Nenhuma validação do lado dele o impede; é a
task `validate` do consumer que descobre.

Uma nota de honestidade: aqui o contrato é **partilhado por ficheiro** (o Airflow
monta a pasta `api/`). Em produção o contrato seria um artefacto versionado e
independente (pacote, JSON Schema, schema registry), com regras de
compatibilidade entre versões.

## Contrato vs qualidade de dados

| `validate` (Pydantic) | `quality_check` (SQL, depois do load) |
|---|---|
| Este **registo** tem a forma certa? | Este **conjunto** de dados faz sentido? |
| schema, campos obrigatórios, opcionais | row count > 0 |
| tipos, enums | freshness |
| constraints de campo (`revenue >= 0`, `country_code`...) | chaves únicas (compostas) |
| regras de um só campo (hora certa) | integridade referencial (FKs) |
| | `postback_timestamp >= visit_timestamp` |
| | fonte da conversão == fonte da campanha |
| | reconciliação com o `daily_control` |

`revenue < 0` falha **no `validate`**: é uma violação de uma constraint de campo
do contrato, e quebra a task antes de qualquer escrita.

Uma nota sobre `postback_timestamp >= visit_timestamp`: como as duas datas vivem
na mesma linha, também poderia ser um `@model_validator` do contrato. Fica no
`quality_check` por escolha de ensino: é uma regra *entre campos*, não *de um campo*.
A fronteira entre contrato e qualidade é, em parte, uma decisão de equipa.

## O que acontece quando o contrato é violado

A task `validate` valida **todos** os registos (não pára no primeiro) e regista,
para cada dataset, quantos falharam e porquê:

```
conversions      13 de 172 registos INVALIDOS     (modo invalid_payload)
    campo=revenue         erro=greater_than_equal     em 18 registos
    campo=country_code    erro=string_pattern_mismatch em 17 registos

conversions      172 de 172 registos INVALIDOS    (modo schema_drift)
    campo=revenue         erro=missing           em 172 registos
    campo=revenue_amount  erro=extra_forbidden   em 172 registos
```

Ver tudo de uma vez distingue "um registo estragado" de "o schema mudou" (todos
os registos falham). Depois levanta `ContractViolation`; `transform`, `load_*`
e `quality_check` ficam `upstream_failed` e nunca correm.

## Evolução de produção: quarentena

Esta versão falha a task inteira se **um** registo for inválido. É o
comportamento mais simples de ensinar e o mais seguro (dados maus nunca entram),
mas num sistema real um único registo estragado não deveria parar a carga de
milhares de bons. A evolução habitual é a **quarentena**: os registos inválidos
vão para uma tabela à parte (`rejected_records`, com o payload e o erro), os
válidos seguem, e a pipeline só falha acima de um limiar (por exemplo, mais de
1 % rejeitados). **Não está implementada** nesta versão, de propósito.

## Mudanças ao contrato

| Mudança | Compatível? |
|---|---|
| Acrescentar campo opcional | sim (mas com `extra="forbid"` o consumer atual falha; ver acima) |
| Acrescentar campo obrigatório | **não** para os consumers atuais |
| Remover ou renomear um campo | **não** (é o `schema_drift`) |
| Mudar o tipo de um campo (`int` → `str`) | **não** |
| Alargar um enum (novo valor) | só se os consumers o tolerarem |
| Apertar uma constraint | **não** para producers que a violem |

Quebrar o contrato exige versionar (`/v2/conversions`) e uma janela de migração em
que os dois coexistem.
