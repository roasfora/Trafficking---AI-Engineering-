"""semantic.yaml -> Documents. Nao escrevemos documentos de metricas a mao.

    semantic.yaml (fonte unica) -> Document (um por metrica) -> pgvector

Assim a definicao de CPC que o RAG recupera e EXATAMENTE a que a tool
get_metric_definition devolve: se alguem mudar o yaml, muda nos dois sitios
(depois de voltar a correr `python -m rag.index`).
"""

from __future__ import annotations

from langchain_core.documents import Document

from tools.metrics import load_semantic, one_line


def metric_documents() -> list[Document]:
    docs = []
    for key, metric in load_semantic()["metrics"].items():
        name = key.upper()
        lines = [
            # Cabecalho PT/EN so para o embedding encontrar a metrica quando se pergunta
            # "o que e CPC?" ou "what is CPC?". O resto vem tal e qual do yaml.
            f"{name} - {metric['label']}. Definition of {name}: what is {name}? O que é {name}?",
            f"Description: {metric['description']}",
            f"Formula (PostgreSQL): {one_line(metric['expression'])}",
            f"Unit: {metric['unit']}",
        ]
        if metric.get("synonyms"):
            lines.append("Also known as: " + ", ".join(metric["synonyms"]))
        if metric.get("never"):
            lines.append("Never compute it as: " + "; ".join(metric["never"]))
        docs.append(
            Document(
                page_content="\n".join(lines),
                metadata={"source": "semantic.yaml", "doc_type": "metric_definition", "metric": key},
            )
        )
    return docs
