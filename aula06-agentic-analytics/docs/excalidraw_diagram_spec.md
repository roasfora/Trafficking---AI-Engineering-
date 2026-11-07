# Especificação para desenhar no Excalidraw

Dicas gerais: canvas **landscape (16:9)**; fonte *Normal* (não Virgil, se quiseres mais sério) ou *Virgil* (se quiseres informal);
retângulos com cantos arredondados; stroke 2; fill "hachure" desligado (cor sólida suave). Setas sólidas = fluxo; tracejadas = devolve/resposta.

## Paleta (fundo / contorno)

| Tipo | Fundo | Contorno |
|---|---|---|
| Interface | `#dbeafe` | `#2563eb` |
| Agente / LangChain | `#dcfce7` | `#16a34a` |
| LLM / providers | `#fef9c3` | `#ca8a04` |
| Tools | `#ede9fe` | `#7c3aed` |
| Dados | `#e5e7eb` | `#6b7280` |
| Segurança | `#fee2e2` | `#dc2626` |

Grupos = retângulo grande **sem fundo**, contorno cinzento tracejado, título a negrito no canto superior esquerdo.

---

## DIAGRAMA 1 — Arquitetura geral  (esquerda → direita, 5 colunas)

Título no topo: **Arquitetura geral do Business Analytics Chatbot**. Subtítulo: *uma aplicação, vários modelos, mesma lógica de negócio*.

**Coluna 0** — `User` (elipse, sem cor).

**Grupo A — Interfaces** (coluna 1, azul)
1. `Streamlit UI` / `streamlit_app.py`
2. `CLI` / `app.py`

**Grupo B — Agente** (coluna 2, verde) — um só bloco grande
3. `run_agent()` / `agent.py` / "um só agente"
4. `Recibo + logs` / `observability.py` (mais pequeno, por baixo)

**Grupo C — Modelo (muda)** (coluna 3 topo, amarelo) — etiqueta vermelha/laranja "MUDA"
5. `get_llm()` / `providers.py`
6. `Amazon Bedrock` / `ChatBedrockConverse`
7. `Ollama local` / `ChatOllama`

**Grupo D — Tools (não mudam)** (coluna 3 fundo, roxo) — etiqueta "NÃO MUDA"
8. `get_metric_definition`
9. `get_dataset_metadata`
10. `run_postgres_query`

**Grupo E — Dados (não mudam)** (coluna 4, cinzento)
11. `semantic.yaml` / "o que significa"
12. `PostgreSQL` (cilindro) / `marketing.campaign_performance_daily`

**Segurança** (vermelho claro, entre 10 e 12)
13. `SQL guard` / `sql_guard.py`
14. `Role read-only` / `analytics_agent`

**Setas**
* User → 1; User → 2
* 1 → 3; 2 → 3 (as duas setas convergem — destaca com texto "mesmo agente")
* 3 → 5 → 6 e 5 → 7 (duas saídas de 5)
* 6 e 7 ⇢ 3 (tracejada, "tool calls")
* 3 → 8, 3 → 9, 3 → 10
* 8 → 11; 9 → 12; 10 → 13 → 14 → 12
* 3 → 4; 4 ⇢ 1 e 4 ⇢ 2 (tracejada, "resposta + recibo")

**Ordem de leitura:** User → interfaces → agente → modelo (cima) / tools (baixo) → dados.
**Destaque final:** uma moldura grossa à volta de C com a nota "troca-se aqui" e de D+E com "não se mexe".

---

## DIAGRAMA 2 — Fluxo de uma pergunta  (topo → fundo, com ciclo à direita)

Título: **Fluxo de uma pergunta no chatbot**. Subtítulo: *"Quanto gastámos ontem na Erobella?"*.

**Coluna principal (azul → verde → amarelo), de cima para baixo**
1. `1. Utilizador escreve a pergunta` (azul, elipse)
2. `2. Streamlit envia` / `streamlit_app.py` (azul)
3. `3. Histórico recente` / `history_for_agent()` / "últimas 10 msgs" (azul)
4. `4. run_agent(question, history, provider, model_id)` (verde)
5. `5. Modelo escolhido` / `get_llm()` + `bind_tools()` (amarelo)
6. `6. O modelo decide: tool ou resposta?` (amarelo, **losango**)

