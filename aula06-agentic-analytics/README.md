# Aula 06 — Agentic Analytics · Controlled Business Agent

> **O objetivo não é construir um agente mais inteligente.
> É construir um agente com menos liberdade e melhor contexto.**
>
> **Python · LangChain · Amazon Bedrock (Claude) · PostgreSQL · Pydantic · `semantic.yaml`**

Projeto do Módulo 06 do AI Engineering Course. Um agente que responde a perguntas de
negócio sobre investimento em tráfego (*"Quanto gastámos ontem na Erobella?"*), mas que só
pode fazer três coisas, sobre uma tabela, com definições de métricas que não inventa.

Os dados são **100 % sintéticos**. Não há credenciais reais no repositório.

```text
LangChain  = componentes / abstração do modelo / tools
Bedrock    = fornecedor do modelo
PostgreSQL = motor de dados + metadata técnica
semantic.yaml = semântica de negócio
Pydantic   = contratos estruturados
```

---

## 1. What we are building

```text
User
 ↓
Controlled Business Agent      agent.py  (ciclo explícito, com limites)
 ↓
LangChain                      bind_tools / invoke / @tool
 ↓
3 tools ──────────────────────────────────────────────┐
 │ get_metric_definition  → semantic.yaml  (sem DB, sem LLM)
 │ get_dataset_metadata   → catálogo do PostgreSQL
 │ run_postgres_query     → SQL guard → PostgreSQL (role read-only)
```

Além do agente há dois componentes **sem liberdade**, onde o LLM não decide nada:

* `workflows/diagnose_metric_drop.py`: *porque é que a CR desceu?* Passos fixos, SQL de templates.
* `dashboard/spec.py`: um contrato Pydantic; o SQL sai das métricas do `semantic.yaml`.

## 2. Why PostgreSQL?

* É a plataforma interna real: o que aprendes aqui aplica-se tal e qual.
* Local e produção usam **o mesmo motor** (mudar de ambiente = mudar o `DATABASE_URL`).
* Tem catálogo técnico (`information_schema`, `COMMENT ON ...`), que o agente lê.
* Simplifica a aula: um só `docker compose`, sem DuckDB nem warehouse.

## 3. Architecture

```text
aula06-agentic-analytics/
├── app.py            CLI: perguntar | diagnose | dashboard
├── agent.py          o ciclo do agente (limites + log)
├── providers.py      get_llm(settings): a ÚNICA fronteira com o fornecedor do modelo
├── config.py         .env → Settings
├── observability.py  logs/requests.jsonl + recibo
├── semantic.yaml     métricas e dimensões governadas
├── prompts/          system.md | system_naive.md
├── tools/            catalog.py · metrics.py · postgres.py · sql_guard.py
├── workflows/        diagnose_metric_drop.py
├── dashboard/        spec.py
├── sql/              01_schema.sql · 02_seed.sql
└── tests/
```

Decisões deliberadas (*explícito > genérico, pequeno > reutilizável*):

* **O ciclo do agente é nosso** (~30 linhas em `agent.py`), não um `AgentExecutor`. O
  LangChain dá-nos o modelo e as tools; o ciclo mostra os limites e o log à vista de todos.
  A próxima evolução natural é o **LangGraph**, mas não é necessário agora.
* As tools são **funções simples** com *docstring*; `tool(função)` transforma-as em tools
  LangChain. A docstring é o que o modelo lê.
* Sem *factories*, registos, injeção de dependências, async, MCP, RAG ou multi-agente.

## 4. Technical metadata vs semantic metadata

```text
PostgreSQL     →  what exists     colunas, tipos, COMMENT ON ...
semantic.yaml  →  what it means   "CPC = SUM(cost) / NULLIF(SUM(clicks), 0), nunca AVG(cost/clicks)"
```

O PostgreSQL sabe que `cost` é `NUMERIC(12,2)`; não sabe que um CPC nunca se calcula como
média de rácios. Por isso o agente tem **duas** fontes de contexto, e a segunda é versionada
em git e revista como código.

## 4b. Streamlit chatbot

Uma segunda interface sobre o **mesmo** agente (`run_agent` em `agent.py`). Não há segundo agente.

