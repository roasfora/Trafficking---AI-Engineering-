# Aula 08 — Data Quality Control Center

> **A pipeline that runs successfully is not necessarily a pipeline that produces trustworthy data.**
>
> **Python · PostgreSQL · Docker Compose · Apache Airflow (opcional) · Streamlit**

PoC didática de **Data Quality / Data Observability** sobre três providers simulados (Erobella, TrafficJunky, Voluum):
camadas Bronze → Silver → Gold, checks configuráveis, reconciliação, deteção simples de anomalias, resultados
persistidos, alertas simulados, um DAG com *quality gates* e um dashboard Streamlit.

Os dados são **100 % sintéticos**. Não há APIs reais, credenciais nem segredos. Sem LangChain, Great Expectations, Soda,
dbt, Kafka ou Spark: o objetivo é *Data Quality Engineering*.

```text
Pipeline Observability  →  did the job run?
Data Quality            →  should we trust the result?
```

## Princípios

```text
Bronze preserves.            (o que o provider disse, tal como o disse)
Silver interprets.           (EUR, nomes canónicos, grain)
Gold validates metrics.      (rácios como ratio of sums, nunca AVG de rácios)
Data Quality is data.        (os resultados são linhas numa tabela, não logs)
Checks are configuration.    (config/quality_checks.yaml, não lógica de DAG)
Airflow orchestrates and reacts; it is not the Data Quality system.
The dashboard reads quality. It does not define quality.
Anomaly != error. It means investigate.
```

## 1. Arquitetura

```text
 API simulators                  (simulators/: Erobella · TrafficJunky · Voluum, cenários healthy | broken)
        │
        ▼
 BRONZE  raw.*                   "Did we receive the data correctly?"      → bronze_quality
        │  (bronze_loader: sem converter, sem renomear, sem corrigir)
        ▼
 SILVER  analytics.campaign_performance_daily
        │  (normalize.sql: EUR via analytics.exchange_rate)                 "Does the data make sense?" → silver_quality
        ▼
 GOLD    semantic.yaml + views                                              "Are the metrics trustworthy?" → semantic_quality
        │
        ▼
 publish  analytics.published_campaign_performance_daily   ← só recebe dados se NÃO houver FAIL
        ▼
 DASHBOARD / AI                  "Can consumers safely use them?"

 todos os checks ──► data_quality.check_results ──► Alertas (consola + data_quality.alerts [+ webhook opcional])
                                  └──────────────► Streamlit (só lê)         └► data_quality.current_issues (futuro chatbot)
```

| Camada | Pergunta | Onde |
|---|---|---|
| Bronze (`raw`) | Recebemos os dados corretamente? | `sql/01_raw_schema.sql`, `ingestion/bronze_loader.py`, `quality/bronze_checks.py` |
| Silver (`analytics`) | Os dados normalizados fazem sentido? | `sql/02_analytics_schema.sql`, `ingestion/normalize.py`, `quality/silver_checks.py` |
| Gold (semântica) | As métricas publicadas merecem confiança? | `semantic.yaml`, `sql/05_views.sql`, `quality/semantic_checks.py` |
| Reconciliação | O mesmo número, contado em dois sítios, bate? | `quality/reconciliation.py` |
| Resultados | Data Quality is data | `sql/03_quality_schema.sql` → `data_quality.check_results` |

## 2. Arrancar

```bash
cd aula08-data-quality-control-center
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

docker compose up -d postgres         # PostgreSQL na porta 5436 (aulas 06 e 07 usam 5434 e 5435)
docker compose ps                     # espera por "healthy"
```

Os scripts `sql/*.sql` correm **uma vez**, quando o volume nasce. Para recomeçar do zero:
`docker compose down -v && docker compose up -d postgres`.

A configuração está em `.env.example` (`DATABASE_URL`, `SCENARIO`, `AS_OF_DATE`, `GATE_MODE`, `DQ_WEBHOOK_URL`). Os
valores por omissão funcionam sem `.env`.

## 3. Demo

```bash
python -m quality.demo_run --scenario healthy      # tudo PASS, publish ALLOWED
python -m quality.demo_run --scenario broken       # os 9 problemas, publish BLOCKED
python -m quality.demo_run --scenario broken --provider voluum      # só um provider
python -m quality.demo_dag --scenario broken       # o mesmo fluxo como DAG: estados das tasks (sem Airflow)
streamlit run dashboard/streamlit_app.py           # Data Quality Control Center
```

Saída do `healthy`:

```text
BRONZE GATE: PASS
SILVER GATE: PASS
SEMANTIC GATE: PASS
PUBLISH: ALLOWED
```