**Grupo "Ciclo do agente"** (moldura tracejada à direita do losango; nota "máx. MAX_MODEL_CALLS")
7. `get_metric_definition` / "gastámos = spend = SUM(cost)" (roxo)
8. `get_dataset_metadata` / "colunas e tipos" (roxo)
9. `run_postgres_query` / `SELECT SUM(cost)…` (roxo)
10. `SQL guard` (vermelho claro) entre 9 e a base de dados

**Coluna de dados à direita** (cinzento)
* `semantic.yaml` (ligado a 7)
* `Catálogo PostgreSQL` (ligado a 8)
* `PostgreSQL · role read-only` (ligado ao guard)

**Saída (de volta à coluna principal, em baixo)**
11. `11. Resposta final em PT + métrica e fonte` (amarelo)
12. `Recibo` / "tools, SQL, tokens, latência, custo, stopped_by" (verde)
13. `12. UI: resposta + Technical details` (azul)
14. `Follow-up: "E qual teve menor?"` (azul, elipse) → seta tracejada de volta a 3

**Setas**
* 1→2→3→4→5→6 (vertical, sólidas)
* 6 → 7, 6 → 8, 6 → 9 (rotular "tool"), 9 → 10 → PostgreSQL
* 7→semantic.yaml, 8→Catálogo
* Dados ⇢ 6 (tracejada, rótulo "10. resultado volta ao modelo") — desenha uma seta curva a fechar o ciclo
* 6 → 11 (rótulo "responder") → 12 → 13 → 14; 14 ⇢ 3

**Numeração:** mantém os números nos blocos; são a ordem de leitura. Anima-os um a um no slide.
**Faixa lateral opcional (swimlanes):** Utilizador/UI | Agente/Modelo | Tools | Dados, como 4 colunas verticais.

---

## DIAGRAMA 3 — LangChain interno  (topo → fundo, 3 faixas)

Título: **Como o LangChain está a ser usado neste projeto**. Subtítulo: *LangChain liga modelo + tools + contexto*.

**Faixa 1 (topo, azul):** `Escolha na UI: provider + model_id`

**Faixa 2 — grupo grande "LangChain (liga as peças)", verde**; dentro, em grelha 2×3:
* `MODEL` / `get_llm(provider, model_id, settings)` / `ChatBedrockConverse | ChatOllama`
* `PROMPT` / `SystemMessage` / `prompts/system.md`
* `MESSAGES` / `HumanMessage · AIMessage` / `history_to_messages()`
* `TOOLS` / `tool(fn)` + `bind_tools()` / "3 funções com docstring"
* `AGENT LOOP (nosso)` / "invoke → tool_calls? → ToolMessage → invoke…" (bloco maior, centro)
* `Resposta final` / `AIMessage`

Ao lado do loop: bloco vermelho claro `Limites` / `MAX_MODEL_CALLS · MAX_TOOL_CALLS · MAX_COST_PER_REQUEST` (seta tracejada para o loop).

**Faixa 3 (fundo) — grupo "Controlado pela aplicação (não pelo LangChain)", cinzento/vermelho**
* `semantic.yaml` / "define as métricas"
* `PostgreSQL` / "contém os dados"
* `SQL guard + role read-only` (vermelho claro)

**À direita da faixa 2:** `Recibo / observability` (verde) / "`usage_metadata` → tokens · `requests.jsonl`"

**Setas**
* Escolha → MODEL
* MODEL, PROMPT, MESSAGES, TOOLS → AGENT LOOP (quatro setas a convergir)
* AGENT LOOP → Resposta final → Recibo
* TOOLS ⇢ semantic.yaml ("get_metric_definition") e TOOLS ⇢ SQL guard → PostgreSQL ("run_postgres_query") — tracejadas, a atravessar a fronteira da faixa 2 para a 3 (reforça "o LangChain não conhece o negócio")

**Nota de rodapé a pôr no slide:** "Sem AgentExecutor, sem LangGraph, sem RAG. O ciclo tem ~30 linhas em `agent.py`."

---

## Sugestão de apresentação
Apresenta 1 → 2 → 3 por esta ordem: *o quê* (arquitetura), *como corre* (uma pergunta), *o que há por dentro* (LangChain).
Se tiveres pouco tempo, mostra só o 1 e o 2 e deixa o 3 como material de consulta.