```text
CLI (app.py) ─────┐
                  ▼
            agent.py  ◄── get_llm(provider, model_id)  ◄── Bedrock | Ollama
                  ▼
   get_metric_definition · get_dataset_metadata · run_postgres_query
                  ▼
        semantic.yaml · PostgreSQL (guard + role read-only)
```

```bash
docker compose up -d
source .venv/bin/activate
streamlit run streamlit_app.py       # http://localhost:8501
```

Sidebar: **Model Provider** (Amazon Bedrock | Ollama), **Model**, estado da ligação, **Show technical details**
(provider, modelo, chamadas, tools, SQL, tokens, latência, custo estimado, `stopped_by`),
**Clear conversation** e **Generate dashboard specification** (valida o `DashboardSpec` de exemplo
e desenha gráficos nativos; SQL determinístico do semantic layer, sem LLM).

* **Memória curta:** o histórico vive em `st.session_state` e as últimas 10 mensagens (só texto)
  vão ao modelo, para perguntas como *"e qual teve menor?"*. O histórico serve para entender a pergunta;
  o prompt manda voltar sempre à base de dados. Modelos pequenos podem ignorar isto: vê o recibo.
* **Mudar de modelo a meio** não apaga o histórico: aparece um aviso visual ("Model changed to…"), que não vai ao LLM.
* O modelo é cacheado por `(provider, model_id)` com `st.cache_resource`.
* **Custo:** os preços do `.env` valem para o `BEDROCK_MODEL_ID`; para qualquer outro modelo a UI mostra
  `unavailable`. Nunca se aplica o preço de um modelo a outro.

### Bedrock na UI

Preenche no `.env` só os IDs que a tua conta tem ativos (`BEDROCK_NOVA2_LITE_MODEL_ID`,
`BEDROCK_NOVA_LITE_MODEL_ID`, `BEDROCK_CLAUDE_HAIKU_MODEL_ID`, `BEDROCK_GPT_TERRA_MODEL_ID`); os vazios não aparecem.
Não há IDs por defeito. As credenciais AWS vêm da credential chain; a UI só verifica se existem
(não faz nenhuma chamada ao modelo para mostrar o estado).

### Ollama na UI

Arranca-o à parte (`ollama serve`) e instala os modelos tu (`ollama pull …`); a app não instala nada.
Os modelos instalados são descobertos com `GET /api/tags` (embeddings excluídos). Se o Ollama não estiver
ativo, a sidebar avisa e a app continua a funcionar. Fallback: `OLLAMA_MODELS=qwen2.5:7b-instruct,llama3.1:8b`.

### Trocar de provider: a mensagem da aula

```text
Bedrock ↕ Ollama     muda o modelo.
NÃO muda: a app · as tools · o PostgreSQL · o semantic layer · o SQL guard · o role read-only
```

Experimenta a mesma pergunta nos dois e compara os recibos (`provider` e `model` vão para o
`logs/requests.jsonl`, ao lado de tool calls, tokens, latência e custo).

## 5. Start PostgreSQL

```bash
docker compose up -d
```

Cria `postgres:16` na porta **5434** (as aulas 02 e 03 usam 5432/5433), corre `sql/01_schema.sql`
(schema `marketing`, tabela, `COMMENT ON`, role `analytics_agent`) e `sql/02_seed.sql` (80 linhas).
Para repor tudo do zero: `docker compose down -v && docker compose up -d`.

Tabela `marketing.campaign_performance_daily`, grain **1 linha = 1 data + 1 provider + 1 campanha**.

