"""O STATE — o que o sistema sabe enquanto pensa.

Esta e a primeira das cinco ideias do LangGraph:

    STATE       um dicionario tipado que atravessa o grafo inteiro   <- aqui
    NODES       funcoes que recebem estado e devolvem estado         <- graph.py
    EDGES       quem corre a seguir a quem                           <- graph.py
    ROUTING     o proximo no depende do estado                       <- graph.py
    CHECKPOINTS quem guarda o estado entre turnos                    <- graph.py

Um no nunca devolve o estado inteiro. Devolve **apenas as chaves que mudou**,
e o LangGraph funde isso no estado. Por isso e que os nos sao faceis de testar
isoladamente: sao funcoes de um dicionario para um dicionario.

A chave `messages` e especial. O `Annotated[..., add_messages]` diz ao
LangGraph como fundir esta chave: em vez de substituir a lista, **acrescenta**
as mensagens novas. E essa anotacao — e nao codigo nosso — que faz o historico
crescer sozinho a cada turno.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

# As duas rotas possiveis. Hoje sao duas; quando este sistema tiver ferramentas
# (Modulo 04) serao mais, e e aqui que a lista cresce.
Route = Literal["knowledge", "chat"]


class AssistantState(TypedDict):
    """Tudo o que o assistente sabe durante uma volta de conversa."""

    # O historico. `add_messages` acumula em vez de substituir.
    messages: Annotated[list[AnyMessage], add_messages]

    # A pergunta desta volta, em texto simples. Redundante com `messages[-1]`,
    # mas ter uma chave explicita torna os nos legiveis e testaveis.
    question: str

    # A decisao do classificador. Preenchida pelo no `classify`.
    route: Route

    # Os pedacos recuperados e a sua pontuacao. Vazio se a rota for "chat".
    context: list[tuple[Document, float]]

    # Os nomes dos ficheiros citados, para mostrar na interface.
    sources: list[str]
