# Business glossary

> Documento sintético, para fins pedagógicos.

## Termos básicos

- **Impressions**: número de vezes que um anúncio foi mostrado.
- **Clicks**: número de cliques no anúncio.
- **Conversions**: número de ações de valor (compra, registo, lead) atribuídas a uma campanha.
- **Revenue**: receita atribuída às conversões, em EUR.
- **Spend** (ou cost): o que pagámos pelo tráfego, em EUR.

## Rácios

- **CPC** (cost per click) = spend / clicks.
- **CTR** (click-through rate) = clicks / impressions, em percentagem.
- **CR** (conversion rate) = conversions / clicks, em percentagem. Nesta PoC o denominador são os *cliques*, não as visitas.
- **CPA** (cost per acquisition) = spend / conversions.
- **ROAS** (return on ad spend) = revenue / spend. ROAS 1.5 significa 1,50 EUR de receita por cada 1 EUR gasto.

## Ratio of sums

Todos os rácios calculam-se como **soma / soma** (ratio of sums):

    CPC = SUM(cost) / SUM(clicks)

Nunca se faz a média dos rácios diários ou por campanha: **não usar AVG(cpc), AVG(ctr) nem AVG(cr)**.

Porquê? Uma média de rácios dá o mesmo peso a um dia com 12 cliques e a um dia com 12 000 cliques.
Exemplo: dia A tem custo 10 e 100 cliques (CPC 0,10); dia B tem custo 500 e 1 000 cliques (CPC 0,50).
A média dos CPC dá 0,30, mas o CPC real do período é 510 / 1 100 = 0,46.