## 6. Setup

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # preenche BEDROCK_MODEL_ID (ver secção 12)
pytest                        # não precisa de Bedrock
```

> Os dados acabam em 2026-11-05. O `.env.example` traz `AS_OF_DATE=2026-11-06`, para que
> *"ontem"* seja 2026-11-05 (as demos usam essa data). Sem isso, "ontem" seria o dia real.

## 7. Run demo 1 — uma métrica simples

```bash
python app.py "Quanto gastámos ontem na Erobella?" -v
```

Esperado: **426,28 EUR**. O recibo mostra `get_metric_definition("gastámos")` → `spend` → `SUM(cost)`.

## 8. Run demo 2 e *naive vs governed* — o CPC

```bash
python app.py "Qual provider teve maior CPC nos últimos 7 dias?" -v           # governado
python app.py "Qual provider teve maior CPC nos últimos 7 dias?" --naive -v   # sem get_metric_definition
```

Período 2026-10-30 → 2026-11-05:

| | trafficjunky | erobella | quem parece mais caro |
|---|---|---|---|
| **correto**: `SUM(cost)/SUM(clicks)` | 0,2699 | 0,2367 | trafficjunky |
| **errado**: `AVG(cost/clicks)` | 0,2644 | **0,3374** | erobella |

A culpa é de uma linha: 2026-11-02, `EB ES Sports Native`, 12 cliques e 30 € (CPC 2,50). Numa
média de rácios pesa tanto como uma campanha de 500 cliques; numa razão de somas quase não pesa.

No modo `--naive` o modelo **não tem** a definição e escolhe a fórmula sozinho.
**O modo naive demonstra risco, não uma falha determinística**: um bom modelo pode acertar na
mesma. Repete algumas vezes, ou compara o SQL nos recibos.

## 9. CR diagnosis — um workflow controlado

```bash
python app.py diagnose conversion_rate 2026-11-05            # 0 chamadas ao LLM
python app.py diagnose conversion_rate 2026-11-05 --explain  # 1 chamada, só para redigir
```

```text
conversion_rate 2026-11-04 -> 2026-11-05: 8.15% -> 7.28% (-0.87 pp)
  erobella       7.90 -> 6.03   contribuição -0.527 pp
  trafficjunky   8.32 -> 8.33   contribuição -0.340 pp
Campanhas de erobella
  EB ES Sports Native   8.57 -> 2.09   contribuição -0.683 pp
```

Passos fixos: resolver métrica → confirmar a mudança → provider → contribuição → top provider →
campanhas → (opcional) LLM explica. Sem ciclo aberto.

**Método de contribuição.** Para uma taxa `N/D` (CR = conversões / cliques), com peso
`w = D_segmento / D_total`:

```text
contribuição = w_atual · taxa_atual  −  w_anterior · taxa_anterior
             = w_atual · (Δ taxa)        ← efeito taxa: converteu pior
             + (Δ w) · taxa_anterior     ← efeito mix:  ganhou/perdeu tráfego