Alerta no `broken` (consola, e também gravado em `data_quality.alerts`):

```text
[DQ ALERT] provider=voluum layer=bronze check=voluum_pagination status=FAIL observed=50 expected=60
```

### Passo a passo recomendado para a aula

1. **Healthy.** `Run healthy scenario` no dashboard: tudo verde, `Publish status: PUBLISHED`.
2. **Broken.** `Run broken scenario`: Erobella RED, TrafficJunky RED, Voluum RED, `Publish status: BLOCKED`.
3. **Falhas.** Abre *Latest failing checks* e o *Drill-down*: missing day, duplicate, pagination, schema drift, CPC mismatch.
   Cada check explica *Why it matters*.
4. **Alerta.** Mostra a linha `[DQ ALERT]` na consola (ou `SELECT * FROM data_quality.alerts`).
5. **DAG.** `python -m quality.demo_dag --scenario broken`: `simulate → bronze → DQ → blocked` (ver secção 5).
6. **Anomalia ≠ erro.** O *spend drop* do TrafficJunky dá WARN e **não** bloqueia nada por si: o `daily_control` (sistema
   interno) concorda que o spend caiu; só uma investigação diz se foi orçamento esgotado ou um problema de dados.
7. **Os consumidores continuam seguros.** `SELECT DISTINCT run_id FROM analytics.published_campaign_performance_daily`
   continua a apontar para o último run bom: um FAIL **nunca apaga** Bronze nem Silver, só impede o publish.

## 4. Os dois modos das gates: `strict` e `observe`

| | `strict` | `observe` |
|---|---|---|
| Um FAIL numa gate… | **para** o pipeline (as camadas seguintes não correm) | bloqueia o publish mas **continua** |
| Onde é o padrão | o DAG Airflow e `quality.demo_dag` | `quality.demo_run`, o dashboard e `GATE_MODE` |
| Serve para | produção: não gastar tempo em dados que já sabemos maus | aula: ver **todos** os 9 problemas num só run |

Em `strict`, o `broken` pára na Bronze (Erobella, TrafficJunky e Voluum falham aí) e **não chega** a ver o spend drop,
o CPC mismatch nem o revenue sem conversões, que vivem na Silver e na camada semântica. É a gate a fazer o seu trabalho:
arranja-se a Bronze primeiro. Em `observe` vês tudo. Escolhe com `--gate-mode strict|observe` ou `GATE_MODE`.

## 5. Airflow (educativo, opcional)

O DAG está em `dags/provider_data_quality.py` e **não contém lógica de checks**: só chama `quality/pipeline.py`, que
chama `quality/runner.py`.

```text
[ingestion]        simulate_erobella | simulate_trafficjunky | simulate_voluum  →  load_bronze
[quality_bronze]   bronze_quality
[transform]        normalize
[quality_silver]   silver_quality
[quality_gold]     semantic_quality
[publish]          notify  →  publish
```

Como reage a uma falha:

| Situação | Estado |
|---|---|
| gate com PASS/WARN | a task passa, o fluxo segue |
| gate com FAIL (modo strict) | a task **falha**; as seguintes ficam `upstream_failed` |
| `notify` | `trigger_rule=all_done`: corre sempre; regista a decisão `publish_allowed` e resume os alertas |
| `publish` | só corre se a gate semântica passou; se houver FAIL levanta `PublishBlocked` |

**Sem Airflow** (o caminho leve): `python -m quality.demo_dag --scenario broken` reproduz o mesmo fluxo e estados:

```text
[quality_bronze]
   bronze_quality     FAILED    <- GateFailed: BRONZE gate failed (8 FAIL): pipeline stopped
[transform]
   normalize          SKIPPED
...
[publish]
   notify             OK
   publish            SKIPPED
result: BLOCKED: consumers keep the last good data
```

**Com Airflow** (imagem oficial 3.3.2, como na Aula 03; pesado, por isso é um *profile* à parte):

```bash
docker compose --profile airflow up -d        # UI em http://localhost:8082 (sem login: `SIMPLE_AUTH_MANAGER_ALL_ADMINS`, simplificação de formação)
docker compose exec airflow airflow dags unpause provider_data_quality
docker compose exec airflow airflow dags trigger provider_data_quality --conf '{"scenario": "broken", "gate_mode": "strict"}'
```

Para correr o DAG uma vez, sem subir a UI, com uma imagem Airflow que já tenhas:
`airflow dags test provider_data_quality 2026-11-13 --conf '{"scenario":"broken","gate_mode":"strict"}'`
(com `DATABASE_URL` a apontar para o PostgreSQL da PoC, e `PYTHONPATH` para a pasta do projeto).

