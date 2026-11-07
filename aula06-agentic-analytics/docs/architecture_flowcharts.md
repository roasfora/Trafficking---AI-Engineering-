# Aula 06 — Fluxogramas de arquitetura

Três diagramas para explicar o **Business Analytics Chatbot** (`aula06-agentic-analytics/`).
Os diagramas Mermaid estão em [architecture_flowcharts.mmd](architecture_flowcharts.mmd) (3 diagramas num só
ficheiro; cola cada um em <https://mermaid.live>). Para desenhar no Excalidraw, segue
[excalidraw_diagram_spec.md](excalidraw_diagram_spec.md).

> Mensagem global: **uma aplicação, vários modelos, mesma lógica de negócio.**

## Legenda de cores

| Cor | Significa | Exemplos reais |
|---|---|---|
| 🟦 Azul | Interface | `streamlit_app.py`, `app.py`, `chat.py` |
| 🟩 Verde | Agente / LangChain | `agent.py` (`run_agent`), `observability.py` |
| 🟨 Amarelo | LLM / providers | `providers.py` (`get_llm`), `ChatBedrockConverse`, `ChatOllama` |
| 🟪 Roxo | Tools (lógica) | `tools/metrics.py`, `tools/catalog.py`, `tools/postgres.py` |
| ⬜ Cinzento | Dados | `semantic.yaml`, PostgreSQL |
| 🟥 Vermelho claro | Segurança / guardrails | `tools/sql_guard.py`, role `analytics_agent`, limites do agente |

---

## Diagrama 1 — Arquitetura geral

**Blocos**

* **Interfaces:** o Streamlit (`streamlit_app.py`) e a CLI (`app.py`) são duas portas para o **mesmo** `run_agent()`.
* **`run_agent()`** (`agent.py`): o único agente. Recebe pergunta, histórico, provider e modelo.
* **`get_llm()`** (`providers.py`): constrói `ChatBedrockConverse` (nuvem) ou `ChatOllama` (local). É a única parte que muda.
* **3 tools:** `get_metric_definition` (lê `semantic.yaml`), `get_dataset_metadata` (lê o catálogo do PostgreSQL), `run_postgres_query` (passa pelo `sql_guard` e por um role só de leitura).
* **Recibo/log:** `observability.py` escreve `logs/requests.jsonl` e o recibo mostrado na UI.

1. **Objetivo pedagógico:** ver, num só quadro, o que muda (modelo) e o que não muda (tools, dados, guardrails).
2. **Em 1 minuto:** "O utilizador fala com uma de duas interfaces. Ambas chamam o mesmo agente. O agente pede ao `providers.py` um modelo — Bedrock ou Ollama — e dá-lhe três tools. As tools só tocam em dois sítios: o `semantic.yaml` e o PostgreSQL, e o SQL passa sempre por um guarda e por um utilizador só de leitura. Trocar de modelo não toca em nada disto."
3. **Erros comuns:** achar que o LLM acede à base de dados (só as tools acedem); achar que o Streamlit tem lógica de negócio (não tem: só mostra); achar que a CLI é um agente à parte (é o mesmo).
4. **Mensagem-chave:** *o modelo é um componente substituível; a governança está à volta dele.*

---

## Diagrama 2 — Fluxo de uma pergunta

Exemplo: *"Quanto gastámos ontem na Erobella?"* (esperado: 426,28 €, com `AS_OF_DATE=2026-11-06`).

**Blocos (por ordem)**

1. O utilizador escreve. 2. O Streamlit recebe. 3. `chat.history_for_agent()` junta as últimas mensagens (só texto, máx. 10).
4. `run_agent(question, history, provider, model_id)`. 5. O modelo escolhido recebe as 3 tools (`bind_tools`).
6. O modelo decide: chamar uma tool ou responder. 7. `get_metric_definition("gastámos")` → `spend = SUM(cost)`.
8. `get_dataset_metadata` (opcional) → colunas e tipos. 9. `run_postgres_query` → `check_sql()` → PostgreSQL.
10. Cada resultado volta ao modelo. 11. Resposta final em PT com métrica e fonte. 12. A UI mostra resposta + *Technical details*
(tools usadas, SQL, tokens, latência, custo estimado, `stopped_by`).

O ciclo 6→10 repete-se até o modelo responder ou até um limite (`MAX_MODEL_CALLS`, `MAX_TOOL_CALLS`, `MAX_COST_PER_REQUEST`).
Num *follow-up* ("E qual teve menor?") o histórico volta ao passo 3.

1. **Objetivo pedagógico:** mostrar que a resposta **sai das tools**, não da cabeça do modelo.
2. **Em 1 minuto:** "A pergunta entra com o histórico. O modelo não sabe o que é 'gastámos': pede a definição ao `semantic.yaml`. Depois escreve um SELECT, o guarda valida-o e o PostgreSQL devolve um número. O modelo só redige a frase. No fim há um recibo com tudo o que aconteceu."
3. **Erros comuns:** pensar que o histórico dá números ao modelo (serve só para entender a pergunta; ele deve voltar a consultar); pensar que o recibo é opcional (é o que permite comparar modelos); esquecer que o ciclo tem limites.
4. **Mensagem-chave:** *o LLM não responde sozinho; usa tools governadas.*

---

## Diagrama 3 — Como o LangChain é usado

Conceitos do LangChain que **existem** neste projeto:

| Conceito | No código |
|---|---|
| Model | `get_llm()` → `ChatBedrockConverse` / `ChatOllama` |
| Prompt | `SystemMessage` com `prompts/system.md` (ou `system_naive.md`) |
| Messages | `HumanMessage` / `AIMessage` / `ToolMessage`; `history_to_messages()` |
| Tools | `tool(get_metric_definition)` etc. + `bind_tools()` |
| Agent loop | o ciclo `while` em `run_agent()` (explícito, **nosso**) |
| Receipt | `usage_metadata` do `AIMessage` → `observability.py` |

Não existem: `AgentExecutor`, LangGraph, *structured output* no agente, RAG. O Pydantic só aparece no `DashboardSpec` (`dashboard/spec.py`).

**Separação de responsabilidades:** LangChain orquestra modelo + tools; `semantic.yaml` define as métricas; o PostgreSQL guarda os dados; a aplicação controla o contexto, os limites e a segurança.

1. **Objetivo pedagógico:** desmistificar "agente": é um ciclo de 30 linhas à volta de um modelo com tools.
2. **Em 1 minuto:** "O LangChain dá-nos quatro peças: modelo, mensagens, tools e a forma de as ligar. O ciclo é nosso, para os limites ficarem à vista. As métricas não estão no LangChain, estão num YAML; os dados não estão no LangChain, estão no PostgreSQL."
3. **Erros comuns:** achar que o LangChain 'é' o agente; achar que o LangChain conhece o negócio; confundir `bind_tools` (dizer ao modelo que tools existem) com executá-las (quem executa é o nosso ciclo).
4. **Mensagem-chave:** *LangChain é a camada que liga modelo + tools + contexto.*

---

## Referência: funções e o que é LangChain

> O pacote `langchain` está no `requirements.txt`, mas nenhum ficheiro o importa. Usamos só `langchain-core`,
> `langchain-aws` e `langchain-ollama`. Não há `AgentExecutor`, LangGraph, chains, retrievers nem structured output.

### O que vem do LangChain

| Peça LangChain | Onde é usada | Para quê |
|---|---|---|
| `ChatBedrockConverse` (`langchain_aws`) | `providers.get_llm()` | Modelo na nuvem (Bedrock) |
| `ChatOllama` (`langchain_ollama`) | `providers.get_llm()` | Modelo local |
| `BaseChatModel` (`langchain_core`) | tipo de retorno de `get_llm()` | Os dois modelos têm a mesma interface |
| `tool(fn)` | `agent.ALL_TOOLS` | Transforma uma função Python numa tool. A *docstring* é a descrição que o modelo lê e os *type hints* viram o schema |
| `.bind_tools(tools)` | `run_agent()` | Diz ao modelo que tools existem |
| `.invoke(messages)` | `run_agent()`, `explain()` | Uma chamada ao modelo |
| `SystemMessage`, `HumanMessage`, `AIMessage`, `ToolMessage` | `run_agent()`, `history_to_messages()` | O formato da conversa |
| `ai.tool_calls` | `run_agent()` | O modelo pede uma tool (nome, argumentos e id) |
| `ai.usage_metadata` | `_add_usage()` | Tokens de entrada e saída, que alimentam o recibo |
| `StructuredTool.invoke(args)` | `_run_tool()` | Executa a tool pedida |

### O que é nosso, por ficheiro

**`providers.py`** (a fronteira com o modelo)

* `get_llm(provider, model_id, settings)`: escolhe `ChatBedrockConverse` ou `ChatOllama`; recusa providers desconhecidos e model ids vazios.
* `with_model()`: devolve as settings para esse modelo e retira os preços se o modelo não for o default do `.env`.
* `bedrock_models()`, `discover_ollama_models()`, `aws_credentials_found()`: alimentam a sidebar; não usam LangChain.

**`agent.py`** (o agente)

* `run_agent(question, history, provider, model_id, …)`: o ciclo. Monta as mensagens, chama o modelo e, enquanto houver `tool_calls`,
  executa as tools e devolve os `ToolMessage` ao modelo. Pára ao responder ou ao atingir um limite
  (`max_model_calls`, `max_tool_calls`, `max_cost`). Devolve a resposta e o recibo, e escreve no log (também em caso de erro).
* `build_system_prompt()`: lê `prompts/system.md` (ou `system_naive.md`) e injeta "hoje" e "ontem".
* `history_to_messages()`: converte o histórico em `HumanMessage` e `AIMessage` (últimas 10).
* `_run_tool()`: executa a tool pedida; tools desconhecidas ou com erro voltam ao modelo como erro.
* `_add_usage()` e `_text()`: leem os tokens e o texto da resposta.

**As 3 tools** (funções simples, sem LangChain lá dentro; só `agent.py` as embrulha com `tool()`)

* `get_metric_definition()` (`tools/metrics.py`): lê o `semantic.yaml` e devolve a expressão SQL da métrica.
* `get_dataset_metadata()` (`tools/catalog.py`): lê colunas, tipos e comentários do PostgreSQL (com cache).
* `run_postgres_query()` (`tools/postgres.py`): valida com `check_sql()` (`tools/sql_guard.py`) e executa com o role só de leitura.
  Se o guard recusar, o erro volta ao modelo para ele corrigir.

**Fora do ciclo LangChain**

* `chat.py`: guarda o histórico, traduz erros e filtra os detalhes mostrados na UI.
* `observability.py`: `estimate_model_cost()`, `log_request()`, `format_receipt()`.
* `workflows/diagnose_metric_drop.py`: `explain()` é a única chamada ao modelo; é opcional e sem tools.
* `dashboard/spec.py`: o `DashboardSpec` usa Pydantic, não LangChain.

### Fluxo de uma chamada

```text
get_llm() → .bind_tools([3 tools]) → .invoke([System, *history, Human])
   → AIMessage com tool_calls? → _run_tool() → ToolMessage → .invoke(...) …
   → AIMessage sem tool_calls = resposta final → usage_metadata → recibo
```

---

## Notas e limitações

* Não existe `create_business_agent`: a função real é `run_agent()` em `agent.py`.
* O dashboard (`dashboard/spec.py`) e o workflow `diagnose_metric_drop` são **fora do agente** (sem LLM, ou com 1 chamada opcional); por isso não estão nos 3 diagramas. Podes acrescentá-los como caixas extra ao lado das tools.
* O `.mmd` contém 3 diagramas num ficheiro, por isso não abre como um único diagrama: copia um bloco de cada vez.
* Os diagramas Mermaid não foram renderizados aqui (sem ferramenta de render); verifica-os em mermaid.live.