```

As contribuições **somam exatamente** a variação do total (em pontos percentuais). Não se
ordena pela maior queda percentual, porque uma campanha minúscula com uma queda enorme não explica nada.
Repara no TrafficJunky: a sua CR não mexeu (8,32 → 8,33), mas perde −0,34 pp por *mix*:
teve menos tráfego e o peso dos providers mudou. Em `diagnose_metric_drop.py` está a derivação.

## 10. Request receipt

Com `-v` cada pedido imprime um recibo, e **todos** os pedidos (também os falhados) acrescentam
uma linha a `logs/requests.jsonl`: `request_id, timestamp, question, provider, model, model_calls,
tool_calls, input_tokens, output_tokens, latency_ms, sql_queries, estimated_model_cost, stopped_by, answer`
(mais `naive` e `error`).

* Se o provider não devolve tokens, ficam `null`. **Nunca inventamos usage.**
* `estimated_model_cost` só existe se preencheres `MODEL_INPUT_PRICE_PER_1M` e
  `MODEL_OUTPUT_PRICE_PER_1M` com os preços do **teu** modelo. Sem preços: `null`.
* Não há "custo da query PostgreSQL": não há maneira honesta de o calcular.

Limites (`.env`): `MAX_MODEL_CALLS`, `MAX_TOOL_CALLS`, `MAX_COST_PER_REQUEST` (este só atua com
preços configurados). `stopped_by` ∈ `end_turn | max_model_calls | max_tool_calls | max_cost | error`.

## 11. Dashboard spec

```bash
python app.py dashboard            # corre o exemplo de dashboard/spec.py
```

O LLM (ou uma pessoa) pode propor uma `DashboardSpec` em JSON; o Pydantic valida: métricas
existentes no `semantic.yaml`, dimensões existentes, datas ISO, tipos de gráfico e filtros em allowlist.
O SQL é **montado por código** a partir das expressões do semantic layer, com valores em parâmetros.

## 12. Bedrock configuration

```text
LLM_PROVIDER=bedrock
AWS_REGION=eu-north-1
BEDROCK_MODEL_ID=<o id ou inference profile ativo na tua conta>
```

* Credenciais pela *credential chain* normal da AWS (`aws configure`, `AWS_PROFILE`, SSO...). **Zero keys no repo.**
* É preciso ter o acesso ao modelo ativado na conta/região, e permissão `bedrock:InvokeModel*`.
* Usamos só o `ChatBedrockConverse` do LangChain. Sem Bedrock Agents, Knowledge Bases, AgentCore
  nem ciclo manual com `boto3`.
* `BEDROCK_MODEL_ID` fica vazio de propósito: não escolhemos um modelo (nem preços) por ti.

## 13. Ollama — future provider

`providers.py` já tem o ramo `ollama` (`ChatOllama`). Para experimentar:

```text
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:8b      # um modelo com suporte a tool calling
```

Tools, semantic layer, PostgreSQL, SQL guard e workflows **não mudam**. Não foi testado
nesta aula; modelos locais pequenos costumam errar mais no *tool calling*, e é exatamente aí
que os guardrails compensam.

## 14. Security

```text
Prompt → Tool schema → SQL guard → PostgreSQL read-only role
```

* **Sem** tool de shell, de ficheiros ou de HTTP. Só 3 tools.
* `tools/sql_guard.py` (parser **sqlglot**, não regex): só `SELECT` / `WITH … SELECT`; uma statement;
  sem DDL/DML/COPY/GRANT/…, mesmo escondidos num CTE; só `marketing.campaign_performance_daily`
  (também em subqueries, joins e CTEs); funções desconhecidas (`pg_sleep`, `pg_read_file`, `lo_import`…)
  recusadas; tamanho máximo; `LIMIT` máximo imposto; o guard devolve o SQL **regenerado da árvore**.
* **CTE shadowing:** uma tabela sem schema só passa se for um CTE *visível naquele ponto*
  (`(WITH pg_shadow AS (…) SELECT …), pg_shadow` é recusado).
* Role `analytics_agent`: `CONNECT`, `USAGE` no schema, `SELECT` numa tabela; transação *read-only* e
  `statement_timeout` de 5 s. Mesmo que o guard falhasse, a base de dados recusa.
* O modelo nunca vê a connection string; os erros do PostgreSQL passam só pela 1.ª linha.
* `.env` e `logs/*.jsonl` estão no `.gitignore`. O log guarda perguntas e SQL, nunca credenciais.
* A password `agent_dev` é de **desenvolvimento local** (container descartável).
* Os logs e o prompt contêm dados de negócio: tem isso em conta ao trocar para um modelo remoto real.

## 15. Tests

```bash
pytest
```

Nenhum precisa de Bedrock (o agente é testado com um modelo falso). Os de integração
(`test_catalog`, `test_diagnose`, `test_demo_data`, parte de `test_dashboard`) precisam de
`docker compose up -d` e são *skipped* sem ele. Cobrem: sinónimos, metadata/comentários, 30+
casos do SQL guard (incl. bypass por subquery e CTE), limites e falhas do agente, modo naive,
os números das demos e o role read-only.

## 16. Futuro: OpenClaw

Fora de âmbito aqui. A fronteira prevista:

```text
OpenClaw
   │  analytics question
   ▼
POST /analytics/ask
   ▼
Controlled Business Agent
```

A API fica para uma aula futura.

## Verificar os dados

`sql/02_seed.sql` é determinístico (80 linhas, 2026-10-27 → 2026-11-05, 4 campanhas por provider).
Foi calibrado para as demos: spend Erobella 2026-11-05 = 426,28; CPC 0,2699 / 0,2367 (e 0,3374
com a média de rácios); CR total 8,15 % → 7,28 %; trafficjunky 8,32 → 8,33; erobella 7,90 → 6,03;
`EB ES Sports Native` 8,57 → 2,09. Estão todos verificados em `tests/test_demo_data.py`.

## Limitações

* Não foi testado com Bedrock real (ver o relatório de entrega); o fluxo do agente é testado com um modelo falso.
* Um único dataset; o workflow só cobre `conversion_rate`.
* Não há memória entre perguntas, autenticação nem API.
