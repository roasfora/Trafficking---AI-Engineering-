-- Tres schemas, tres papeis:
--   raw        dados que imitam as APIs dos providers (contratos reais, subconjunto)
--   analytics  modelo canonico normalizado (e a UNICA coisa que o agente consulta por SQL)
--   knowledge  vector store (pgvector) para RAG sobre conhecimento interno
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA raw;
CREATE SCHEMA analytics;
CREATE SCHEMA knowledge;

COMMENT ON SCHEMA raw IS 'Provider API payloads, as delivered (Erobella, TrafficJunky, Voluum). Never queried by the agent.';
COMMENT ON SCHEMA analytics IS 'Canonical normalized model. The only schema the SQL agent can read.';
COMMENT ON SCHEMA knowledge IS 'pgvector store with internal knowledge chunks (RAG). Not a source of numeric facts.';
