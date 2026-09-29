"""O GRAFO — nos, arestas, routing e memoria.

Isto e o coracao do projeto. Um chatbot simples e uma linha reta:

    pergunta -> modelo -> resposta

O nosso sistema nao e uma linha reta:

    pergunta
       |
    classify            <- o modelo decide o caminho
       |
    precisa da base de conhecimento?
       |                        |
      sim                      nao
       |                        |
    retrieve                    |
       |                        |
       +--------> generate <----+
                     |
                  resposta

Tem um ramo e uma decisao. Um `if/else` dentro de uma funcao aguentava isto
durante duas semanas. Depois disso — quando aparecem ferramentas, ciclos de
retry e aprovacao humana — precisas de uma maquina de estados explicita.
E disso que o LangGraph trata.

As cinco ideias, e onde estao neste ficheiro:

    STATE       -> state.py
    NODES       -> node_classify, node_retrieve, node_generate
    EDGES       -> add_edge
    ROUTING     -> route_question + add_conditional_edges
    CHECKPOINTS -> InMemorySaver, no fim do ficheiro
"""

from __future__ import annotations

from typing import Iterator

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.vectorstores import VectorStore
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from meridian.config import Settings, settings
from meridian.knowledge import format_context, search
from meridian.models import get_chat_model
from meridian.prompts import CHAT_SYSTEM, RAG_SYSTEM, ROUTER_SYSTEM
from meridian.state import AssistantState

# Palavras que, se aparecerem na pergunta, indicam quase de certeza que a
# resposta esta na documentacao interna. Usadas apenas como rede de seguranca
# quando o classificador do modelo falha ou devolve algo inesperado.
_PALAVRAS_INTERNAS = (
    "meridian", "northline", "kessler", "vela", "campanha", "cpa", "roas",
    "ctr", "ngr", "budget", "compliance", "criativo", "onboarding", "cliente",
    "politica", "processo", "tracking", "q3", "trimestre", "frequency",
)


# ===========================================================================
# NOS  —  cada no e uma funcao: recebe estado, devolve as chaves que mudou
# ===========================================================================


def make_node_classify(llm: BaseChatModel):
    """Nó 1 — decide o caminho.

    Este e o no mais interessante da aula, porque e o primeiro sitio onde o
    modelo deixa de gerar texto e passa a **tomar uma decisao de controlo de
    fluxo**. E o embriao de um agente: a diferenca entre um workflow e um
    agente e apenas quantas destas decisoes entregas ao modelo.

    Chamamos o modelo com uma temperatura de 0 e um prompt minimo. Se a
    resposta nao for uma das rotas conhecidas, caimos numa heuristica de
    palavras-chave. Em producao isto chamar-se-ia "graceful degradation";
    numa aula chama-se "o que fazes quando o classificador falha".
    """

    def node_classify(state: AssistantState) -> dict:
        question = state["question"]

        try:
            resposta = llm.invoke(
                [
                    SystemMessage(content=ROUTER_SYSTEM),
                    HumanMessage(
                        content=(
                            f"Mensagem do utilizador:\n{question}\n\n"
                            'Responde com uma unica palavra: "knowledge" ou "chat".'
                        )
                    ),
                ]
            )
            texto = str(resposta.content).strip().lower()
            route = "knowledge" if "knowledge" in texto else "chat" if "chat" in texto else None
        except Exception:  # noqa: BLE001 - o classificador nunca deve derrubar a app
            route = None

        if route is None:
            pergunta_lower = question.lower()
            route = (
                "knowledge"
                if any(p in pergunta_lower for p in _PALAVRAS_INTERNAS)
                else "chat"
            )

        return {"route": route}

    return node_classify


def make_node_retrieve(store: VectorStore, config: Settings):
    """Nó 2 — vai buscar os pedacos relevantes.

    Nao ha modelo de linguagem aqui. E aritmetica sobre vetores: a pergunta
    vira um vetor e comparamos com os vetores do indice.

    Repara que este no so preenche o estado. Nao decide nada e nao gera nada.
    Nos pequenos e com uma responsabilidade so sao faceis de testar, de
    substituir (hoje InMemory, amanha pgvector) e de instrumentar.
    """

    def node_retrieve(state: AssistantState) -> dict:
        resultados = search(store, state["question"], config)
        fontes = []
        for doc, _score in resultados:
            fonte = doc.metadata.get("source", "desconhecido")
            if fonte not in fontes:
                fontes.append(fonte)
        return {"context": resultados, "sources": fontes}

    return node_retrieve


