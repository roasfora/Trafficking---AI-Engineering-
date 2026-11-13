-- Defesa em profundidade: mesmo que o SQL guard falhe, o PostgreSQL recusa.
-- Passwords so para dev local. Nada de segredos reais.

-- Agente SQL: so le UMA tabela de analytics. Sem acesso a raw nem a knowledge.
CREATE ROLE analytics_agent LOGIN PASSWORD 'agent_dev';
ALTER ROLE analytics_agent SET default_transaction_read_only = on;
ALTER ROLE analytics_agent SET statement_timeout = '5s';
GRANT CONNECT ON DATABASE analytics TO analytics_agent;
GRANT USAGE ON SCHEMA analytics TO analytics_agent;
GRANT SELECT ON analytics.campaign_performance_daily TO analytics_agent;

-- Retriever RAG: so le o vector store (schema knowledge). Sem acesso a dados de analytics.
CREATE ROLE knowledge_reader LOGIN PASSWORD 'reader_dev';
ALTER ROLE knowledge_reader SET default_transaction_read_only = on;
GRANT CONNECT ON DATABASE analytics TO knowledge_reader;
GRANT USAGE ON SCHEMA knowledge TO knowledge_reader;
GRANT USAGE ON SCHEMA public TO knowledge_reader;   -- o tipo vector vive em public
-- As tabelas do vector store so existem depois de `python -m rag.index` (corre como o dono):
ALTER DEFAULT PRIVILEGES FOR ROLE analytics IN SCHEMA knowledge GRANT SELECT ON TABLES TO knowledge_reader;
