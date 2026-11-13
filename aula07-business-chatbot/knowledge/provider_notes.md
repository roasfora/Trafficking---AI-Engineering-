# Provider notes

> Notas sintéticas e pedagógicas sobre diferenças entre providers. Não são documentação oficial dos providers.

## Diferenças gerais

- **Timezone**: Erobella reporta dias em UTC. O TrafficJunky reporta no fuso da conta (assumido America/New_York nesta PoC). No Voluum o fuso é pedido no report (parâmetro `tz`); usamos Europe/Lisbon. Por isso o "dia" de cada provider pode ter fronteiras diferentes de 1 a 5 horas, e os totais de um dia podem não bater certo entre providers.
- **Moeda**: Erobella reporta em EUR. O TrafficJunky reporta em USD, convertido para EUR na camada analytics com uma taxa fixa de 0,92 (só PoC). O Voluum reporta na moeda pedida (EUR).
- **Rácios reportados pelo provider vs cálculo interno**: CTR, CPC, CR, eCPM reportados por cada provider usam fórmulas e denominadores próprios. Internamente calculamos tudo a partir de somas (ratio of sums) sobre o modelo canónico.
- **Filtered clicks**: alguns providers removem cliques inválidos (bots, duplicados) depois do reporte inicial, por isso os cliques de dias recentes podem baixar ligeiramente.
- **Reporting delay**: os números dos últimos dias podem ser revistos. As conversões chegam mais tarde e os últimos dias ficam sub-reportados.
- **Campos específicos**: cada provider traz campos próprios que não existem nos outros e que não entram no modelo canónico.
- **Receita e conversões**: só o Voluum reporta revenue e visits. O TrafficJunky reporta conversões mas não receita por campanha. A Erobella não reporta conversões nem receita. Por isso o ROAS só existe para voluum.

## Erobella

- Reporta impressões, cliques, custo (EUR), CTR em % e eCPM.
- Não tem campanhas: o creative (label) é a unidade; na camada analytics o label torna-se campaign_id e campaign_name.
- **price_eur cannot be interpreted without checking model.** Nas tarifas, `price_eur` depende do campo `model`: com `cpm` é EUR por mil impressões; com `revshare` é uma percentagem (50.0 significa 50%, não 50 EUR). Não tratar price_eur como custo absoluto.

## TrafficJunky

- **ecpc is provider-reported but internal CPC should be calculated from canonical cost / clicks.** O ecpc vem em USD e com a fórmula do provider; o CPC interno vem do custo canónico (EUR) a dividir pelos cliques.
- Reporta conversões e custo por campanha; a receita aparece só no relatório de spots, que não está ligado às campanhas.

## Voluum

- **Report metrics depend on requested dimensions / columns.** Os campos preenchidos de cada linha dependem do `groupBy` e das `column` pedidas.
- O Voluum é um tracker: o seu CR reportado usa visitas como denominador, enquanto o CR interno usa cliques. Os valores diferem por construção.
- Os custos no Voluum vêm da fonte de tráfego ou de uma estimativa e podem ser ajustados mais tarde.