def make_node_generate(llm: BaseChatModel, config: Settings):
    """Nó 3 — escreve a resposta.

    Duas coisas acontecem aqui, e vale a pena separa-las na explicacao:

    1. **Montagem do prompt.** O system prompt muda consoante a rota: com
       excertos ("responde so com base nisto") ou sem ("nao inventes dados da
       empresa"). O mesmo modelo, dois comportamentos.

    2. **A memoria.** Reenviamos as ultimas N mensagens do historico. O modelo
       nao tem memoria nenhuma — a conversa existe porque nos a reenviamos.
       O corte e a estrategia mais simples que existe: quando a conversa
       cresce, as mensagens mais antigas caem. Em producao, isto vira
       sumarizacao ou memoria seletiva.
    """

    def node_generate(state: AssistantState) -> dict:
        if state.get("route") == "knowledge":
            system = RAG_SYSTEM.format(context=format_context(state.get("context") or []))
        else:
            system = CHAT_SYSTEM

        # `messages` ja inclui a pergunta desta volta, acrescentada por
        # `add_messages` quando invocamos o grafo. Cortamos as mais antigas.
        historico = state["messages"][-config.max_history_messages :]

        resposta = llm.invoke([SystemMessage(content=system), *historico])

        # Devolvemos so a chave que mudou. `add_messages` acrescenta a resposta
        # ao historico — nao substitui a lista.
        return {"messages": [AIMessage(content=resposta.content)]}

    return node_generate


# ===========================================================================
# ROUTING  —  a funcao que escolhe a proxima aresta
# ===========================================================================


def route_question(state: AssistantState) -> str:
    """Le o estado e devolve o nome do proximo no.

    Isto e uma aresta condicional. Nao chama o modelo, nao gera nada: e uma
    funcao pura sobre o estado. E, por isso, trivial de testar.
    """
    return "retrieve" if state.get("route") == "knowledge" else "generate"


# ===========================================================================
# CONSTRUCAO DO GRAFO
# ===========================================================================


def build_graph(
    store: VectorStore,
    config: Settings | None = None,
    *,
    llm: BaseChatModel | None = None,
    router_llm: BaseChatModel | None = None,
    checkpointer: InMemorySaver | None = None,
) -> CompiledStateGraph:
    """Monta e compila o grafo.

    Repara na estrutura: declaramos os nos, declaramos as ligacoes, e
    compilamos. O grafo e uma **descricao** do sistema, separada da execucao —
    e e por isso que o LangGraph consegue desenha-lo, retomar a meio, e
    fazer streaming por no.
    """
    config = config or settings

    if llm is None:
        llm = get_chat_model(config)
        # Um segundo handle para o mesmo modelo, so para classificar, com
        # temperatura 0. Classificar nao e sitio para criatividade: queremos a
        # mesma pergunta a dar sempre a mesma rota. Nao carrega um segundo
        # modelo para memoria — muda so os parametros de sampling.
        router_llm = router_llm or get_chat_model(config, temperature=0.0)

    router_llm = router_llm or llm

    builder = StateGraph(AssistantState)

    # --- NOS ---
    builder.add_node("classify", make_node_classify(router_llm))
    builder.add_node("retrieve", make_node_retrieve(store, config))
    builder.add_node("generate", make_node_generate(llm, config))

    # --- ARESTAS ---
    builder.add_edge(START, "classify")

    # A aresta condicional: o caminho depende do estado.
    builder.add_conditional_edges(
        "classify",
        route_question,
        {"retrieve": "retrieve", "generate": "generate"},
    )

    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", END)

    # --- CHECKPOINTS ---
    # O checkpointer guarda o estado depois de cada no, indexado por
    # `thread_id`. E isto — e nao codigo nosso — que da memoria a conversa
    # entre turnos, e o que tornara possivel pausar para uma pessoa aprovar
    # (human-in-the-loop) quando este sistema crescer.
    #
    # `InMemorySaver` perde tudo quando o processo morre. Em producao trocas
    # por `SqliteSaver` ou `PostgresSaver` — mesma interface, uma linha.
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


# ===========================================================================
# INVOCACAO  —  o que a interface chama
# ===========================================================================


def ask(graph: CompiledStateGraph, question: str, thread_id: str) -> dict:
    """Uma volta completa. Devolve o estado final.

    O `thread_id` e o identificador da conversa. Duas threads diferentes tem
    historicos independentes; a mesma thread continua de onde ficou. E assim
    que se serve varios utilizadores com um so grafo.
    """
    return graph.invoke(
        {"messages": [HumanMessage(content=question)], "question": question},
        config={"configurable": {"thread_id": thread_id}},
    )


def stream_answer(
    graph: CompiledStateGraph, question: str, thread_id: str
) -> Iterator[str]:
    """A mesma volta, mas devolve a resposta token a token.

    `stream_mode="messages"` emite cada pedaco gerado por qualquer no que
    chame um modelo. Filtramos pelo no `generate` para nao mostrar ao
    utilizador a saida do classificador.
    """
    for mensagem, metadados in graph.stream(
        {"messages": [HumanMessage(content=question)], "question": question},
        config={"configurable": {"thread_id": thread_id}},
        stream_mode="messages",
    ):
        if metadados.get("langgraph_node") != "generate":
            continue
        texto = getattr(mensagem, "content", "")
        if texto:
            yield texto


def get_last_state(graph: CompiledStateGraph, thread_id: str) -> dict:
    """Le o estado guardado pelo checkpointer.

    Util na interface para mostrar que rota foi tomada e que fontes foram
    citadas — e util em producao para depurar o que o sistema estava a pensar.
    """
    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    return snapshot.values if snapshot else {}
