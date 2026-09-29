"""A base de conhecimento — o "R" de RAG.

RAG tem duas fases, e este ficheiro contem a primeira inteira:

    FASE 1 · INDEXAR   (offline, uma vez)
        ficheiros -> Documents -> pedacos -> vetores -> indice em disco

    FASE 2 · CONSULTAR (a cada pergunta, em graph.py)
        pergunta -> vetor -> os k pedacos mais proximos -> prompt

Noventa por cento da dificuldade de um sistema RAG esta na fase 1: como partir
os documentos, o que fazer com tabelas e PDFs, como lidar com versoes,
permissoes e documentos que se contradizem. Nao e a parte glamorosa. E a parte
onde os projetos morrem.

Neste projeto usamos o `InMemoryVectorStore` do LangChain: guarda os vetores
num dicionario em memoria e sabe gravar-se num ficheiro JSON. Chega
perfeitamente para 10 documentos e tem a vantagem pedagogica de nao esconder
nada. Em producao, a mesma interface (`VectorStore`) e implementada por
pgvector, Chroma, Weaviate, OpenSearch — troca-se a classe e o resto do
codigo nao muda.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

from meridian.config import Settings, settings
from meridian.models import get_embeddings


# ---------------------------------------------------------------------------
# FASE 1 — indexacao
# ---------------------------------------------------------------------------


def load_documents(config: Settings | None = None) -> list[Document]:
    """Le os ficheiros markdown e transforma-os em `Document`.

    Um `Document` do LangChain sao duas coisas:
        - `page_content`: o texto
        - `metadata`: tudo o resto (fonte, titulo, data, permissoes...)

    Os metadados nao sao decoracao. Sao o que permite citar a fonte na
    resposta, filtrar por cliente ou por data, e aplicar permissoes.
    Um RAG sem metadados uteis e um RAG que nao consegues auditar.
    """
    config = config or settings
    documents: list[Document] = []

    for path in sorted(config.docs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        # A primeira linha `# ...` serve de titulo legivel.
        title = next(
            (line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("# ")),
            path.stem,
        )
        documents.append(
            Document(
                page_content=text,
                metadata={"source": path.name, "title": title},
            )
        )

    return documents


def split_documents(
    documents: list[Document],
    config: Settings | None = None,
) -> list[Document]:
    """Parte cada documento em pedacos que caibam no prompt.

    Porque nao enviar o documento inteiro? Porque a janela de contexto e
    finita, porque texto irrelevante piora a resposta, e porque queremos
    recuperar *a passagem certa*, nao *o ficheiro certo*.

    O `RecursiveCharacterTextSplitter` tenta cortar pelos separadores mais
    naturais primeiro — paragrafos, depois linhas, depois frases, depois
    palavras — e so parte a meio de uma palavra em ultimo recurso.

    O `chunk_overlap` faz os pedacos sobreporem-se um pouco, para que uma
    frase que caia exatamente na fronteira nao fique orfa dos dois lados.
    """
    config = config or settings
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""],
        add_start_index=True,
    )
    return splitter.split_documents(documents)


def build_index(config: Settings | None = None, *, verbose: bool = False) -> InMemoryVectorStore:
    """Corre a fase 1 completa e grava o indice em disco.

    O passo caro e o `add_documents`: cada pedaco passa pelo modelo de
    embeddings e sai de la um vetor de 768 numeros. Com 10 documentos demora
    segundos. Com 40 000 documentos internos, isto e um pipeline agendado —
    e ai ja se chama data engineering.
    """
    config = config or settings

    documents = load_documents(config)
    chunks = split_documents(documents, config)

    if verbose:
        print(f"  {len(documents)} documentos -> {len(chunks)} pedacos")

    store = InMemoryVectorStore(embedding=get_embeddings(config))
    store.add_documents(chunks)

    config.index_path.parent.mkdir(parents=True, exist_ok=True)
    store.dump(str(config.index_path))

    if verbose:
        size_kb = config.index_path.stat().st_size / 1024
        print(f"  indice gravado em {config.index_path} ({size_kb:.0f} KB)")

    return store


def load_index(config: Settings | None = None) -> InMemoryVectorStore:
    """Carrega o indice do disco. Se nao existir, constroi-o."""
    config = config or settings
    if not config.index_path.exists():
        return build_index(config)
    return InMemoryVectorStore.load(str(config.index_path), get_embeddings(config))


def index_exists(config: Settings | None = None) -> bool:
    return (config or settings).index_path.exists()


# ---------------------------------------------------------------------------
# FASE 2 — consulta
# ---------------------------------------------------------------------------


def search(
    store: InMemoryVectorStore,
    question: str,
    config: Settings | None = None,
) -> list[tuple[Document, float]]:
    """Os k pedacos mais proximos da pergunta, com a pontuacao de semelhanca.

    E so isto. A pergunta vira um vetor pelo mesmo modelo de embeddings, e
    comparamos esse vetor com todos os vetores do indice. Nao ha magia, nao ha
    modelo a "procurar" — ha aritmetica sobre vetores.

    Devolvemos a pontuacao de proposito: numa aula, ver que a resposta certa
    tem 0.82 e o ruido tem 0.31 explica mais do que qualquer slide. E em
    producao, a pontuacao e o que te permite dizer "nao encontrei nada
    relevante" em vez de responder com lixo.
    """
    config = config or settings
    return store.similarity_search_with_score(question, k=config.top_k)


def format_context(results: list[tuple[Document, float]]) -> str:
    """Transforma os pedacos recuperados no bloco de texto que vai no prompt.

    Numerar as fontes nao e cosmetico: e o que permite pedir ao modelo que
    cite `[1]`, `[2]`, e ao utilizador verificar de onde veio a resposta.
    Uma resposta que nao se consegue verificar nao serve para trabalho.
    """
    blocos = []
    for i, (doc, _score) in enumerate(results, start=1):
        fonte = doc.metadata.get("source", "desconhecido")
        titulo = doc.metadata.get("title", "")
        blocos.append(f"[{i}] {titulo} · ficheiro: {fonte}\n{doc.page_content.strip()}")
    return "\n\n---\n\n".join(blocos)
