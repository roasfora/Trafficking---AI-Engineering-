"""SQL guard: valida o SQL que o modelo escreveu ANTES de ir ao PostgreSQL.

Usa o parser do sqlglot (arvore sintatica), nao regex. O guard devolve o SQL
REGENERADO a partir da arvore: o que foi verificado e exatamente o que corre.

Regras
    1. so SELECT (com ou sem WITH, ou UNION de SELECTs)
    2. uma unica statement
    3. nada de DDL/DML/COPY/GRANT/... em nenhum ponto da arvore (nem dentro de CTEs)
    4. so a tabela analytics.campaign_performance_daily (ou CTEs visiveis)
    5. funcoes desconhecidas (pg_sleep, pg_read_file, lo_import...) sao recusadas
    6. tamanho maximo e LIMIT maximo
O PostgreSQL ainda acrescenta: role read-only + statement_timeout.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

ALLOWED_TABLES = {("analytics", "campaign_performance_daily")}

# Funcoes que o sqlglot nao conhece (Anonymous) mas sao inofensivas.
ALLOWED_ANONYMOUS_FUNCTIONS = {"to_char", "greatest", "least"}

FORBIDDEN_NODES = tuple(
    getattr(exp, name)
    for name in (
        "Insert", "Update", "Delete", "Drop", "Alter", "Create", "TruncateTable",
        "Copy", "Merge", "Grant", "Revoke", "Command", "Set", "Use", "Into", "Lock",
    )
    if hasattr(exp, name)
)


class SqlRejected(ValueError):
    """O SQL viola uma regra do guard. A mensagem diz qual (o modelo le-a)."""


def check_sql(sql: str, max_rows: int = 200, max_length: int = 2000) -> str:
    """Valida `sql`; devolve o SQL seguro (com LIMIT garantido) ou levanta SqlRejected."""
    if len(sql) > max_length:
        raise SqlRejected(f"query longer than {max_length} characters")

    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except SqlglotError as exc:
        raise SqlRejected(f"cannot parse SQL: {str(exc).splitlines()[0]}") from exc

    if len(statements) != 1:
        raise SqlRejected("exactly one statement is allowed")
    root = statements[0]

    if not isinstance(root, (exp.Select, exp.Union)):
        raise SqlRejected("only SELECT queries are allowed")

    for node in root.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise SqlRejected(f"{type(node).__name__.upper()} is not allowed")
        if isinstance(node, exp.Anonymous) and str(node.this).lower() not in ALLOWED_ANONYMOUS_FUNCTIONS:
            raise SqlRejected(f"function {str(node.this).lower()}() is not allowed")
        if isinstance(node, exp.Table):
            _check_table(node)

    _apply_limit(root, max_rows)
    return root.sql(dialect="postgres")


def _check_table(table: exp.Table) -> None:
    if not isinstance(table.this, exp.Identifier):
        raise SqlRejected("table functions are not allowed")
    name, schema, catalog = table.name, table.db, table.catalog
    if catalog:
        raise SqlRejected(f"unknown catalog '{catalog}'")
    if schema:
        if (schema, name) not in ALLOWED_TABLES:
            raise SqlRejected(f"table {schema}.{name} is not allowed")
        return
    # Sem schema: so pode ser um CTE VISIVEL neste ponto da query.
    if name not in _visible_ctes(table):
        raise SqlRejected(f"table '{name}' is not allowed (use analytics.campaign_performance_daily)")


def _visible_ctes(table: exp.Table) -> set[str]:
    """Nomes de CTE que um PostgreSQL resolveria para esta referencia.

    Subir pela arvore: cada WITH num ancestral e visivel no corpo desse ancestral.
    Dentro da definicao de um CTE so se veem os CTEs anteriores (e ele proprio se
    for RECURSIVE). Um CTE definido num ramo irmao NAO e visivel: sem esta regra,
    `(WITH pg_shadow AS (SELECT 1) SELECT 1), pg_shadow` passava a allowlist.
    """
    visible: set[str] = set()
    child: exp.Expression = table
    node = table.parent
    while node is not None:
        with_ = node.args.get("with") or node.args.get("with_")
        if with_ is not None:
            ctes = with_.expressions
            if child is with_:
                # estamos numa definicao de CTE: ver quais vieram antes
                position = next(i for i, cte in enumerate(ctes) if _contains(cte, table))
                visible |= {c.alias for c in ctes[:position]}
                if with_.args.get("recursive"):
                    visible.add(ctes[position].alias)
            else:
                visible |= {c.alias for c in ctes}
        child, node = node, node.parent
    return visible


def _contains(ancestor: exp.Expression, node: exp.Expression) -> bool:
    return any(a is ancestor for a in _ancestors(node))


def _ancestors(node: exp.Expression):
    node = node.parent
    while node is not None:
        yield node
        node = node.parent


def _apply_limit(root: exp.Expression, max_rows: int) -> None:
    """Garante LIMIT <= max_rows no nivel de topo."""
    limit = root.args.get("limit")
    if limit is not None:
        value = limit.expression
        if isinstance(value, exp.Literal) and value.is_int and int(value.name) <= max_rows:
            return
    root.set("limit", exp.Limit(expression=exp.Literal.number(max_rows)))
