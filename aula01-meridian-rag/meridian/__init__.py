"""Meridian AI Assistant.

Um assistente RAG sobre a documentacao interna da Meridian Digital,
a correr inteiramente na tua maquina: Ollama + LangChain + LangGraph + Streamlit.

A anatomia do projeto, por ordem de leitura:

    config.py      o que muda entre maquinas
    models.py      A FRONTEIRA DO PROVIDER - o unico ficheiro que conhece o Ollama
    knowledge.py   documentos -> pedacos -> vetores -> indice  (a parte "R" do RAG)
    prompts.py     as instrucoes que damos ao modelo
    state.py       o que o sistema sabe enquanto pensa  (o "state" do LangGraph)
    graph.py       os nos, as arestas e o routing        (o "graph" do LangGraph)
    ../app.py      a interface em Streamlit

A Meridian Digital e uma empresa FICTICIA. Todos os documentos em data/docs
foram inventados para efeitos de formacao.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