## 6. Os 9 problemas plantados (`SCENARIO=broken`)

| # | Provider | Problema | Check que o apanha | Camada | Estado |
|---|---|---|---|---|---|
| 1 | Erobella | Dia 11 Nov em falta | `erobella_coverage` (`row_count`) | bronze | **FAIL** |
| 2 | Erobella | `clicks = NULL` num dia | `erobella_clicks_null_rate` (`null_rate`) | bronze | WARN |
| 3 | Erobella | schema drift: `cost.amount` em vez de `cost_eur` | `erobella_schema` (`schema_diff`) | bronze | **FAIL** |
| 4 | TrafficJunky | mesma campanha/dia duas vezes | `trafficjunky_duplicates` + `silver_unique_grain` | bronze, silver | **FAIL** |
| 5 | TrafficJunky | spend ~75 % abaixo da média de 7 dias | `daily_volume_change` (`rolling_avg_change`) | silver | WARN (*) |
| 6 | TrafficJunky | `ecpc` do provider ~6 % acima do CPC canónico | `trafficjunky_cpc_reconciliation` (`metric_vs_provider`) | semantic | WARN |
| 7 | Voluum | paginação incompleta (`total_rows > rows`, `truncated`) | `voluum_pagination`, `voluum_truncated`, `voluum_api_to_bronze` | bronze | **FAIL** |
| 8 | Voluum | dados com 2 dias de atraso | `voluum_freshness` (`freshness`) | bronze | **FAIL** |
| 9 | Voluum | `revenue > 0` com `conversions = 0` | `revenue_without_conversions` | silver | WARN |

(\*) O cálculo dá FAIL (queda > 70 %), mas o check tem `severity: warning`: **um check `warning` nunca passa de WARN**.
É a tradução de *anomaly != error*: avisa, notifica, não bloqueia.

Em `observe`, o Erobella herda ainda falhas **em cascata** do schema drift (o `cost` fica NULL na Silver): é esperado e
mostra como um problema na Bronze contamina as camadas seguintes.

Cada ficheiro de `simulators/` diz no topo o que planta. O `daily_control` (investimento e receita
reais, independente dos providers) é a segunda opinião da reconciliação: apanha dias em falta (Erobella, Voluum) e o
dinheiro contado duas vezes (duplicado TrafficJunky: +2,5 %), e concorda com o spend drop, que é real.

## 7. Checks

Configuração em `config/quality_checks.yaml` (46 specs; cada uma com `severity` e `why`). Limites em percentagem são
valores absolutos da diferença.

| Camada | Checks |
|---|---|
| **Bronze** | `freshness` · `schema_diff` · `row_count` · `null_rate` · `duplicate_rows` · `pagination_complete` · `truncated_response` · `reconcile_api_to_bronze` |
| **Silver** | `not_null` · `min_value` · `allowed_values` · `unique_grain` · `country_iso2` · `currency_is_eur` · `clicks_le_impressions` · `conversions_le_clicks` · `revenue_without_conversions` · `cost_without_impressions` · `known_campaign` · `rolling_avg_change` · `reconcile_bronze_to_silver` |
| **Semantic** | `ratio_bounds` (CTR, CR ∈ [0, 100]) · `ratio_of_sums` · `metric_vs_provider` · `metric_availability` (ROAS NULL sem receita) · `no_avg_of_ratios` · `additivity` · `reconcile_silver_to_gold` · `reconcile_control` |

Todos devolvem `CheckResult(run_id, checked_at, provider, dataset, layer, check_name, dimension, status, observed_value,
expected_value, threshold, details)`, gravado em `data_quality.check_results`. Dimensões: `freshness`, `completeness`,
`schema`, `uniqueness`, `validity`, `consistency`, `accuracy`, `volume`, `reconciliation`.

**Gates**

| Estado | Persiste | Notifica | Efeito |
|---|---|---|---|
| PASS | sim | não | segue |
| WARN | sim | sim | segue |
| FAIL | sim | sim | **bloqueia o publish** (nunca apaga Bronze/Silver) |

**Reconciliação** (`quality/reconciliation.py`): API → Bronze (linhas declaradas vs carregadas), Bronze → Silver
(linhas, spend em EUR re-derivado com a tabela de câmbio, clicks, conversões), Silver → Gold (fórmulas do `semantic.yaml`) e
Silver vs `daily_control`. O TrafficJunky vem em USD e é convertido com `analytics.exchange_rate`: a taxa **nunca**
está escrita no SQL de normalização.

