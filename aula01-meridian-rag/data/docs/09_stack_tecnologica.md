<!--
DOCUMENTO SINTÉTICO — material de formação.
A Meridian Digital é uma empresa fictícia. Nenhum dado neste ficheiro é real.
-->

# Stack tecnológica

> Documento interno · v5 · atualizado em 2026-09-20 · dono: Data & Tracking

## Plataformas de media

Meta Ads Manager, Google Ads, TikTok Ads Manager, DV360 (apenas Northline Media).

## Dados

| Camada | Ferramenta | Notas |
|---|---|---|
| Ingestão | Fivetran | conectores de Meta, Google e TikTok |
| Armazenamento | BigQuery | dataset `meridian_prod`, retenção de 26 meses |
| Transformação | dbt | modelos em `analytics/models` |
| Visualização | Looker Studio | dashboards por cliente |
| Tracking server-side | GTM Server + Conversions API | um contentor por cliente |

## Operações

- **Linear** — tarefas, incidentes e alterações de budget.
- **Frame.io** — revisão e aprovação de criativos.
- **Notion** — documentação interna e briefs.
- **Slack** — canais por cliente, com o prefixo `#cli-`.

## Regras de acesso

- Acesso a dados de cliente exige aprovação do gestor de conta.
- Credenciais de plataforma vivem no 1Password, nunca em documentos ou mensagens.
- Nenhum dado de cliente sai do BigQuery para ferramentas externas sem parecer de
  Compliance. Isto inclui ferramentas de IA generativa.

## Nota sobre IA

Em setembro de 2026 abrimos uma exceção controlada: modelos executados **localmente**
podem processar documentação interna, porque nenhum dado sai da máquina. Ferramentas
de IA em cloud continuam a exigir parecer caso a caso.