**Anomalias** (`quality/anomalies.py`, sem ML): `percentage_change`, `rolling_mean_change`, `rolling_std`, `z_score`, IQR.

## 8. Notificações e `current_issues`

`quality/notifier.py`: `notify(result)`. `ConsoleNotifier` funciona sempre (imprime e grava em `data_quality.alerts`);
`WebhookNotifier` só existe se `DQ_WEBHOOK_URL` estiver definida (vazio = nunca toca na internet; uma falha de rede não
derruba o run). Payload: `provider, dataset, layer, check, status, observed, expected, threshold, run_id, message`.

Preparado para a Aula 07 (sem integrar LangChain): `SELECT * FROM data_quality.current_issues;` devolve os WARN/FAIL do
último run.

## 9. Dashboard

`dashboard/streamlit_app.py` (tema escuro, layout *wide*). **Só faz SELECT** a `data_quality.check_results`,
`pipeline_runs` e `raw.api_runs`; não define limites nem recalcula estados (há testes a garantir isto).

- KPIs: Overall health · Critical failures · Warnings · Latest fresh data · Publish status.
- Cartões por provider (GREEN / YELLOW / RED), com contagens PASS/WARN/FAIL e último dia de dados.
- Linhagem Bronze → Silver → Gold por provider (mostra `not run` onde o pipeline parou).
- Gráficos: estados ao longo do tempo · saúde por provider · *freshness lag* · volume de linhas por run · diferença % de
  reconciliação · falhas por dimensão.
- Tabela de checks falhados + *drill-down* (observed, expected, threshold, details, run_id, *why it matters*).
- Filtros: run_id, intervalo de datas, provider, camada, estado, dimensão.
- Botões *Run healthy scenario* / *Run broken scenario* (chamam o pipeline local, não o Airflow) e a opção *Observe mode*.

## 10. Testes

```bash
docker compose up -d postgres
pytest
```

Os testes de integração usam uma base **separada** (`dq_test`, criada automaticamente) e nunca tocam nos dados da demo.
Sem PostgreSQL fazem *skip*; os testes de lógica pura (anomalias, checks sobre dados em memória) correm sempre.

Cobrem: healthy sem FAIL crítico e com publish permitido; os 9 problemas detetados; `WARN` não bloqueia; `FAIL`
bloqueia o publish e mantém os últimos dados bons; resultados persistidos; notificações em WARN/FAIL (e não em PASS);
`severity: warning` limita a WARN; webhook opcional; modo `strict`; o dashboard faz *smoke*, só lê `check_results` e não
implementa limites.

## 11. Produção: QuickSight

```text
PostgreSQL
data_quality.check_results
        ↓
QuickSight dataset
        ↓
Data Quality dashboard
```

A PoC usa Streamlit; a tabela `check_results` já tem a forma certa para um dataset de BI.

## 12. Limitações da PoC

- **Dados sintéticos.** O "mundo verdadeiro" é gerado de forma determinística (`AS_OF_DATE=2026-11-13`, janela de 14 dias).
  O "agora" da simulação é fixo (06:00 UTC do dia seguinte), para a demo ser reprodutível.
- **Modelo realista simplificado.** `campaigns`, `conversions`, `daily_control`, `exchange_rate` e `alerts` existem;
  `campaign_costs` e `hourly_performance` do modelo completo ficaram de fora (a granularidade é diária).
- **Câmbio e fusos.** USD→EUR por tabela diária; os três providers têm fusos diferentes (UTC, conta, parâmetro `tz` do Voluum)
  e atrasos de conversão. A PoC compara o mesmo conjunto de dias, não modela dados tardios.
- **Gates por run, não por provider.** Um FAIL (em `strict`) para o pipeline todo, não só o provider afetado.
- **Silver reconstruída por run.** Cada run reescreve a Silver de cada provider a partir da Bronze desse run (a Bronze é
  *append-only* por `run_id`). Por isso os runs **não podem sobrepor-se**: o DAG tem `max_active_runs=1` (dois runs em
  paralelo apagavam a Silver um do outro; foi o que aconteceu ao disparar `healthy` e `broken` com segundos de intervalo).
- **Anomalias simples.** Média móvel de 7 dias: sem sazonalidade (fins de semana) nem ML.
- **Airflow.** O DAG foi validado com `airflow dags test` na imagem Airflow 3.3.2; o `profile airflow` do Compose foi construído
  e a UI testada (porta 8082); o primeiro build falhou por timeout de rede e passou à segunda tentativa.
- **Sem autenticação** nem escrita em sistemas externos. O webhook é opcional e não tem retries.
