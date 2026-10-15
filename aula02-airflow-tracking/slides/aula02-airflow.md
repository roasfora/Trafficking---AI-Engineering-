---
marp: true
theme: default
size: 16:9
paginate: true
footer: 'SCOPPHU  ·  AI Engineering Course 2026  ·  M02'
title: 'Data Pipelines com Apache Airflow — Aula 02'
author: 'Scopphu · AI Engineering Course'
description: 'Dos dados à operação — e o que acontece quando tudo começa a falhar'
---

<style>
:root {
  --bg:#0D0D0D; --fg:#F5F5F5; --lime:#C8F03C; --red:#FF5C5C;
  --muted:#9A9A9A; --faint:#5A5A5A; --card:#161616; --hot:#171A0E; --line:#2A2A2A;
}
section {
  background: var(--bg); color: var(--fg);
  font-family: Arial, Helvetica, sans-serif;
  padding: 48px 64px 68px; font-size: 22px; line-height: 1.45;
  justify-content: flex-start;
}
section::after { color: var(--lime); font-size: 13px; right: 42px; bottom: 26px; }
footer { color: var(--faint); font-size: 12px; left: 64px; bottom: 26px; letter-spacing: .05em; }

h1 { font-size: 58px; line-height: 1.08; margin: 0 0 18px; font-weight: 700; color: var(--fg); }
h1 strong { color: var(--lime); }
h2 { font-size: 38px; line-height: 1.15; margin: 0 0 26px; font-weight: 700; color: var(--fg); }
h3 { font-size: 20px; margin: 0 0 8px; font-weight: 700; color: var(--fg); }
p  { margin: 0 0 14px; }
ul { margin: 0 0 14px; padding-left: 22px; }
li { margin-bottom: 8px; }
em { color: var(--muted); font-style: italic; }
strong { color: inherit; }
h2 strong, h3 strong { color: var(--lime); }

.kicker { color: var(--lime); font-size: 12px; font-weight: 700; letter-spacing: .2em;
          text-transform: uppercase; margin: 0 0 16px; }
.big    { font-size: 38px; font-weight: 700; line-height: 1.22; margin: 0 0 18px; }
.huge   { font-size: 46px; font-weight: 700; line-height: 1.18; margin: 0 0 18px; }
.lime   { color: var(--lime); }
.red    { color: var(--red); }
.muted  { color: var(--muted); }
.note   { color: var(--muted); font-size: 17px; margin: 0 0 10px; }
.spacer { height: 14px; }

.cols { display: flex; gap: 20px; align-items: stretch; }
.cols > * { flex: 1; min-width: 0; }
.cols.tight { gap: 14px; }

.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px; }
.card.hot { background: var(--hot); border-color: var(--lime); }
.card.bad { border-color: var(--red); }
.card h3 { font-size: 19px; }
.card p  { font-size: 16px; color: var(--muted); margin: 0; }
.card ul { font-size: 16px; color: var(--muted); margin: 0; padding-left: 18px; }
.card li { margin-bottom: 5px; }
.tag { font-size: 11px; font-weight: 700; letter-spacing: .15em; text-transform: uppercase;
       color: var(--muted); margin: 0 0 10px; }
.card.hot .tag { color: var(--lime); }
.card.bad .tag { color: var(--red); }

.chips { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 16px; }
.chip { border: 1px solid var(--line); background: var(--card); border-radius: 999px;
        padding: 7px 16px; font-size: 17px; }
.chip.bad { border-color: var(--red); color: var(--red); }
.chip.ok  { border-color: var(--lime); color: var(--lime); }

.flow { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
.box  { border: 1px solid var(--line); background: var(--card); border-radius: 8px;
        padding: 9px 15px; font-size: 17px; }
.box.hot { border-color: var(--lime); background: var(--hot); color: var(--lime); }
.box.bad { border-color: var(--red); color: var(--red); }
.arrow { color: var(--lime); font-size: 19px; }

pre { background: #111; border: 1px solid var(--line); border-radius: 10px; padding: 14px 18px !important; margin: 0 0 14px; }
pre code { font-family: "Courier New", monospace; font-size: 17px; color: #D6F27A; line-height: 1.5; }
pre code span { color: #D6F27A; }
pre code .hljs-comment, pre code .hljs-quote { color: #7E8C5A; }
pre code .hljs-keyword, pre code .hljs-built_in, pre code .hljs-type { color: #F5F5F5; }
p code, li code, td code, th code { font-family: "Courier New", monospace; background: #1A1A1A;
       color: #D6F27A; padding: 1px 6px; border-radius: 4px; font-size: .9em; }
pre.diagram { background: transparent; border: 0; padding: 0 !important; }
pre.diagram code { color: var(--muted); font-size: 17px; line-height: 1.4; }
pre.diagram code b { color: var(--lime); font-weight: 400; }
pre.diagram.sm code { font-size: 15px; line-height: 1.35; }

table { width: 100%; border-collapse: collapse; font-size: 17px; margin: 0 0 14px; }
tr { background: transparent; }
th { color: var(--lime); text-align: left; background: #1A1A1A; font-weight: 700; }
th, td { border: 1px solid #262626; padding: 7px 12px; }
td { color: var(--muted); background: #0F0F0F; }
tr:nth-child(even) td { background: #141414; }
td:first-child { color: var(--fg); font-weight: 700; }
table.sm { font-size: 15px; }
table.sm th, table.sm td { padding: 5px 9px; }

.demo { display: inline-block; background: var(--lime); color: #0D0D0D; font-weight: 700;
        font-size: 12px; letter-spacing: .15em; padding: 5px 12px; border-radius: 4px; }

section.lead, section.statement { justify-content: center; }
section.lead h1 { font-size: 62px; }
</style>

<!-- _class: lead -->
<!-- _paginate: false -->
<!-- _footer: '' -->

<p class="kicker">Scopphu · AI Engineering Course 2026 · Módulo 02</p>

# Data Pipelines com<br>**Apache Airflow**

<p class="big muted" style="font-size:26px">Dos dados à operação — e o que acontece quando tudo começa a falhar</p>

<div class="flow">
<span class="box">Synthetic Tracking API</span><span class="arrow">→</span>
<span class="box hot">Apache Airflow</span><span class="arrow">→</span>
<span class="box">PostgreSQL</span>
</div>

<p class="note">Apolonia Group  ·  5 horas  ·  Python · Pandas · FastAPI · Pydantic · Airflow · PostgreSQL · Docker</p>

<!--
**Objetivo** · Abrir sem teoria. A sala tem de ver o fim antes do princípio.

**Dizer** — "Hoje não vamos falar sobre pipelines de dados. Vamos construir uma, parti-la sete vezes, e reparar os buracos que cada falha abre." Depois a promessa concreta: ao fim do dia cada um tem a pipeline a correr no portátil, com dados a entrar numa base PostgreSQL todos os dias.

Os dados são 100 % sintéticos, gerados por uma API fictícia com seed — mas a **estrutura** é a de uma plataforma de tracking real. É o que permite falar de problemas verdadeiros sem pôr dados de ninguém em cima da mesa.

**Não dizer** — nada sobre Airflow ainda. O Airflow é a terceira coisa que aparece, não a primeira.

**Ligação** — "Isto é o que vamos ter no fim. Vamos ver o desenho completo."

**Tempo** 2 min
-->

---

<p class="kicker">Abertura</p>

## Hoje vamos construir isto

<div class="cols">
<div>

<pre class="diagram"><code>  Synthetic Tracking API      <b>o producer</b> (FastAPI)
            │
            ▼
      <b>Apache Airflow</b>           orquestra, uma vez por dia
            │
            ▼
        PostgreSQL            4 dim_*  ·  3 fact_*
            │
            ▼
        Analytics             views: CPC, CPA, ROAS, ROI
</code></pre>

</div>
<div>

<pre class="diagram"><code>  Dentro do Airflow, 7 tasks:

  <b>check_api</b>
      ↓
  <b>extract</b>
      ↓
  <b>validate</b>
      ↓
  <b>transform</b>
      ↓
  <b>load_dimensions</b>
      ↓
  <b>load_facts</b>
      ↓
  <b>quality_check</b>
</code></pre>

</div>
</div>

<p class="note">Três containers: <code>api</code>, <code>airflow</code>, <code>postgres</code>. E <strong class="lime">duas bases de dados</strong> no mesmo Postgres: <code>analytics</code> (o negócio) e <code>airflow</code> (os metadados do orquestrador). Confundi-las é o erro mais comum da primeira semana.</p>

<!--
**Objetivo** · Dar o mapa. A partir daqui, cada bloco da aula é um pedaço deste desenho.

**Dizer** — percorrer a coluna da esquerda de cima para baixo em 30 segundos. Depois a direita: "cada uma destas sete caixas é uma task; cada uma faz uma coisa e passa à seguinte."

Dois nomes que já vale a pena plantar, sem explicar: *producer* (quem emite os dados) e *orquestrador* (quem decide o que corre e quando).

**Insistir nas duas bases de dados.** `analytics` tem as tabelas do negócio e é para onde o nosso ETL escreve; `airflow` tem o estado do Airflow — runs, tasks, retries, XComs — e só o Airflow lhe toca. São configuradas por variáveis diferentes (`DATABASE_URL` e `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN`) e em produção estariam em servidores diferentes. Apontar a pipeline a outro PostgreSQL (o do Render, por exemplo) é mudar **só** a primeira.

**Perguntar** — "quantas destas sete tasks é que acham que são o Airflow?" A resposta certa é zero: o Airflow é a moldura, o trabalho é Python.

**Ligação** — "Reparem que eu disse 'o Airflow é a moldura'. Isso é mesmo o ponto da aula."

**Tempo** 6 min
-->

---

<!-- _class: statement -->

<p class="kicker">Abertura</p>

## O objetivo não é aprender Airflow

<p class="huge">O objetivo é perceber como construir uma<br><span class="lime">pipeline de dados fiável</span>.</p>

<div class="flow">
<span class="box">Python</span>
<span class="box">Pandas</span>
<span class="box">FastAPI</span>
<span class="box">Pydantic</span>
<span class="box hot">Airflow</span>
<span class="box">PostgreSQL</span>
<span class="box">Docker</span>
</div>

<p class="note">O Airflow é uma das sete peças. É a que organiza as outras — e é a última que vamos montar.</p>

<!--
**Objetivo** · Baixar a expectativa de "curso de ferramenta" e subir a de "curso de conceitos".

**Dizer** — "Se saírem daqui a saber clicar na UI do Airflow e mais nada, falhei. O Airflow muda de versão todos os anos; grain, contratos e idempotência não mudam há trinta."

Dizer também o que fica deliberadamente de fora: dbt, Spark, Kafka, Kubernetes, Celery, medallion, bronze/silver/gold. Não porque não prestem — porque são respostas a problemas que ainda não temos. "Quem vos vender arquitetura antes de vos perguntar o grain, desconfiem."

**Perguntar** — "quantos de vocês já ouviram 'precisamos de um data lake'? E quantos ouviram primeiro a pergunta 'o que é uma linha da vossa tabela'?"

**Ligação** — "Então vamos começar pelo problema, não pela stack."

**Tempo** 5 min
-->

---

<p class="kicker">Abertura · o problema</p>

## O problema

<div class="cols">
<div class="card">
<p class="tag">O que o negócio gera</p>
<ul>
<li><strong>custo</strong> — tráfego comprado, cobrado <em>à hora</em></li>
<li><strong>clicks e impressions</strong> — também agregados por hora</li>
<li><strong>conversões</strong> — postbacks, uma a uma, com receita</li>
<li><strong>daily control</strong> — o agregado diário, vindo de <em>outro</em> sistema</li>
</ul>
</div>
<div class="card hot">
<p class="tag">O que o negócio pergunta</p>
<ul>
<li>Quanto gastámos ontem?</li>
<li>Quanto ganhámos ontem?</li>
<li>Que campanhas dão lucro?</li>
</ul>
<p style="margin-top:12px">E, sobretudo: <strong class="lime">todos os dias, antes das 9h.</strong></p>
</div>
</div>

<p class="note">Os dados nascem em dois sistemas diferentes. Alguém tem de os ir buscar, pô-los de acordo, e deixá-los onde se possam somar.</p>

<!--
**Objetivo** · Ancorar a aula num problema de negócio reconhecível, antes de qualquer conceito técnico.

**Dizer** — explicar o domínio em 60 segundos: uma plataforma de performance marketing compra tráfego e ganha dinheiro quando esse tráfego converte. Três perguntas simples do lado direito.

Chamar a atenção para a assimetria do lado esquerdo, que é o que torna este modelo interessante: o **custo chega agregado por hora** (ninguém guarda os clicks um a um), mas a **receita chega evento a evento**. Dois grãos diferentes na mesma pipeline — e é daí que vêm metade dos erros de relatório.

E há uma quarta linha que ninguém espera: o **daily control**, um agregado diário que vem do backoffice e que às vezes é escrito à mão. É uma segunda opinião sobre os mesmos números. Guardar o nome: volta às 16:15, e é o melhor check de qualidade do projeto.

O detalhe que muda tudo é o último da coluna direita: "antes das 9h". Um número certo que chega às 15h não serve para decidir se se pausa uma campanha.

**Perguntar** — "no vosso trabalho, quem responde a estas perguntas hoje, e de onde tira o número?" A resposta mais comum — "exporto para Excel" — é exatamente o problema.

**Ligação** — "Parece fácil: ir buscar os dados e metê-los numa base de dados."

**Tempo** 8 min
-->

---

<p class="kicker">Abertura · o problema</p>

## O difícil não é mover dados

<div class="flow" style="margin-bottom:26px">
<span class="box">API</span><span class="arrow">───────→</span><span class="box">PostgreSQL</span>
<span class="note" style="margin-left:16px;margin-bottom:0">cinquenta linhas de Python</span>
</div>

<div class="chips">
<span class="chip bad">API em baixo</span>
<span class="chip bad">timeout</span>
<span class="chip bad">HTTP 429</span>
<span class="chip bad">schema drift</span>
<span class="chip bad">valores impossíveis</span>
<span class="chip bad">a mesma run outra vez</span>
<span class="chip bad">dois sistemas a discordar</span>
</div>

<p class="big">Mover dados é fácil.<br><span class="lime">Fazê-lo de forma fiável é o trabalho.</span></p>

<!--
**Objetivo** · Justificar as cinco horas. Sem este slide, metade da sala acha que isto é um script.

**Dizer** — "Qualquer pessoa nesta sala escreve o script de cima em meia hora. E funciona. Funciona durante três semanas." Depois ler a lista vermelha devagar — cada uma é um dia mau real.

Insistir nos dois últimos, que são os únicos que **não dão erro nenhum**:
- *a mesma run outra vez* — duplica tudo, em silêncio, e ninguém repara até o CFO perguntar porque é que o custo triplicou.
- *dois sistemas a discordar* — o dashboard diz 4 500 € e o backoffice diz 4 600 €. Ambos estão convencidos de que têm razão.

**Perguntar** — "qual destes sete é o mais perigoso?" Deixar discutir. A resposta que quero: os que não falham, porque são os únicos que ninguém vê.

**Ligação** — "Vamos atacar todos estes. Mas não hoje pela ordem da lista: primeiro temos de perceber os dados."

**Tempo** 9 min
-->

---

<p class="kicker">O domínio e o modelo</p>

## Como é que isto funciona, no mundo real

<div class="cols tight">
<div class="card">
<p class="tag">1 · compra-se tráfego</p>
<p style="color:#F5F5F5">Uma <strong>campanha</strong>, de um <strong>workspace</strong>, compra tráfego numa <strong>fonte</strong> (ExoClick, TrafficStars…).</p>
<p style="margin-top:8px">O custo, os clicks e as impressions chegam <strong class="lime">agregados por hora</strong> — e por <em>investment provider</em>.</p>
</div>
<div class="card">
<p class="tag">2 · alguém converte</p>
<p style="color:#F5F5F5">A rede de afiliação envia um <strong>postback</strong>: é uma <strong>conversão</strong> de uma <strong>oferta</strong>, com a sua <code>revenue</code>.</p>
<p style="margin-top:8px">Chega <strong class="lime">evento a evento</strong>, e sempre <em>depois</em> da visita que a originou.</p>
</div>
<div class="card hot">
<p class="tag">3 · o backoffice fecha o dia</p>
<p style="color:#F5F5F5">Um segundo sistema mantém o <strong>daily control</strong>: receita e investimento por campanha e por dia.</p>
<p style="margin-top:8px">Às vezes <strong class="lime">escrito à mão</strong> (<code>is_manual</code>). É uma segunda opinião sobre os mesmos números.</p>
</div>
</div>

<p class="note">Na realidade isto vive em dois sítios: Mongo (eventos) e Postgres (gestão e daily control). A nossa API expõe os dois lados num só serviço.</p>

<!--
**Objetivo** · Dar o domínio antes do modelo. Quem não percebe o negócio desenha tabelas bonitas e erradas.

**Dizer** — percorrer os três cartões como uma história, com um exemplo concreto: "a campanha *US Dating Push* compra tráfego na ExoClick; às 14h gastou 12 € e trouxe 400 clicks; às 14h37 um desses visitantes depositou, e a rede mandou-nos um postback de 25 € de receita."

Três palavras novas a fixar:
- **investment provider** — quem financiou aquele tráfego. Há 16; uma campanha pode usar dois no mesmo dia, e por isso o custo da mesma hora pode vir em duas linhas.
- **postback** — a chamada que a rede faz quando alguém converte. É assíncrona: chega minutos ou horas depois da visita.
- **daily control** — o agregado do backoffice.

**Perguntar** — "porque é que o custo vem agregado por hora e a receita vem evento a evento?" Porque são sistemas diferentes com donos diferentes. É assim na vida real, e o modelo tem de aceitar isso em vez de fingir que não.

**Ligação** — "Três coisas a acontecer, três ritmos diferentes. Que tabelas é que isto dá?"

**Tempo** 8 min
-->

---

<p class="kicker">O domínio e o modelo</p>

## Antes do Airflow: o que representa **uma linha**?

<div class="cols tight">
<div class="card hot">
<p class="tag">fact_conversions</p>
<h3>1 linha = 1 conversão</h3>
<p>um postback</p>
</div>
<div class="card hot">
<p class="tag">fact_campaign_costs</p>
<h3>1 campanha × 1 hora<br>× 1 provider</h3>
<p>o custo nunca é por evento</p>
</div>
<div class="card hot">
<p class="tag">fact_daily_control</p>
<h3>1 campanha × 1 dia</h3>
<p>o agregado do outro sistema</p>
</div>
</div>

<div class="spacer"></div>

<p class="big"><span class="lime">Grain.</span> A primeira decisão de modelação — e aquela de que todas as outras dependem.</p>

<p class="note">Três tabelas, <strong>três grains diferentes</strong>. Não é um defeito do modelo: é o mundo a chegar assim.</p>

<!--
**Objetivo** · Instalar a palavra *grain* como a primeira pergunta de qualquer modelo. É o conceito mais importante do dia.

**Dizer** — "Antes de escolher ferramenta, antes de desenhar tabelas, há uma pergunta: o que é uma linha?" Parece trivial e é onde quase toda a gente se engana. Se a resposta for vaga — "é os dados da campanha" — o modelo vai estar errado e só se descobre quando os números não batem certo.

O grain determina três coisas: o que a chave primária identifica, o que `count(*)` conta, e o que se pode somar sem contar duas vezes.

O cartão do meio é o que custa a engolir: **não há tabela de clicks**. Na origem os clicks não são guardados um a um — só chegam agregados por hora, dentro do custo. Logo `clicks` é uma coluna de `fact_campaign_costs`, não uma fact. Quem desenhar uma `fact_clicks` aqui está a inventar dados que não existem.

**Exercício (3 min)** — "escrevam numa frase o grain de uma tabela que usam no vosso trabalho. Começa por 'uma linha é...'." Pedir duas em voz alta. Se alguém não conseguir acabar a frase, esse é o ponto do slide.

**Ligação** — "Temos três tabelas de factos. E as campanhas, as fontes, as ofertas?"

**Tempo** 9 min
-->

---

<p class="kicker">O domínio e o modelo</p>

## Fact ou dimension?

<div class="cols">
<div class="card">
<p class="tag">Dimension — descreve</p>
<h3>Quem, o quê, onde</h3>
<ul>
<li>Poucas linhas (2, 6, 8, 7)</li>
<li>Mudam devagar — SCD tipo 1</li>
<li>Atributos descritivos</li>
</ul>
<p style="margin-top:10px;color:#F5F5F5"><code>dim_workspace</code> · <code>dim_traffic_source</code><br><code>dim_campaign</code> · <code>dim_offer</code></p>
</div>
<div class="card hot">
<p class="tag">Fact — regista</p>
<h3>O que aconteceu</h3>
<ul>
<li>Muitas linhas, só crescem</li>
<li>Um facto passado não muda</li>
<li>Chaves + métricas + contexto</li>
</ul>
<p style="margin-top:10px;color:#F5F5F5"><code>fact_conversions</code> · <code>fact_campaign_costs</code><br><code>fact_daily_control</code></p>
</div>
</div>

<p class="note">Teste rápido: se a frase natural é <em>«é uma campanha»</em>, é dimension. Se é <em>«aconteceu às 14:32»</em> ou <em>«entre as 14h e as 15h»</em>, é fact.</p>

<!--
**Objetivo** · Dar o critério de decisão, não a definição de manual.

**Dizer** — a diferença operacional: uma dimension responde "o que é isto?", uma fact responde "o que aconteceu, quando, e quanto?". Aqui as dimensões têm 2, 6, 8 e 7 linhas; as facts têm centenas por dia e crescem para sempre.

Consequência prática: uma fact nunca se edita. Uma dimension sim — uma campanha muda de nome, é pausada. Usamos **SCD tipo 1**: o valor novo substitui o antigo e perde-se o histórico. Para saber "qual era o estado desta campanha na altura do click" seria preciso SCD tipo 2, e fica fora do âmbito.

Reparar numa coisa que o modelo herda da origem: `dim_traffic_source` e `dim_offer` têm uma coluna `deleted`. É um *soft delete* — a entidade já não está ativa, mas não se apaga, porque as facts históricas apontam para ela. Apagar uma dimensão é criar órfãos no passado.

**Perguntar** — "`investment_provider` é fact ou dimension?" São 16 valores fixos e não têm atributos nenhuns (nem fee, nem conta, nem moeda). Por isso é uma **coluna** dentro da fact — uma *dimensão degenerada*. Passa a dimensão no dia em que tiver atributos próprios.

**Ligação** — "Quatro dimensões, três factos. Vamos ver o desenho."

**Tempo** 8 min
-->

---

<p class="kicker">O domínio e o modelo</p>

## O nosso modelo

<pre class="diagram sm"><code>  <b>dim_workspace</b>  ◄──┐                      ┌──►  <b>dim_traffic_source</b>
                     │                      │           (deleted)
                     └───  <b>dim_campaign</b>  ───┘
                                 ▲   ▲   ▲
            ┌────────────────────┘   │   └────────────────────┐
  <b>fact_campaign_costs</b>        <b>fact_daily_control</b>        <b>fact_conversions</b>  ──►  <b>dim_offer</b>
  1 campanha × 1 hora          1 campanha × 1 dia        1 conversão (postback)
  × 1 provider                                           + traffic_source
  cost · clicks · impressions  revenue · investment      revenue
</code></pre>

<div class="card bad">
<p class="tag">Armadilha · fan-out</p>
<p style="color:#F5F5F5">Juntar <code>fact_conversions</code> com <code>fact_campaign_costs</code> e somar a seguir repete o <code>cost</code> de cada hora <strong>uma vez por cada conversão</strong>. Agrega-se cada fact ao seu grain e só depois se juntam os <em>resultados</em>.</p>
</div>

<!--
**Objetivo** · Mostrar que o modelo inteiro cabe num slide — quatro dimensões, três facts — e plantar o erro de junção mais caro que existe.

**Dizer** — percorrer as chaves. A hierarquia da origem é Workspace → TrafficSource → Campaign, e a campanha referencia as duas. As três facts apontam todas para `dim_campaign`; só a conversão aponta também para a oferta e para a fonte.

Duas perguntas que a sala costuma fazer e que vale a pena antecipar:
- *Porque é que a conversão guarda `traffic_source_id` se a campanha já o tem?* Porque vem assim da origem — e porque se tornou um **check de qualidade**: se a fonte da conversão não for a da campanha, alguma coisa está mal. Voltamos a isto às 16:15.
- *E `dim_offer`, porque é que só a conversão lhe aponta?* Porque **o custo não tem oferta**. O tráfego compra-se para uma campanha, não para uma oferta. É por isso que a view `v_offer_daily` só tem receita e conversões — não há CPA por oferta, e isso é uma informação, não uma lacuna.

Depois o fan-out, devagar, porque é o momento em que a sala percebe porque é que o grain importa: uma hora de custo com 5 conversões, num JOIN com SUM, conta o custo cinco vezes. O relatório fica com 400 % mais custo e ninguém consegue explicar porquê. Há um teste que trava isto: `test_no_fan_out_totals_match_the_facts` — a soma das views tem de bater certo com a soma das facts.

**Ligação** — "Reparem que não há uma coluna `id` em lado nenhum das facts. Isso não é um esquecimento."

**Tempo** 10 min
-->

---

<p class="kicker">O domínio e o modelo</p>

## O data catalog

<table class="sm">
<tr><th>Tabela</th><th>1 linha =</th><th>Chave primária</th><th>Linhas/dia</th></tr>
<tr><td>dim_workspace</td><td>1 workspace</td><td><code>workspace_id</code></td><td>2 · estática</td></tr>
<tr><td>dim_traffic_source</td><td>1 fonte de tráfego</td><td><code>traffic_source_id</code></td><td>6 · estática</td></tr>
<tr><td>dim_campaign</td><td>1 campanha</td><td><code>campaign_id</code></td><td>8 · estática</td></tr>
<tr><td>dim_offer</td><td>1 oferta</td><td><code>offer_id</code></td><td>7 · estática</td></tr>
<tr><td>fact_conversions</td><td>1 conversão</td><td><code>click_id</code> + <code>conversion_type_id</code> + <code>postback_timestamp</code></td><td>≈ 170</td></tr>
<tr><td>fact_campaign_costs</td><td>1 campanha × 1 hora × 1 provider</td><td><code>datetime</code> + <code>campaign_id</code> + <code>investment_provider</code></td><td>≈ 190</td></tr>
<tr><td>fact_daily_control</td><td>1 campanha × 1 dia</td><td><code>date</code> + <code>campaign_id</code></td><td>6</td></tr>
</table>

<div class="cols tight">
<div class="card">
<p class="tag">E 4 views por cima</p>
<p style="color:#F5F5F5"><code>v_campaign_daily</code> · <code>v_traffic_source_daily</code> · <code>v_offer_daily</code> · <code>v_reconciliation_daily</code></p>
</div>
<div class="card hot">
<p class="tag">Porque é que isto existe</p>
<p>Uma tabela sem grain, sem chave e sem dono não é um ativo — é um ficheiro. O catálogo é o sítio onde isso está escrito.</p>
</div>
</div>

<!--
**Objetivo** · Dar a fotografia completa do warehouse num slide, e apresentar a ideia de *data catalog* como prática, não como ferramenta.

**Dizer** — "isto é tudo o que existe na base `analytics`. Sete tabelas e quatro views. Cabe num slide, e é de propósito: um modelo que não cabe num slide normalmente também não cabe na cabeça de ninguém."

Depois o conceito. Um data catalog é o inventário do que existe: por cada tabela, o que uma linha representa, qual é a chave, de onde vêm os dados, o que cada coluna significa e quem é o dono. Pode ser uma ferramenta cara (DataHub, Amundsen, Unity Catalog) ou — como aqui — **um ficheiro markdown ao lado do código**, que se revê no mesmo pull request que muda o schema. Para sete tabelas, a segunda opção é melhor.

A pergunta que o catálogo responde e mais ninguém responde: *«posso usar esta coluna?»* Sem catálogo, a resposta vem por Slack, de quem estiver online, e muda consoante a pessoa.

Reparar na coluna da direita: as dimensões são estáticas (2, 6, 8, 7 linhas) e as facts crescem todos os dias. É a distinção do slide anterior, agora em números.

**Perguntar** — "no vosso trabalho, se eu abrir uma tabela que nunca vi, onde é que descubro o que uma linha significa?" A resposta honesta costuma ser «pergunto a alguém» — e às vezes «já ninguém sabe».

**Nota** — o catálogo deste projeto está em `docs/data-catalog.md`, com linhagem, regras de qualidade por camada e o glossário de métricas. Vale a pena projetá-lo 30 segundos para a sala ver o formato.

**Ligação** — "Uma linha do catálogo, vista de perto, é isto."

**Tempo** 7 min
-->

---

<p class="kicker">O domínio e o modelo</p>

## Uma entrada do catálogo

<p class="note" style="margin-bottom:12px"><code>fact_campaign_costs</code> — 1 linha = 1 campanha × 1 hora × 1 <em>investment provider</em></p>

<table class="sm">
<tr><th>Coluna</th><th>Tipo</th><th>Nulo?</th><th>De onde vem</th></tr>
<tr><td>datetime</td><td>TIMESTAMPTZ</td><td>não</td><td>início da hora, UTC · <strong class="lime">PK</strong> · janela de extração</td></tr>
<tr><td>cost_date</td><td>DATE</td><td>não</td><td><em>calculada</em> no transform · a data dos relatórios</td></tr>
<tr><td>campaign_id</td><td>TEXT</td><td>não</td><td>FK → <code>dim_campaign</code> · <strong class="lime">PK</strong></td></tr>
<tr><td>investment_provider</td><td>TEXT</td><td>não</td><td>enum de 16 valores · <strong class="lime">PK</strong></td></tr>
<tr><td>cost</td><td>NUMERIC(14,4)</td><td>não</td><td>USD · métrica aditiva · <code>CHECK >= 0</code></td></tr>
<tr><td>clicks</td><td>BIGINT</td><td><strong class="red">sim</strong></td><td><code>NULL</code> = o provider não reporta</td></tr>
<tr><td>impressions</td><td>BIGINT</td><td><strong class="red">sim</strong></td><td><code>NULL</code> = o provider não reporta</td></tr>
<tr><td>loaded_at / updated_at</td><td>TIMESTAMPTZ</td><td>não</td><td>1.ª carga / última recarga</td></tr>
</table>

<p class="note">Nome, tipo, se pode ser nulo, de onde vem e o que lhe fizemos. <strong class="lime">Nada disto se descobre olhando para o <code>CREATE TABLE</code>.</strong></p>

<!--
**Objetivo** · Mostrar o que uma entrada de catálogo tem a mais do que o DDL — e usar a tabela mais rica do modelo para o fazer.

**Dizer** — percorrer as oito linhas, parando em quatro:
- **As três `PK`** — a chave composta está marcada coluna a coluna. É o grain, outra vez, agora visível a olho.
- **`cost_date` é *calculada*** — não vem da origem. O catálogo diz isso; o `CREATE TABLE` não. Quem não souber, procura-a na API e não a encontra.
- **`clicks` e `impressions` podem ser nulos**, e o catálogo explica *porquê*: nem todos os providers reportam. A coluna "de onde vem" é a que distingue um catálogo de uma listagem de colunas.
- **`loaded_at` e `updated_at`** — metadados de carga, não dados do negócio. Estão em todas as tabelas e servem para responder a "quando é que esta linha apareceu?" e "quando é que foi recarregada?". Vamos usá-los na demo de idempotência.

A frase de fecho é o argumento todo: o schema diz *como* os dados estão guardados; o catálogo diz *o que significam*. São documentos diferentes com leitores diferentes.

**Perguntar** — "quem é que devia manter isto atualizado?" A resposta que quero: quem muda o schema, no mesmo pull request. Um catálogo mantido por outra equipa, à parte, está desatualizado ao fim de um mês — e um catálogo desatualizado é pior do que nenhum, porque as pessoas confiam nele.

**Se estiver atrasado** — este slide é o primeiro candidato a corte do bloco: o catálogo completo está em `docs/data-catalog.md` e pode ir como leitura.

**Ligação** — "Reparem outra vez nas três colunas marcadas com PK. Porque é que são três?"

**Tempo** 6 min
-->

---

<p class="kicker">O domínio e o modelo</p>

## Escolher a chave é escolher o grain

<div class="cols">
<div>

```sql
PRIMARY KEY (click_id,
             conversion_type_id,
             postback_timestamp)
```

<p class="note">Não há <code>conversion_id</code> na origem. A chave é <strong class="lime">composta e natural</strong>.</p>

<p class="note" style="margin-top:12px">Um mesmo click pode converter <strong>mais do que uma vez</strong>: tipo 1 (o depósito), tipo 2 (o upsell), em momentos diferentes.</p>

<p class="note">Por isso <code>click_id</code> sozinho <strong class="red">não é chave</strong>.</p>

</div>
<div>

<table class="sm">
<tr><th>Tabela</th><th>Chave primária</th></tr>
<tr><td>fact_conversions</td><td><code>click_id</code> + <code>conversion_type_id</code> + <code>postback_timestamp</code></td></tr>
<tr><td>fact_campaign_costs</td><td><code>datetime</code> + <code>campaign_id</code> + <code>investment_provider</code></td></tr>
<tr><td>fact_daily_control</td><td><code>date</code> + <code>campaign_id</code></td></tr>
</table>

<p class="note">Cada chave <strong class="lime">é</strong> o grain, escrito em SQL. Se a chave admitir duas linhas para o mesmo acontecimento, o grain está errado.</p>

<p class="note">E é esta chave que vai tornar a carga <strong class="lime">idempotente</strong> — às 16:00.</p>

</div>
</div>

<!--
**Objetivo** · O slide que separa quem já modelou de quem ainda não. A chave não é um detalhe técnico: é a definição formal do grain.

**Dizer** — a tentação, vinda de aplicações, é pôr um `id SERIAL` em tudo. Num warehouse isso é quase sempre um erro: um id artificial aceita a mesma linha duas vezes sem se queixar, e a duplicação passa a ser invisível.

A chave natural tem de responder à pergunta "o que é que, repetido, significa a mesma coisa?". Nas conversões, três colunas. Nos custos, a hora + a campanha + o provider — e é por isso que o provider está na chave: a mesma campanha pode comprar na mesma hora a dois providers, e são duas linhas legítimas.

**Perguntar** — "se eu puser só `(datetime, campaign_id)` na chave dos custos, o que acontece?" A segunda linha da mesma hora sobrepõe-se à primeira e perde-se metade do custo. Silenciosamente. É o tipo de bug que se descobre três meses depois, numa auditoria.

**Perguntar também** — "e `postback_timestamp` na chave, não é estranho?" É, um pouco. Está lá porque a origem não garante mais nada: o mesmo click, o mesmo tipo, reportado duas vezes em momentos diferentes, são dois postbacks. Vale a pena dizer em voz alta que uma chave natural é sempre uma *decisão*, tomada com quem conhece o negócio — não uma dedução.

**Ligação** — "Reparem numa coluna da chave: `postback_timestamp`. E há outra data na tabela. Porquê duas?"

**Tempo** 9 min
-->

---

<p class="kicker">O domínio e o modelo</p>

## Duas datas, dois usos

<pre class="diagram"><code>  14:32  <b>visit_timestamp</b>   o utilizador clicou
                              │
                              │   (minutos? horas?)
                              ▼
  17:05  <b>postback_timestamp</b>  a rede reportou a conversão
</code></pre>

<div class="cols">
<div class="card">
<p class="tag">Extrai-se por postback</p>
<p>É quando o dado <strong>nos chega</strong>. A janela da run tem de usar esta, senão uma conversão reportada hoje sobre uma visita de ontem nunca seria apanhada.</p>
</div>
<div class="card hot">
<p class="tag">Reporta-se por visita</p>
<p><code>visit_date</code> é o dia UTC da visita. É a data dos relatórios: põe a receita no <strong>mesmo dia do custo</strong> que a gerou.</p>
</div>
</div>

<p class="note">O custo tem o mesmo desenho: extrai-se por <code>datetime</code> (a hora), reporta-se por <code>cost_date</code>.</p>

<!--
**Objetivo** · Uma distinção pequena no schema e enorme nos relatórios. Quase ninguém a faz bem à primeira.

**Dizer** — há duas perguntas diferentes e cada uma quer a sua data:
- *«o que é que entrou no sistema hoje?»* → `postback_timestamp`. É a data **técnica**, a da ingestão.
- *«quanto rendeu a campanha no dia 3?»* → `visit_date`. É a data **de negócio**.

Se usássemos a data do postback nos relatórios, uma conversão lenta apareceria no dia errado e o ROAS do dia 3 ficaria distribuído por dois dias. Se usássemos a data da visita para extrair, perdíamos todas as conversões tardias — para sempre, porque a run do dia 3 já passou.

**Perguntar** — "e se um postback chegar três dias depois da visita?" Resposta honesta: a run de hoje apanha-o (extrai por postback) e atualiza o dia 3 (reporta por visita). Logo **o dia 3 muda depois de estar fechado**. Isto é normal em marketing e tem de ser explicado a quem lê os relatórios — e é mais uma razão para a carga ser idempotente.

**Perguntar** — "quantos dias esperamos antes de considerar um dia fechado?" Não há resposta universal; é uma decisão de negócio (a *janela de atribuição*). Vale a pena a sala dizer o número do caso deles.

**Ligação** — "Já temos as tabelas e as datas. Falta decidir o que guardamos dentro delas."

**Tempo** 7 min
-->

---

<p class="kicker">O domínio e o modelo</p>

## Métricas: base ou derivada?

<div class="cols">
<div class="card hot">
<p class="tag">Base — guardam-se</p>
<p style="color:#F5F5F5"><code>cost</code> · <code>clicks</code> · <code>impressions</code> · <code>revenue</code></p>
<p style="margin-top:8px">Aditivas: somam-se por qualquer dimensão e continuam a fazer sentido. <code>conversions</code> é <code>count(*)</code>.</p>
</div>
<div class="card">
<p class="tag">Derivadas — calculam-se</p>
<table class="sm" style="margin:0">
<tr><td>CPC</td><td><code>cost / clicks</code></td><td>CR</td><td><code>conv / clicks</code></td></tr>
<tr><td>CPM</td><td><code>cost / impr × 1000</code></td><td>CPA</td><td><code>cost / conv</code></td></tr>
<tr><td>CTR</td><td><code>clicks / impr</code></td><td>EPC</td><td><code>revenue / clicks</code></td></tr>
<tr><td>ROAS</td><td><code>revenue / cost</code></td><td>ROI</td><td><code>profit / cost</code></td></tr>
</table>
</div>
</div>

<p class="big" style="font-size:28px;margin-top:16px">Não guardar o que podemos<br><span class="lime">calcular corretamente depois</span>.</p>

<!--
**Objetivo** · Separar o que é dado do que é cálculo — e preparar as duas regras seguintes.

**Dizer** — quatro números guardam-se; nove calculam-se. As derivadas vivem todas em `sql/analytics.sql`, e só aí.

A tentação clássica é guardar o CPA na tabela "para ser mais rápido". Quem o faz descobre três meses depois que o CPA guardado foi calculado com a definição antiga e que já ninguém sabe qual era. Pior: um rácio guardado por linha não se pode somar nem agregar — fica inútil assim que alguém muda o nível de análise.

Reparar numa consequência do modelo: **não há CPA por oferta**. O custo não tem oferta (compra-se tráfego para uma campanha), por isso a view `v_offer_daily` tem receita e conversões e mais nada. Dizer isto em voz alta é melhor do que a sala descobrir sozinha e achar que falta uma coluna.

**Perguntar** — "`conversions` é base ou derivada?" Pergunta com rasteira: é `count(*)` das linhas de `fact_conversions`. É aditiva, mas não se guarda — deriva do grain.

**Ligação** — "Ora, se um rácio não é aditivo, o que acontece quando alguém o soma na mesma?"

**Tempo** 7 min
-->

---

<p class="kicker">O domínio e o modelo</p>

## Soma primeiro. Divide depois.

<div class="cols">
<div>

| dia | revenue | cost | roas |
|---|---|---|---|
| 1 Out | 60 | 60 | 1,0 |
| 2 Out | 100 | 20 | 5,0 |

<div class="card bad">
<p class="tag">Errado</p>
<p style="color:#F5F5F5"><code>AVG(roas)</code> = (1,0 + 5,0) / 2 = <strong class="red">3,0</strong></p>
</div>
<div class="spacer"></div>
<div class="card hot">
<p class="tag">Certo</p>
<p style="color:#F5F5F5"><code>SUM(revenue) / SUM(cost)</code> = 160 / 80 = <strong class="lime">2,0</strong></p>
</div>

</div>
<div>

<p class="big">Um rácio<br>não é aditivo.</p>

<p>Gastámos 80, rendeu 160. O ROAS dos dois dias é <strong class="lime">2,0</strong> — não 3,0.</p>

<p class="note">A média dos rácios dá 50 % a mais, e o erro cresce quanto mais desiguais forem os dias.</p>

<p class="note">Por isso as views agregam as métricas <em>aditivas</em> e só calculam o rácio no fim. E qualquer dashboard por cima delas tem de fazer o mesmo.</p>

<p class="note"><code>NULLIF(x, 0)</code> em todas as divisões: um dia sem conversões tem CPA <strong>indefinido</strong>, não um erro.</p>

</div>
</div>

<!--
**Objetivo** · Dar o erro de SQL mais comum em marketing analytics, com números que se conferem de cabeça.

**Dizer** — fazer as contas em voz alta e deixar a sala verificar. Dois dias, nada de extraordinário, e 50 % de diferença. Num relatório mensal com dias muito desiguais — que é o normal, porque se pausa e se escala — a diferença é maior.

Estes números não são inventados: são os do teste `tests/test_analytics.py::test_ratios_are_not_additive`, que falha se alguém mudar as views e partir isto.

Depois o `NULLIF`: um dia sem conversões tem CPA `NULL`, não infinito e não zero. Mostrar a diferença prática — num gráfico, `NULL` deixa um buraco honesto; um zero mente e diz "este dia foi baratíssimo".

**Perguntar** — "onde é que isto vos aparece no dia-a-dia?" Em Power BI e Looker: uma medida definida como `AVG(roas)` em vez de `SUM(revenue)/SUM(cost)`. O gráfico fica lindo e está errado.

**Ligação** — "Há um segundo valor que mente ainda melhor do que um rácio mal somado."

**Tempo** 8 min
-->

---

<p class="kicker">O domínio e o modelo</p>

## Nulo não é zero

<div class="cols">
<div>

<table class="sm">
<tr><th>provider</th><th>cost</th><th>clicks</th><th>impressions</th></tr>
<tr><td>exoclick</td><td>12,40</td><td>380</td><td>52 000</td></tr>
<tr><td>trafficstars</td><td>8,10</td><td>210</td><td>31 000</td></tr>
<tr><td>pushground</td><td>5,00</td><td>160</td><td><strong class="red">NULL</strong></td></tr>
</table>

<p class="note"><code>pushground</code> e <code>reactiveclicks</code> <strong>não reportam</strong> impressions. Não é zero: é <em>não sei</em>.</p>

</div>
<div>

<div class="card bad">
<p class="tag">Errado</p>
<p style="color:#F5F5F5">CTR = 750 / 83 000 = <strong class="red">0,90 %</strong></p>
<p style="margin-top:6px">Usa clicks que não têm impressões correspondentes. Inflaciona.</p>
</div>
<div class="spacer"></div>
<div class="card hot">
<p class="tag">Certo</p>
<p style="color:#F5F5F5">CTR = 590 / 83 000 = <strong class="lime">0,71 %</strong></p>
<p style="margin-top:6px">Só os clicks <strong>das linhas que reportam impressions</strong>.</p>
</div>

<p class="note" style="margin-top:12px">Na view: <code>sum(clicks) FILTER (WHERE impressions IS NOT NULL)</code>. O mesmo para o CPM, com o custo.</p>

</div>
</div>

<!--
**Objetivo** · Mostrar que um `NULL` tratado como zero é uma mentira silenciosa — e que a correção cabe numa cláusula de SQL.

**Dizer** — fazer as contas: 380+210+160 = 750 clicks, mas só 52 000+31 000 = 83 000 impressions, de duas das três linhas. Dividir 750 por 83 000 é misturar um numerador de três providers com um denominador de dois. O CTR aparece 27 % mais alto do que é.

O `FILTER (WHERE ...)` do PostgreSQL resolve isto numa linha, e é das coisas mais úteis que há para agregações condicionais. Mostrar a view se houver ecrã disponível.

A regra geral, maior do que este exemplo: **`NULL` significa "não sei"**, e "não sei" nunca se deve converter em zero sem alguém decidir conscientemente que o quer fazer. Um `COALESCE(x, 0)` distraído é uma das formas mais comuns de inventar dados.

**Perguntar** — "e se o Power BI, por cima destas views, fizer `SUM(clicks)/SUM(impressions)`?" Volta a dar o número errado. A view protege-se a si própria, mas não protege quem a usa — por isso as colunas `clicks_with_impressions` e `cost_with_impressions` estão expostas.

**Perguntar** — "quantos `NULL` há nas vossas tabelas que na verdade querem dizer zero? E quantos zeros que na verdade queriam dizer NULL?"

**Ligação** — "Já sabemos que tabelas queremos e que regras elas têm. Falta ver de onde vêm os dados."

**Tempo** 7 min
-->

---

<p class="kicker">API e data contract &nbsp;·&nbsp; <span class="demo">DEMO 1</span></p>

## A nossa fonte

<div class="cols">
<div>

<table class="sm">
<tr><th>Endpoint</th><th>Janela sobre</th></tr>
<tr><td>/health</td><td>—</td></tr>
<tr><td>/workspaces</td><td>dimensão</td></tr>
<tr><td>/traffic-sources</td><td>dimensão</td></tr>
<tr><td>/campaigns</td><td>dimensão</td></tr>
<tr><td>/offers</td><td>dimensão</td></tr>
<tr><td>/conversions</td><td><code>postback_timestamp</code></td></tr>
<tr><td>/campaign-costs</td><td><code>datetime</code></td></tr>
<tr><td>/daily-control</td><td><code>date</code></td></tr>
</table>

</div>
<div>

```json
{ "data":  [ ... ],
  "count": 100,
  "total": 437,
  "limit": 100,
  "offset": 0 }
```

<p class="big" style="font-size:26px">Pedi 100. Existem 437.<br><span class="lime">Como é que a pipeline sabe?</span></p>

<p class="note">Sem <code>total</code>, uma extração parcial parece uma extração completa. É o pior tipo de bug em dados: não dá erro.</p>

<p class="note">≈170 conversões · ≈190 linhas de custo · 6 de daily control, por dia.</p>

</div>
</div>

<!--
**Objetivo** · Mostrar a fonte a sério, no browser, e introduzir o envelope de paginação como um problema de fiabilidade — não como um detalhe de REST.

**Demo 1** (8 min)
```bash
docker compose up -d
open http://localhost:8000/docs
curl "localhost:8000/campaigns?limit=3"
curl "localhost:8000/conversions?start_date=2026-10-03&end_date=2026-10-04&limit=3"
curl "localhost:8000/campaign-costs?start_date=2026-10-03&end_date=2026-10-03T06:00:00&limit=3"
```
No `/docs`: abrir `/conversions`, *Try it out*, pôr `limit=3` e mostrar que `total` continua a dizer a verdade (≈170). Abrir também `/campaign-costs` e mostrar duas linhas da mesma hora com providers diferentes — é o grain do slide 7 a aparecer nos dados reais.

**Dizer** — a janela é `[start_date, end_date)`: início inclusivo, fim exclusivo, em UTC. Dois dias seguidos nunca partilham nem perdem um registo na fronteira. É o mesmo desenho dos *data intervals* do Airflow, que vamos ver depois do intervalo.

Reparar que cada endpoint de factos filtra pela **sua** data — a que corresponde ao momento em que o dado nos chega. É a decisão do slide 13.

E os dados são determinísticos: a mesma seed dá sempre os mesmos registos, com os mesmos IDs. Sem isso não havia demo repetível, não havia backfill, não havia demonstração de idempotência.

**Perguntar** — "quem é que já extraiu dados de uma API paginada sem verificar o total?" Toda a gente, mais cedo ou mais tarde.

**Ligação** — "A API respondeu 200 e deu-nos JSON. Isso chega para confiar?"

**Tempo** 10 min
-->

---

<p class="kicker">API e data contract</p>

## Producer → Consumer

<div class="cols">
<div>

<pre class="diagram"><code>      <b>FastAPI</b>
      PRODUCER
    "eu prometo que
     os dados são assim"
         │
         │  JSON
         ▼
    <b>Pydantic</b>  ◄── o contrato
         │
         ▼
      <b>Pipeline</b>
      CONSUMER
    "não confio, verifico"
</code></pre>

</div>
<div>

<p class="big">Uma API responder <span class="lime">200</span> não significa que os dados estejam <span class="lime">corretos</span>.</p>

<p>O producer valida o que <strong>emite</strong> — e só apanha os bugs dele próprio, se a validação existir.</p>

<p>O consumer valida o que <strong>recebe</strong> — e apanha qualquer desvio, venha de onde vier.</p>

<p class="note">Por isso a pipeline valida outra vez, mesmo sabendo que a API já validou.</p>

</div>
</div>

<!--
**Objetivo** · Instalar o vocabulário producer/consumer e justificar a validação dupla, que à primeira vista parece desperdício.

**Dizer** — "um data contract é o acordo explícito sobre a forma dos dados que um sistema entrega a outro. Sem contrato, o acordo existe só na cabeça de quem escreveu a API — e a primeira vez que alguém o quebra descobre-se quando um dashboard mostra números errados."

A pergunta óbvia da sala é: se a API já valida, porque é que eu valido outra vez? Duas respostas. Primeira: o producer pode estar errado sem o saber. Segunda, mais importante: **o producer não é teu**. Hoje é uma equipa ao lado, amanhã é um fornecedor que faz deploy à sexta-feira sem avisar.

Aqui há um pormenor honesto a assumir: o contrato é partilhado **por ficheiro** (o Airflow monta a pasta `api/`). Em produção seria um artefacto versionado e independente — um pacote, um JSON Schema, um schema registry — com regras de compatibilidade entre versões.

**Perguntar** — "alguém aqui já recebeu um aviso antes de um campo mudar numa API de terceiros?" Normalmente ninguém.

**Ligação** — "Vamos ver o contrato. São dez linhas de Python."

**Tempo** 6 min
-->

---

<p class="kicker">API e data contract</p>

## O contrato, em código

```python
class CampaignCost(Contract):                 # extra="forbid"
    datetime:            AwareDatetime        # sem timezone -> erro
    campaign_id:         EntityId             # UUID estrito: "123" nao passa
    investment_provider: InvestmentProvider   # enum: 16 valores
    cost:                Money                # >= 0, sem NaN/Infinity
    clicks:              int | None = None    # OPCIONAL: None != 0
    impressions:         int | None = None

    @field_validator("datetime")
    def must_be_top_of_the_hour(cls, v):      # regra do negocio, no contrato
        if v.minute or v.second:
            raise ValueError("deve ser o inicio de uma hora")
        return v
```

<div class="chips" style="margin-top:14px">
<span class="chip ok">tipos estritos</span>
<span class="chip ok">enums fechados</span>
<span class="chip ok">constraints</span>
<span class="chip ok">opcionais explícitos</span>
<span class="chip ok">regras do negócio</span>
<span class="chip ok">campos desconhecidos = erro</span>
</div>

<!--
**Objetivo** · Mostrar que um data contract não é burocracia: são doze linhas que já estão no repositório — e que podem conter regras de negócio, não só tipos.

**Dizer** — passar campo a campo, rápido:
- `AwareDatetime` — um timestamp sem fuso horário é uma armadilha. Quem já debugou um relatório com uma hora de desvio em março sabe porquê.
- `EntityId` é um UUID **estrito**: por omissão o Pydantic seria simpático e converteria coisas; aqui, se o producer começar a mandar inteiros ou UUIDs mal formados, queremos saber.
- O enum com 16 providers: um provider novo **parte a pipeline**. É deliberado — um valor que não conhecemos não devia entrar em silêncio num relatório.
- `clicks: int | None` — o opcional é explícito. `None` não é `0`; é o slide 16 a aparecer no contrato.
- E o validador: *o custo é horário, logo minutos e segundos têm de estar a zero*. Isto não é um tipo, é uma **regra do negócio** escrita no sítio onde os dados entram. É o melhor exemplo do dia de "o contrato é código executável, não um PDF".

`extra="forbid"`: um campo que o contrato não conhece é um erro. Assumir o trade-off — é a opção mais rígida, um campo *novo* e inofensivo também parte a pipeline. Muitos consumers reais usam `extra="ignore"`. Escolhemos `forbid` porque torna a deriva visível.

**Nota** — no repositório os tipos estão escritos com `Annotated[...]`; aqui está simplificado para caber no slide. O ficheiro real é `api/schemas.py`.

**Ligação** — "Agora imaginem que alguém do outro lado renomeia um campo."

**Tempo** 8 min
-->

---

<p class="kicker">API e data contract</p>

## Schema drift

<div class="cols">
<div class="card">
<p class="tag">Antes</p>

```json
{ "revenue": 29.90,
  "cost": 12.40 }
```
</div>
<div class="card bad">
<p class="tag">Depois</p>

```json
{ "revenue_amount": 29.90,
  "cost_amount": 12.40 }
```
</div>
</div>

<div class="spacer"></div>

<div class="chips">
<span class="chip ok">HTTP 200</span>
<span class="chip ok">120 ms</span>
<span class="chip ok">serviço UP</span>
<span class="chip ok">JSON válido</span>
</div>

<p class="big">Está tudo bem? &nbsp; <span class="red">NÃO.</span></p>

<p class="note">Pydantic: <code>revenue → missing</code> &nbsp;e&nbsp; <code>revenue_amount → extra_forbidden</code>, em <strong>172 de 172</strong> registos. É a única coisa no sistema inteiro que dá por isto.</p>

<!--
**Objetivo** · Mostrar o cenário de falha que nenhuma monitorização de infraestrutura apanha. É a semente do bloco de observabilidade, três horas mais tarde.

**Dizer** — não há erro nenhum. O serviço está de pé, responde depressa, devolve JSON bem formado. Um painel de uptime fica verde. Um alerta de latência fica calado. E a receita desapareceu.

Sem contrato, o que acontece a seguir: o `revenue` chega como `null` ou a coluna fica vazia, a carga corre com sucesso, e o dashboard mostra zero euros de receita. Alguém vai acreditar nesse zero.

Reparar na proporção: **172 de 172**. Não é um registo estragado, é o schema inteiro. Essa contagem é o que distingue "alguém mandou lixo" de "o producer mudou". Voltamos a ela no slide do `validate`.

**Perguntar** — "quantas destas mudanças é que acham que são anunciadas pelo producer?" E a seguir: "e se em vez de renomear, tivessem *acrescentado* um campo?" Com `extra="forbid"`, também falha. É o trade-off do slide anterior — e é por isso que a escolha entre `forbid` e `ignore` é uma decisão de equipa, não um default.

Dizer que vamos provocar isto ao vivo às 15:45.

**Ligação** — "Já sabemos o que queremos construir e de onde vêm os dados. Vamos escrever a ETL — sem Airflow nenhum."

**Tempo** 6 min
-->

---

<p class="kicker">ETL &nbsp;·&nbsp; <span class="lime">extract</span> · validate · transform · load</p>

## Extract

<div class="cols">
<div>

<pre class="diagram"><code>  API  ──►  raw_conversions.json
            raw_campaign_costs.json
            raw_daily_control.json
            raw_campaigns.json  ...

  data/staging/<b>20261003T000000</b>/
       ▲
       a pasta é a <b>janela</b>,
       não o relógio
</code></pre>

</div>
<div>

```python
while True:
    page = get(path, limit=500, offset=offset)
    rows += page["data"]
    offset += len(page["data"])
    if offset >= page["total"]:
        break
if len(rows) != total:
    raise ExtractError(...)
```

</div>
</div>

<p class="note">O <strong class="lime">XCom</strong> leva caminhos e contagens — nunca os dados. Vive na base de metadados do Airflow e é para mensagens pequenas.</p>

<!--
**Objetivo** · Mostrar que "extrair" tem duas responsabilidades e nenhuma delas é validar conteúdo: apanhar *tudo*, e deixar o resultado num sítio previsível.

**Dizer** — o `raise` no fim é a parte que interessa. Uma API que devolve 100 de 437 linhas sem dar erro produz dados incompletos em silêncio. A verificação `len(rows) != total` transforma isso numa falha ruidosa. (Há uma segunda verificação, menos óbvia: se o `total` **mudar a meio** da paginação, também falha — significa que a origem está a mudar debaixo dos nossos pés.)

As dimensões pedem-se sempre completas; só os três factos usam a janela. São poucas linhas e evita uma classe inteira de bugs de FK.

Depois a pasta: `data/staging/20261003T000000/`. O nome vem da *janela*, não de "agora". Voltar a correr o mesmo dia reescreve os mesmos ficheiros em vez de acumular lixo — é o primeiro sinal de idempotência, muito antes de falarmos dela.

E o XCom: cada task devolve um dicionário pequeno com caminhos e contagens. Quem mete um DataFrame no XCom descobre, um mês depois, que a base de metadados do Airflow tem 40 GB.

**Perguntar** — "porque é que os dados vão para ficheiros e não diretamente para memória entre tasks?" Porque cada task pode correr noutro processo, noutro worker, noutra máquina. E porque um ficheiro que fica é um ficheiro que se pode inspecionar quando algo corre mal.

**Ligação** — "Temos os dados em bruto. Cumprem o contrato?"

**Tempo** 7 min
-->

---

<p class="kicker">ETL &nbsp;·&nbsp; extract · <span class="lime">validate</span> · transform · load</p>

## Validate

<div class="cols">
<div>

<pre class="diagram"><code>  raw_*.json
       │
       ▼
   <b>Pydantic</b>   um registo de cada vez
       │
   ┌───┴────┐
   ▼        ▼
 válido   <b>inválido</b>
   │        │
 segue    ContractViolation
          (a task falha, nada
           a jusante corre)
</code></pre>

</div>
<div>

<pre class="diagram"><code>conversions   <b>13 de 172 INVÁLIDOS</b>
  campo=revenue       greater_than_equal
  campo=country_code  pattern_mismatch

conversions   <b>172 de 172 INVÁLIDOS</b>
  campo=revenue         missing
  campo=revenue_amount  extra_forbidden
</code></pre>

<p class="note">Valida <strong>todos</strong> os registos, não pára no primeiro. <code>13 em 172</code> é lixo pontual; <code>172 em 172</code> é o schema que mudou.</p>

</div>
</div>

<!--
**Objetivo** · Mostrar o contrato aplicado, e a diferença entre falhar e falhar *informando*.

**Dizer** — a decisão de desenho aqui é não parar no primeiro erro. Se parasse, o log dizia "o registo 14 tem o country_code errado" e não dava a informação que interessa: quantos, em quantos, e em que campos. Os dois exemplos do slide são os dois modos de falha da API — `invalid_payload` em cima, `schema_drift` em baixo — e distinguem-se **só pela proporção**.

Dizer também o que esta task **não** faz: não conta linhas, não verifica se os dados chegaram a tempo, não sabe se o daily control concorda com os eventos. Isso é o `quality_check`, depois do load. A regra de bolso: Pydantic responde a "este *registo* tem a forma certa?"; data quality responde a "este *conjunto* faz sentido?". Voltamos a isto às 16:15.

**Assumir a limitação** — esta versão falha a carga inteira por causa de treze registos maus em 172. É o mais seguro de ensinar e o mais burro em produção. A evolução chama-se **quarentena**: os maus vão para uma tabela `rejected_records` com o payload e o erro, os bons seguem, e a pipeline só falha acima de um limiar (1 %, por exemplo). Está em `docs/data-contract.md`.

**Ligação** — "Os dados cumprem o contrato. Agora é prepará-los para o destino."

**Tempo** 6 min
-->

---

<p class="kicker">ETL &nbsp;·&nbsp; extract · validate · <span class="lime">transform</span> · load</p>

## Transform

| Antes | Depois | Porquê |
|---|---|---|
| `"pt"` / `" PT "` | `"PT"` | espaços e caixa partem os `GROUP BY` |
| `2026-10-03T10:00+01:00` | `2026-10-03T09:00Z` | um único fuso, sempre |
| `visit_timestamp` | `+ visit_date` | a data de negócio, calculada uma vez |
| `datetime` (hora) | `+ cost_date` | idem, do lado do custo |
| `clicks: NaN` | `clicks: NULL` | «não sei» continua a ser «não sei» |

<div class="spacer"></div>

<p class="big" style="font-size:30px">Pandas. Funções puras: <code style="font-size:0.85em">DataFrame → DataFrame</code>.</p>

<p class="note">Aqui <strong>não</strong> se calcula CPA nem ROAS. Métricas derivadas não se guardam ao nível do facto.</p>

<!--
**Objetivo** · Desmistificar o "T" do ETL: é limpeza aborrecida e previsível, e é exatamente por isso que tem de ser testável.

**Dizer** — cada linha da tabela é um bug real que já aconteceu a alguém. O país com espaços é o clássico: o relatório mostra dois países chamados PT e ninguém percebe porquê.

A quinta linha é a mais subtil e liga-se ao slide 16: o pandas representa inteiros em falta como `NaN`, e ao escrever num CSV isso vira uma string vazia. Se não se tratar, um `clicks` desconhecido chega à base de dados como `0` — e o CTR passa a mentir. O código força `Int64` (o inteiro *nullable* do pandas) e converte `NaN` em `None` antes de escrever.

O ponto de arquitetura é a assinatura: cada transformação é uma função pura que recebe um DataFrame e devolve um DataFrame. Sem API, sem base de dados, sem Airflow. Por isso é que `tests/test_transform.py` corre em milissegundos e não precisa de nada ligado.

Há um pormenor delicioso no código: ao ler o CSV, `keep_default_na=False`. Sem isso o pandas lê o país `"NA"` — Namíbia — como valor em falta.

**Perguntar** — "porque é que o `visit_date` é calculado aqui e não na query?" Porque se calcula uma vez e usa-se mil. E porque fixa a decisão do slide 13, em vez de a deixar à escolha de quem escreve cada query.

**Ligação** — "Dados limpos, num DataFrame. Falta escrevê-los."

**Tempo** 6 min
-->

---

<p class="kicker">ETL &nbsp;·&nbsp; extract · validate · transform · <span class="lime">load</span></p>

## Load

<div class="flow" style="margin-bottom:6px">
<span class="note" style="width:120px;margin:0">1 · dimensões</span>
<span class="box hot">dim_workspace</span>
<span class="box hot">dim_traffic_source</span>
<span class="box hot">dim_campaign</span>
<span class="box hot">dim_offer</span>
</div>
<div class="flow" style="margin-bottom:20px">
<span class="note" style="width:120px;margin:0">2 · factos</span>
<span class="box">fact_conversions</span>
<span class="box">fact_campaign_costs</span>
<span class="box">fact_daily_control</span>
</div>

<div class="cols">
<div class="card">
<p class="tag">Dimensões primeiro</p>
<p>As FKs dos factos apontam para elas. Carregar uma conversão de uma campanha que ainda não existe é um erro de integridade referencial — e ainda bem.</p>
</div>
<div class="card">
<p class="tag">E dentro das dimensões, ordem também</p>
<p><code>dim_campaign</code> referencia <code>dim_workspace</code> e <code>dim_traffic_source</code>. A ordem não é estética: é o que a base de dados exige.</p>
</div>
<div class="card hot">
<p class="tag">Uma transação por passo</p>
<p>Ou entram todas as tabelas do passo, ou nenhuma. Falhar a meio não deixa meia carga.</p>
</div>
</div>

<!--
**Objetivo** · Mostrar que a ordem de carga não é arbitrária e que a base de dados é parte do desenho, não um saco onde se despeja.

**Dizer** — a ordem vem das chaves estrangeiras. Se eu inserir uma conversão que aponta para uma campanha que ainda não existe, o PostgreSQL recusa. Isso é uma funcionalidade, não um obstáculo: é a base de dados a impedir-me de criar órfãos.

Depois as transações: `load_dimensions` e `load_facts` são, cada um, uma transação. Se a terceira tabela falhar, as duas primeiras são revertidas. O estado é sempre coerente — nunca "meio dia carregado".

**Não dizer ainda** — nada sobre `ON CONFLICT`. O upsert aparece aqui no código, mas a conversa sobre idempotência tem de vir *depois* de a sala ver o Airflow a repetir runs sozinho. Guardar para as 16:00. Se alguém perguntar agora: "boa pergunta, é o penúltimo bloco da tarde."

**Perguntar** — "este `load` sabe que o Airflow existe?" Não. Nenhum ficheiro em `pipeline/` importa o Airflow. É isso que torna tudo isto testável — 95 testes, um a dois segundos — e é a deixa para o próximo bloco.

**Ligação** — "Temos uma ETL completa, em Python puro. Corre com um comando. Então porque precisamos de mais alguma coisa?"

**Tempo** 6 min
-->

---

<p class="kicker">Apache Airflow</p>

## Então porque precisamos de Airflow?

```bash
$ python pipeline.py
  172 conversoes, 190 linhas de custo, 6 de daily control  -  18 s
```

<div class="chips" style="margin-top:22px">
<span class="chip">Quem o executa amanhã às 4h?</span>
<span class="chip">E se falhar a meio?</span>
<span class="chip">E se eu precisar de repetir ontem?</span>
<span class="chip">E se uma etapa depender da anterior?</span>
<span class="chip">Onde vejo o que aconteceu na semana passada?</span>
</div>

<p class="big" style="margin-top:22px">Nenhuma destas perguntas é sobre <span class="lime">dados</span>.<br>São todas sobre <span class="lime">operação</span>.</p>

<!--
**Objetivo** · Fazer a sala pedir o Airflow antes de eu o apresentar. Se ele aparecer antes das perguntas, parece moda; depois delas, parece inevitável.

**Dizer** — "o script funciona. Está feito. Qual é o problema?" Deixar o silêncio. Depois pôr as perguntas uma a uma, devagar.

Para cada uma, deixar a sala propor a solução caseira e mostrar onde ela parte:
- *cron* — resolve a primeira. Não resolve mais nenhuma.
- *try/except e um email* — resolve meia. E quem reenvia?
- *um script para reprocessar* — agora são dois scripts a divergir.
- *um ficheiro de log* — e quem o lê às 4h da manhã?

**Perguntar** — "quantos de vocês têm, neste momento, um cron numa máquina que ninguém sabe bem o que faz?" Normalmente há risos. É o problema.

**Ligação** — "É exatamente este o conjunto de problemas que o Airflow resolve. E só este."

**Tempo** 8 min
-->

---

<p class="kicker">Apache Airflow &nbsp;·&nbsp; <span class="demo">DEMO 2</span></p>

## Anatomia do nosso DAG

<pre class="diagram sm"><code> <b>check_api</b> ─► <b>extract</b> ─► <b>validate</b> ─► <b>transform</b> ─► <b>load_dimensions</b> ─► <b>load_facts</b> ─► <b>quality_check</b>
     │                                                                            │
     └── task                                    dependência: <b>&gt;&gt;</b>  ──────────────┘
</code></pre>

<div class="cols tight" style="margin:16px 0 10px">
<div class="card"><p class="tag">schedule</p><p style="color:#F5F5F5"><code>@daily</code></p></div>
<div class="card"><p class="tag">catchup</p><p style="color:#F5F5F5"><code>False</code></p></div>
<div class="card"><p class="tag">max_active_runs</p><p style="color:#F5F5F5"><code>1</code></p></div>
</div>
<div class="cols tight" style="margin:0 0 16px">
<div class="card"><p class="tag">retries</p><p style="color:#F5F5F5"><code>2</code></p></div>
<div class="card"><p class="tag">retry_delay</p><p style="color:#F5F5F5"><code>30 s</code></p></div>
<div class="card"><p class="tag">execution_timeout</p><p style="color:#F5F5F5"><code>2 min</code></p></div>
</div>

<p class="big" style="font-size:30px">Airflow não é a ETL.<br><span class="lime">Airflow orquestra a ETL.</span></p>

<!--
**Objetivo** · Ligar o conceito ao ficheiro real, e correr a pipeline inteira em verde pela primeira vez.

**Demo 2** (ler o DAG 4 min + correr 12 min)
```bash
docker compose exec airflow airflow dags unpause tracking_pipeline
docker compose exec airflow airflow dags trigger tracking_pipeline --conf '{"date": "2026-10-03"}'
open http://localhost:8080        # sem login, é uma simplificação da formação
```
Na UI, *Grid*: ver as sete tasks a ficarem verdes uma a uma. Abrir os logs do `extract` (contagens por endpoint) e do `load_facts` (`fact_conversions {'inserted': 172, 'updated': 0}` — guardar este número, vamos precisar dele às 16:00).

Enquanto corre, abrir `dags/tracking_pipeline.py` no editor e mostrar que tem 137 linhas e **nenhuma** lógica de negócio: imports dentro das funções, `PythonOperator`, e o `>>` no fim.

**Dizer** — os seis parâmetros dos cartões são a aula inteira em miniatura: três são sobre tempo, três são sobre falha. Voltamos a cada um deles.

`max_active_runs=1`: duas runs a escrever as mesmas tabelas ao mesmo tempo é pedir problemas.

**Perguntar** — "o que acontece ao `transform` se o `validate` falhar?" Fica `upstream_failed` e nunca corre. Dados maus não chegam ao destino. Vamos vê-lo às 15:20.

**Ligação** — "Reparem no que escrevi no trigger: `date: 2026-10-03`. Porque é que uma run precisa de saber uma data?"

**Tempo** 16 min
-->

---

<p class="kicker">Apache Airflow</p>

## Data interval

<pre class="diagram"><code>  3 Out 00:00 ────────── os dados deste dia ────────── 4 Out 00:00
  <b>[</b> data_interval_start                      data_interval_end <b>)</b>
                                                            │
                                                            ▼
                                            a run só <b>arranca aqui</b>
</code></pre>

<div class="spacer"></div>

<p class="big">Uma run representa uma <span class="lime">fatia de dados</span>,<br>não a hora a que executou.</p>

<div class="cols">
<div class="card">
<p class="tag">O que a run faz com isto</p>
<p>Passa a janela ao <code>extract</code>, que a envia a cada endpoint como <code>start_date</code> / <code>end_date</code>. Fim inclusivo nunca: <code>[início, fim)</code>.</p>
</div>
<div class="card hot">
<p class="tag">Porque é que isto importa</p>
<p>A run não processa «o que houver agora». Processa <strong>um dia concreto</strong> — e esse dia pode ser reprocessado a qualquer momento com o mesmo resultado.</p>
</div>
</div>

<!--
**Objetivo** · O conceito do Airflow que mais gente usa mal. Quem não o percebe escreve `WHERE date = today()` dentro da pipeline e nunca mais consegue reprocessar nada.

**Dizer** — "a run de 3 de outubro não corre no dia 3. Corre quando o dia 3 acaba, porque só aí os dados do dia 3 estão completos." A run chama-se pela fatia que processa, não pelo instante em que arranca.

O intervalo é meio-aberto: `[00:00 do dia 3, 00:00 do dia 4)`. Um registo exatamente à meia-noite pertence a um único dia. É a mesma convenção da API — não por acaso.

A consequência prática é a que interessa: **nenhuma função do pipeline chama `now()`**. A janela entra por parâmetro. Mudar a janela é mudar o que a run processa, e mais nada.

Nota de versão, se alguém perguntar: no Airflow 3 um `schedule="@daily"` simples já não cria data intervals — daí o `CronDataIntervalTimetable` explícito no DAG. E uma run disparada à mão não tem intervalo nenhum; `pipeline/window.py` resolve a janela por três vias, por esta ordem: `conf.date`, data interval, dia anterior.

**Perguntar** — "se eu quiser reprocessar março inteiro, o que tenho de mudar no código?" Nada. Só a janela.

**Ligação** — "E se eu quiser mesmo reprocessar março?"

**Tempo** 9 min
-->

---

<p class="kicker">Apache Airflow</p>

## Catchup vs backfill

<div class="cols">
<div class="card">
<p class="tag">Catchup — o scheduler decide</p>
<pre class="diagram sm"><code>start_date      hoje
    │             │
    ├─ 1 Out ─────┤   runs criadas
    ├─ 2 Out      │   automaticamente
    ├─ 3 Out      │   ao <b>ativar</b> o DAG
    └─ ...        │
</code></pre>
<p>Com <code>catchup=True</code> e um <code>start_date</code> distante, ativar o DAG dispara centenas de runs de uma vez.</p>
<p style="margin-top:8px;color:#F5F5F5">Aqui: <code>catchup=False</code>.</p>
</div>
<div class="card hot">
<p class="tag">Backfill — eu decido</p>
<pre class="diagram sm"><code>airflow backfill create \
  --dag-id tracking_pipeline \
  --from-date <b>2026-10-01</b> \
  --to-date   <b>2026-10-05</b>

→ 5 runs, uma por dia
</code></pre>
<p>Explícito, com limites que eu escolhi, quando eu quiser.</p>
</div>
</div>

<p class="note"><strong class="lime">Só é seguro porque a carga é idempotente.</strong> Se algum desses dias já estava carregado, não se duplica nada — voltamos a isto às 16:00.</p>

<!--
**Objetivo** · Separar duas palavras que toda a gente troca, e plantar a dependência: reprocessar exige idempotência.

**Dizer** — a diferença é só *quem* decide. Catchup é automático e implícito: o scheduler olha para o `start_date`, vê os períodos em falta, e cria as runs. Backfill é manual e explícito: eu digo o intervalo.

A história de terror do catchup: alguém põe `start_date` em janeiro de 2020, ativa o DAG em outubro, e o scheduler começa a criar mil e setecentas runs contra uma API de terceiros que cobra por chamada. Por isso `catchup=False` é um default defensivo razoável.

Ligar ao slide 13: o backfill é também a forma de recuperar **conversões tardias**. Se um postback chegar três dias depois, a run de hoje apanha-o e corrige o dia da visita — mas se quisermos ter a certeza de que uma semana inteira está certa, faz-se um backfill dessa semana.

**Perguntar** — "se eu correr este backfill duas vezes seguidas, o que acontece à base de dados?" É a pergunta cuja resposta vale o bloco das 16:00. Deixar a sala arriscar; não revelar.

**Ligação** — "Temos uma pipeline a correr, agendada, com histórico. Agora vamos parti-la."

**Tempo** 9 min
-->

---

<!-- _class: statement -->

<p class="kicker">Failures</p>

## Agora vamos partir a pipeline

<div class="cols tight">
<div class="card bad"><p class="tag">1</p><h3>HTTP 500</h3><p>a API devolve erro</p></div>
<div class="card bad"><p class="tag">2</p><h3>API lenta</h3><p>o pedido não volta</p></div>
<div class="card bad"><p class="tag">3</p><h3>HTTP 429</h3><p>rate limit, e recupera</p></div>
<div class="card bad"><p class="tag">4</p><h3>Schema drift</h3><p>dois campos mudaram de nome</p></div>
</div>
<div class="spacer"></div>
<div class="cols tight">
<div class="card bad"><p class="tag">5</p><h3>Payload inválido</h3><p><code>revenue</code> e <code>clicks</code> negativos</p></div>
<div class="card bad"><p class="tag">6</p><h3>Run repetida</h3><p>o mesmo dia outra vez</p></div>
<div class="card bad"><p class="tag">7</p><h3>Dois sistemas discordam</h3><p>o daily control não bate</p></div>
</div>

<p class="note" style="margin-top:18px">Um endpoint <code>/admin/mode</code> muda o comportamento da API. <strong>Só para a aula</strong> — em produção isto seria chaos engineering, isolado e autenticado.</p>

<!--
**Objetivo** · Dar o mapa do bloco mais importante da tarde e criar expectativa. Slide curto, falado depressa.

**Dizer** — "a diferença entre quem já pôs uma pipeline em produção e quem ainda não pôs é só esta lista. Vamos passar por ela toda, ao vivo."

Dividir a lista em voz alta por tipo, sem explicar ainda: 1 a 3 são problemas de *transporte*; 4 e 5 são problemas de *contrato*; 6 e 7 são os que **não dão erro nenhum** — e são os que vão ocupar o bloco das 16:00.

**Avisar** — o endpoint `/admin/mode` não tem autenticação e sabota o próprio serviço na mesma porta do tráfego normal. É pedagógico e é indefensável em produção. Em produção usam-se ferramentas próprias (Toxiproxy, Chaos Mesh, Gremlin) em ambientes isolados, com auditoria e um botão de parar tudo. Dizê-lo em voz alta: a sala copia o que vê.

```bash
curl localhost:8000/admin/mode                    # ver o modo atual
curl -X POST localhost:8000/admin/mode/healthy    # repor, sempre no fim
```

**Ligação** — "Antes de partir seja o que for: o Airflow tem um botão chamado retries. Toda a gente o liga. Quase ninguém pensa no que ele faz."

**Tempo** 5 min
-->

---

<p class="kicker">Failures</p>

## Retry não é error handling

<p class="huge">Retry é para erros <span class="lime">transitórios</span>.</p>

<div class="cols">
<div class="card hot">
<p class="tag">Retry faz sentido</p>
<ul>
<li><code>500</code> — o servidor pode recuperar</li>
<li><code>timeout</code> — a rede pode melhorar</li>
<li><code>429</code> — a quota renova-se</li>
<li>deadlock na base de dados</li>
</ul>
<p style="margin-top:8px">O erro <strong>pode</strong> desaparecer sozinho.</p>
</div>
<div class="card bad">
<p class="tag">Retry só adia a falha</p>
<ul>
<li>schema drift</li>
<li><code>revenue</code> negativo</li>
<li>bug na query</li>
<li>credenciais erradas</li>
</ul>
<p style="margin-top:8px">O erro é <strong>determinístico</strong>: daqui a 30 s está igual.</p>
</div>
</div>

<p class="note"><strong class="lime">Por isso <code>validate</code> e <code>quality_check</code> têm <code>retries=0</code>.</strong> Falham logo, e quem lê o log vê o erro mais cedo.</p>

<!--
**Objetivo** · O conceito que separa quem configura Airflow de quem o desenha. É provavelmente o slide mais útil do dia.

**Dizer** — "retry é uma aposta: aposto que o erro desaparece sozinho." Faz sentido quando a causa é externa e temporária. Não faz nenhum quando a causa é a própria mensagem.

O custo de retentar um erro determinístico não é zero: três tentativas, 30 segundos de espera entre elas, timeouts a esgotar — e no fim o mesmo erro, dois minutos mais tarde, com três vezes mais log para ler. E, pior, cria a ilusão de que o sistema "está a tentar resolver".

Abrir o DAG e mostrar as duas linhas: `validate` e `quality_check` com `retries=0`, tudo o resto com os `retries=2` do `default_args`. São duas palavras no código e são uma decisão de arquitetura.

**Perguntar** — "e se o `load_facts` falhar por deadlock no PostgreSQL? Retry ou não?" Sim: é transitório. "E se falhar por violação de FK?" Não: faltam dimensões, e vão continuar a faltar.

Mencionar `retry_exponential_backoff=True`: em produção não se retenta de 30 em 30 segundos, dobra-se o intervalo.

**Ligação** — "Vamos ver os dois lados ao vivo: um erro que o retry não salva, e um que salva."

**Tempo** 8 min
-->

---

<p class="kicker">Failures &nbsp;·&nbsp; <span class="demo">DEMO 3 · DEMO 4</span></p>

## 500 e 429: quando o retry salva

<div class="cols">
<div class="card bad">
<p class="tag">http_500 — o retry não salva</p>
<pre class="diagram sm"><code>check_api  tentativa 1   <b>500</b>
           ...30 s...
           tentativa 2   <b>500</b>
           ...30 s...
           tentativa 3   <b>500</b>
           ────────────────────
           <b>failed</b>

extract .......... upstream_failed
validate ......... upstream_failed
load_* ........... upstream_failed
</code></pre>
<p>Nada escrito na base de dados. A falha parou tudo.</p>
</div>
<div class="card hot">
<p class="tag">rate_limit — o retry salva</p>
<pre class="diagram sm"><code>check_api  tentativa 1   <b>429</b>
           ...30 s...
           tentativa 2   <b>429</b>
           ...30 s...
           tentativa 3   <b>200</b>
           ────────────────────
           <b>success</b>

o DAG continua, e termina em verde
</code></pre>
<p>Uma hora depois ninguém sabe que isto aconteceu.</p>
</div>
</div>

<p class="big" style="font-size:26px;margin-top:14px">No segundo caso, o retry <span class="lime">resolveu</span> o problema — ou <span class="lime">escondeu-o</span>?</p>

<!--
**Objetivo** · Ver os dois comportamentos de perto e abrir a discussão que leva, cinco slides à frente, à observabilidade.

**Demo 3 — HTTP 500** (6 min)
```bash
curl -X POST localhost:8000/admin/mode/http_500
docker compose exec airflow airflow dags trigger tracking_pipeline --conf '{"date": "2026-10-03"}'
# UI: check_api amarelo (up_for_retry) e depois vermelho; o resto cinzento-escuro
curl -X POST localhost:8000/admin/mode/healthy
```
Mostrar na UI a diferença de cor entre `failed` (correu e falhou) e `upstream_failed` (nunca correu). E mostrar o botão *Clear* numa única task: é como se repete uma etapa sem repetir o DAG todo.

**Demo 4 — HTTP 429** (6 min)
```bash
curl -X POST "localhost:8000/admin/mode/rate_limit?fail_times=2"
docker compose exec airflow airflow dags trigger tracking_pipeline --conf '{"date": "2026-10-03"}'
# duas tentativas falham, a terceira passa; o DAG acaba verde
curl -X POST localhost:8000/admin/mode/healthy
```
Se houver tempo, repetir com `fail_times=3`: agora os dois retries não chegam e o DAG falha. Dois caracteres de diferença na configuração, outro resultado.

**Discussão** (3 min) — a pergunta do slide. As duas respostas estão certas: resolveu a execução de hoje *e* escondeu que a API nos está a limitar. Se isto acontecer todos os dias, ninguém dá por nada até a quota ser cortada a sério. O retry trata o sintoma; a métrica «número de retries por task» é o que mostra a doença. Guardar esta frase para o bloco das 16:35.

**Tempo** 14 min
-->

---

<p class="kicker">Failures &nbsp;·&nbsp; <span class="demo">DEMO 5</span></p>

## A API está lenta

<div class="cols">
<div class="card hot">
<p class="tag">check_api</p>
<p style="color:#F5F5F5"><code>GET /health</code></p>
<h3 class="lime">200 em 8 ms</h3>
</div>
<div class="card bad">
<p class="tag">extract</p>
<p style="color:#F5F5F5"><code>GET /conversions</code></p>
<h3 class="red">timeout aos 5 s</h3>
</div>
</div>

<p class="big" style="margin-top:18px">A API está saudável?</p>

<p class="note"><strong class="lime">Um health check não prova que o serviço consegue servir os dados.</strong></p>

<div class="cols" style="margin-top:14px">
<div class="card"><p class="tag">Timeout 1 · HTTP</p><p><code>5 s</code> — o pedido desiste. Apanha a API pendurada.</p></div>
<div class="card"><p class="tag">Timeout 2 · task</p><p><code>2 min</code> — o Airflow mata a tentativa. Apanha tudo o resto.</p></div>
</div>

<!--
**Objetivo** · Mostrar o primeiro cenário em que a monitorização mente, e introduzir as duas camadas de timeout.

**Demo 5** (8 min)
```bash
curl -X POST localhost:8000/admin/mode/slow
docker compose exec airflow airflow dags trigger tracking_pipeline --conf '{"date": "2026-10-03"}'
# check_api passa em milissegundos; extract esgota o timeout 3 vezes e falha
curl -X POST localhost:8000/admin/mode/healthy
```
É a demo mais lenta da tarde (cerca de 1,5 min de esperas). Aproveitar o tempo morto para a discussão abaixo em vez de ficar a olhar para o ecrã.

**Dizer** — o modo `slow` atrasa só os endpoints de *dados*; o `/health` continua instantâneo. É deliberado e é realista: um `/health` que devolve `{"status":"ok"}` não toca na base de dados, não lê disco, não faz nada. Está sempre verde. Mede que o processo está vivo, não que o serviço é útil.

As duas camadas: o timeout HTTP tem de ser bastante *menor* do que o `execution_timeout` da task. Se fossem iguais, ou ao contrário, o Airflow mataria a tentativa antes de o cliente HTTP conseguir desistir com uma mensagem decente.

**Perguntar** — "o que é que o vosso health check verifica hoje?" E a pergunta a sério: "um health check devia tocar na base de dados?" Não há resposta única: se tocar, deteta mais; se tocar, também cai quando a base está lenta e pode tirar o serviço de rotação sem necessidade.

Guardar para a observabilidade: a sonda do Prometheus não pode apontar só ao `/health` — tem de sondar também um endpoint de dados. É exatamente este cenário.

**Tempo** 9 min
-->

---

<p class="kicker">Failures &nbsp;·&nbsp; <span class="demo">DEMO 6</span></p>

## Schema drift, ao vivo

<div class="chips">
<span class="chip ok">HTTP 200</span>
<span class="chip ok">latência 90 ms</span>
<span class="chip ok">serviço UP</span>
<span class="chip ok">JSON válido</span>
<span class="chip bad">Pydantic falha</span>
</div>

<div class="spacer"></div>

<p class="huge">Availability <span class="lime">≠</span> correctness.</p>

<div class="cols">
<div class="card">
<p class="tag">O que a infraestrutura vê</p>
<p>Nada. Uptime 100 %, latência normal, zero erros 5xx. Qualquer painel de monitorização clássico fica verde.</p>
</div>
<div class="card hot">
<p class="tag">O que a pipeline vê</p>
<p><code>validate</code> falha: <code>172 de 172</code> conversões e <code>190 de 190</code> custos inválidos. Tudo a jusante fica <code>upstream_failed</code>.</p>
</div>
</div>

<!--
**Objetivo** · Fechar o bloco de falhas com o cenário que justifica toda a conversa de observabilidade de dados.

**Demo 6** (6 min)
```bash
curl -X POST localhost:8000/admin/mode/schema_drift
curl "localhost:8000/conversions?start_date=2026-10-03&end_date=2026-10-04&limit=2"   # revenue_amount
docker compose exec airflow airflow dags trigger tracking_pipeline --conf '{"date": "2026-10-03"}'
# extract passa (os dados chegaram!), validate falha de imediato, sem retries
curl -X POST localhost:8000/admin/mode/healthy
```
Mostrar primeiro o `curl` — a sala tem de ver os campos renomeados com os próprios olhos antes de ver a task vermelha. Depois abrir o log do `validate` e ler as quatro linhas: `revenue → missing`, `revenue_amount → extra_forbidden`, e o mesmo para `cost` / `cost_amount`.

Reparar no tempo: o `validate` falha em menos de um segundo. Sem retries, porque não havia nada a ganhar.

**Dizer** — neste modo a API devolve o payload *cru*, sem o passar pelos seus próprios modelos: é um producer que mudou sem avisar. Nenhuma validação do lado dele o impede. É literalmente a razão pela qual o consumer valida outra vez.

Fazer a ponte com o cenário 5 (`invalid_payload`), que não vale uma demo própria: o mecanismo é o mesmo, a causa é outra — ali o schema está certo e os *valores* é que são impossíveis (`revenue` e `clicks` negativos, `country_code` com três letras). E a proporção é diferente: 13 em 172, não 172 em 172.

**Perguntar** — "se não tivéssemos a task `validate`, o que acontecia?" A carga corria em verde e a receita do dia ficava a zero. Alguém ia tomar uma decisão com esse zero.

**Ligação** — "Reparem que já disparámos este mesmo dia, o dia 3, umas cinco vezes esta tarde. Alguém está preocupado com isso?"

**Tempo** 8 min
-->

---

<p class="kicker">Idempotência e qualidade</p>

## O Airflow vai executar de novo

<div class="chips">
<span class="chip">retry automático</span>
<span class="chip">clear task na UI</span>
<span class="chip">trigger manual</span>
<span class="chip">backfill</span>
<span class="chip">conversões tardias</span>
</div>

<div class="flow" style="margin:18px 0">
<span class="box">todos levam ao mesmo</span><span class="arrow">→</span><span class="box hot">o mesmo período, processado outra vez</span>
</div>

<p class="huge">Vamos duplicar os dados?</p>

<p class="note">Não é uma hipótese remota. Esta tarde já disparámos o dia 3 de outubro <strong>cinco vezes</strong>.</p>

<!--
**Objetivo** · Fazer a sala chegar sozinha à pergunta antes de eu dar a resposta. O argumento é forte porque acabámos de o fazer sem querer.

**Dizer** — listar os cinco gestos. Dois são do Airflow sozinho (retry, catchup), dois são nossos (clear, trigger, backfill) — e o quinto não é um gesto de ninguém: as **conversões tardias** obrigam-nos a reprocessar dias antigos de propósito, para sempre. Reprocessar não é a exceção neste domínio; é a rotina.

Depois a pergunta, e **esperar**. Deixar a sala arriscar. Metade vai dizer que sim, duplica; a outra metade vai dizer que não, "porque há uma chave primária". A segunda está mais perto — mas uma PK sozinha não resolve: um `INSERT` simples contra uma chave existente dá erro e a task falha. Não duplicar e falhar também não serve.

**Perguntar** — antes de avançar, correr na sala:
```bash
docker compose exec postgres psql -U tracking -d analytics \
  -c "SELECT visit_date, count(*) FROM fact_conversions GROUP BY 1 ORDER BY 1"
```
A contagem do dia 3 não mudou depois de cinco execuções. A sala tem de ver o número antes da explicação.

**Ligação** — "Isto tem nome, e é a propriedade que torna tudo o que vimos hoje seguro."

**Tempo** 5 min
-->

---

<p class="kicker">Idempotência e qualidade &nbsp;·&nbsp; <span class="demo">DEMO 7</span></p>

## Idempotency

<p class="big">Executar <span class="lime">uma vez</span> ou <span class="lime">dez vezes</span> deixa o sistema no mesmo estado.</p>

<div class="cols">
<div>

<table class="sm">
<tr><th>execução</th><th><code>INSERT</code> simples</th><th><code>upsert</code></th></tr>
<tr><td>run 1</td><td>172 linhas</td><td>172 linhas</td></tr>
<tr><td>run 2</td><td><strong class="red">344</strong></td><td>172</td></tr>
<tr><td>run 3</td><td><strong class="red">516</strong></td><td>172</td></tr>
</table>

<p class="note">172 conversões distintas nos dois casos. À esquerda, a receita do dia passou de <strong>4 531,80</strong> a <strong class="red">13 595,40 USD</strong>.</p>

</div>
<div>

```sql
INSERT INTO fact_conversions (...)
VALUES (...)
ON CONFLICT (click_id,
             conversion_type_id,
             postback_timestamp)
DO UPDATE SET revenue = EXCLUDED.revenue,
              updated_at = now();
```

<p class="note">Três peças: a <strong class="lime">chave composta</strong> identifica a linha, o <strong class="lime">upsert</strong> diz o que fazer quando já existe, e a origem é <strong class="lime">determinística</strong>.</p>

</div>
</div>

<!--
**Objetivo** · Dar a definição, mostrar o contraste com números, e deixar claro que isto não é um truque de SQL: é o que torna retries e backfills aceitáveis.

**Demo 7** (8 min)
```bash
docker compose exec -w /opt/airflow/project airflow python -m scripts.demo_idempotency
```
O script carrega o mesmo dia três vezes em duas tabelas idénticas — uma sem chave e com `INSERT`, outra com a chave composta e upsert — e imprime a tabela do slide. **O número que convence a sala não é 516: é a receita.** 13 595 USD contra 4 532. Triplicar linhas é abstrato; triplicar a receita de um relatório é um despedimento.

Mostrar também `loaded_at` (não muda) e `updated_at` (muda em cada run): é como se distingue "vi esta linha pela primeira vez" de "recarreguei-a".

Depois, no DAG real:
```bash
docker compose exec airflow airflow dags trigger tracking_pipeline --conf '{"date": "2026-10-03"}'
# log de load_facts: fact_conversions {'inserted': 0, 'updated': 172}
```
Comparar com o `{'inserted': 172, 'updated': 0}` da primeira run da tarde.

**Dizer** — a terceira peça é a que se esquece: o determinismo da origem. Se a API gerasse um `click_id` novo a cada chamada, o upsert não servia de nada. Idempotência não é só uma cláusula SQL; é uma propriedade de ponta a ponta — e, repare-se, **só é possível porque a chave é natural**. Com um `id SERIAL`, cada carga criaria linhas novas e o `ON CONFLICT` nunca dispararia.

**Alternativas, para discussão** — `ON CONFLICT DO NOTHING` também é idempotente, mas nunca corrige um valor que mudou na origem. *Delete-then-insert* da janela, numa transação, também funciona: mais simples de explicar, mais caro, mais fácil de fazer mal.

**Perguntar** — "e se a origem corrigir a receita de uma conversão de ontem? Qual das duas estratégias é que quero?"

**Ligação** — "A carga é segura. Mas carregar bem não é a mesma coisa que ter dados bons."

**Tempo** 12 min
-->

---

<p class="kicker">Idempotência e qualidade</p>

## Validate ≠ Data Quality

<div class="cols">
<div class="card">
<p class="tag">validate — antes do load</p>
<h3>Este <span class="lime">registo</span> tem a forma certa?</h3>
<ul>
<li>Pydantic, uma linha de cada vez</li>
<li>schema, campos obrigatórios e opcionais</li>
<li>tipos, enums, UUIDs</li>
<li><code>cost >= 0</code>, país com 2 letras, hora certa</li>
</ul>
</div>
<div class="card hot">
<p class="tag">quality_check — depois do load</p>
<h3>Este <span class="lime">conjunto</span> faz sentido?</h3>
<ul>
<li>SQL, sobre a janela já carregada</li>
<li><code>row count > 0</code> · freshness (&lt; 6 h)</li>
<li>chaves compostas únicas · FKs válidas</li>
<li><code>postback >= visita</code> · fonte coerente</li>
<li><strong class="lime">reconciliação com o daily control</strong></li>
</ul>
</div>
</div>

<p class="note">Corre <strong>todas</strong> as verificações, mesmo depois da primeira falhar, e falha no fim com a lista completa. Um relatório, não um alarme isolado.</p>

<!--
**Objetivo** · Fechar o par que atravessa a aula: contrato de registo vs qualidade de conjunto. Duas perguntas, dois momentos, duas tecnologias.

**Dizer** — a distinção que arruma tudo: nenhum registo individual está errado num dataset que só tem metade das linhas. O Pydantic não tem como saber isso — vê uma linha de cada vez. Só uma query sobre o conjunto responde.

Passar pelos checks, rápido:
- *row count > 0* — uma carga vazia é quase sempre um erro silencioso.
- *freshness* — a hora de custo mais recente tem de estar a menos de 6 horas do fim da janela. Apanha extrações truncadas e dias a meio.
- *chaves únicas e FKs* — já garantidas por constraints. Verificam-se na mesma: a constraint é a primeira linha de defesa, o check é a segunda (protege-te de um destino sem FKs, como um data warehouse) e dá uma métrica auditável.
- *postback >= visita* — não se converte antes de clicar.
- *fonte coerente* — a `traffic_source_id` da conversão tem de ser a da campanha dela. É o slide 9 a tornar-se um teste.

**Assumir o que fica de fora** — qualquer regra do tipo `conversions <= clicks` **não** é uma lei universal: aqui um mesmo click gera conversões de tipo 1 e de tipo 2. Seria legítimo acrescentá-la num dataset onde se saiba que é verdade — como regra *específica desse dataset*.

**Ligação** — "Falta falar do último, que é o mais interessante de todos."

**Tempo** 8 min
-->

---

<p class="kicker">Idempotência e qualidade &nbsp;·&nbsp; <span class="demo">DEMO 8</span></p>

## Reconciliação: dois sistemas, um número

<div class="cols">
<div>

<pre class="diagram"><code>  <b>eventos</b>                  <b>daily control</b>
  (Mongo)                   (Postgres)

  Σ revenue das            revenue do dia
  conversões do dia        por campanha
  Σ cost das horas         investment
         │                       │
         └───────► <b>=</b> ? ◄────────┘
                   ±0,05
</code></pre>

</div>
<div>

<p class="big" style="font-size:28px">Nenhuma <em>constraint</em> apanha dois sistemas a discordar.</p>

<p class="note">É o único check que compara a nossa pipeline com <strong>uma fonte independente</strong>. Tudo o resto verifica se somos coerentes connosco próprios.</p>

<div class="card hot">
<p class="tag">Exceto quando é à mão</p>
<p><code>is_manual = true</code> significa que uma pessoa escreveu aquele número. Nesse caso <strong>não</strong> se exige que bata certo — exigir seria transformar uma decisão humana num alarme diário.</p>
</div>

</div>
</div>

<!--
**Objetivo** · Mostrar o check mais valioso do projeto e, com ele, a ideia de que qualidade de dados acaba quase sempre em *reconciliação*.

**Dizer** — todos os outros checks perguntam "sou coerente comigo próprio?". Este pergunta "concordo com quem olha para o mesmo negócio por outro caminho?". É o que apanha o erro que nenhuma constraint apanha: uma conversão perdida, um custo contado a dobrar, uma janela mal alinhada.

A tolerância de 0,05 existe por causa de arredondamentos (o daily control guarda 2 casas decimais, os eventos 4). Uma tolerância é uma decisão de negócio: demasiado apertada e o alarme toca todos os dias por cêntimos; demasiado larga e deixa passar erros a sério.

E o `is_manual` é a parte honesta do desenho: num sistema real há sempre alguém a corrigir números à mão, e o check tem de saber conviver com isso em vez de fingir que não acontece.

**Demo 8** (8 min) — nenhum modo da API provoca isto: a API só parte o contrato, e isso falha no `validate`. Adultera-se a base de dados:
```bash
docker compose exec postgres psql -U tracking -d analytics -c \
  "UPDATE fact_daily_control SET revenue = revenue + 100
   WHERE NOT is_manual AND date = '2026-10-03'
     AND campaign_id = (SELECT campaign_id FROM fact_daily_control
                        WHERE NOT is_manual AND date = '2026-10-03' LIMIT 1)"
```
Depois, na UI, *Clear* só na task `quality_check` (sem as dependentes): falha em `reconciliacao: revenue (eventos vs daily control)`. Para curar, re-correr o DAG inteiro desse dia — o upsert repõe o valor certo. É a idempotência a trabalhar a nosso favor, dez minutos depois de a termos explicado.

Outras adulterações para experimentar, se a sala estiver viva: pôr um `visit_timestamp` depois do `postback_timestamp`, ou trocar a `traffic_source_id` de uma conversão.

**Perguntar** — "no vosso trabalho, que dois sistemas é que deviam concordar e nunca ninguém verifica?"

**Ligação** — "Reparem no que acabámos de fazer: estragámos os dados sem partir a pipeline."

**Tempo** 10 min
-->

---

<!-- _class: statement -->

<p class="kicker">Idempotência e qualidade</p>

<div class="cols" style="margin-bottom:28px">
<div class="card hot">
<p class="tag">Pipeline</p>
<h3 class="lime" style="font-size:32px">SUCCESS</h3>
<p>sete tasks verdes, 18 segundos, zero retries</p>
</div>
<div class="card bad">
<p class="tag">Data</p>
<h3 class="red" style="font-size:32px">ERRADO</h3>
<p>metade das linhas, receita a zero, ontem em vez de hoje</p>
</div>
</div>

<p class="huge">Uma pipeline verde pode<br>entregar <span class="lime">dados errados</span>.</p>

<p class="note">O job ter corrido com sucesso não diz <strong>nada</strong> sobre os dados.</p>

<!--
**Objetivo** · A frase-charneira da aula. É a ponte para observabilidade e, provavelmente, a única coisa que alguns vão repetir à equipa na segunda-feira.

**Dizer** — deixar o slide respirar. Não encher de palavras.

Dar os exemplos concretos do próprio dia: sem a task `validate`, o schema drift teria corrido em verde com a receita a zero. Sem o `quality_check`, uma extração truncada carregaria 100 das 172 conversões sem queixa nenhuma, e o daily control seria o único a saber. Em ambos os casos a UI do Airflow estaria toda verde e alguém ia tomar decisões com aqueles números.

E a inversa também é verdade e menos óbvia: o job pode falhar e os dados estarem perfeitos — falhou *antes* de escrever.

**Perguntar** — "quem é que, no vosso trabalho, repara primeiro quando um número está errado?" A resposta honesta é quase sempre "o negócio, numa reunião". Esse é o problema que a observabilidade existe para resolver.

**Ligação** — "Então a pergunta final da tarde é esta."

**Tempo** 6 min
-->

---

<p class="kicker">Observabilidade</p>

## Como sabemos que está tudo bem<br>sem ficar a olhar para o Airflow?

<div class="cols">
<div class="card">
<p class="tag">Pipeline</p>
<h3>O job correu?</h3>
<p>sucesso e falha de DAG e tasks, retries, duração, atraso do scheduler</p>
</div>
<div class="card">
<p class="tag">Source</p>
<h3>A fonte está bem?</h3>
<p>disponibilidade, latência, códigos HTTP do producer</p>
</div>
<div class="card hot">
<p class="tag">Data</p>
<h3>Os dados estão certos?</h3>
<p>volume, freshness, duplicados, falhas de validação, reconciliação</p>
</div>
</div>

<p class="note" style="margin-top:18px">Dos sete cenários de hoje, <strong class="lime">três</strong> — schema drift, payload inválido e daily control a discordar — passam despercebidos a qualquer monitorização de disponibilidade.</p>

<!--
**Objetivo** · Mostrar que "observabilidade" não é uma ferramenta: são três perguntas distintas, e cada uma precisa de sinais próprios.

**Dizer** — a razão de serem três e não uma: cada nível pode estar verde enquanto outro está vermelho.
- Pipeline verde, dados errados — é o slide anterior.
- Source verde, dados errados — é o schema drift.
- Pipeline vermelha, dados perfeitos — falhou antes de escrever.

Percorrer os sete cenários da tarde e perguntar, para cada um, *quem o vê primeiro*. O 500 e o 429: source e pipeline. A API lenta: source — mas só se a sonda apontar a um endpoint de dados, não ao `/health`. O schema drift e o payload inválido: só a pipeline, via `validate`. A run repetida e a discordância do daily control: só os dados.

**Dizer sobre alertas** — alertar sobre sintomas que alguém tem de resolver, não sobre tudo o que se consegue medir. Uma task que falhou e recuperou ao segundo retry não acorda ninguém. Um DAG que falhou depois de todos os retries, ou dados com mais de seis horas, sim.

**Perguntar** — "qual dos três níveis é que existe hoje no vosso trabalho?" Quase sempre só o primeiro, e às vezes nem isso.

**Ligação** — "Nada disto está instalado neste projeto. Mas está desenhado."

**Tempo** 7 min
-->

---

<p class="kicker">Observabilidade</p>

## Próxima evolução

<pre class="diagram"><code>  API  ──►  <b>Blackbox Exporter</b>  ──►  <b>Prometheus</b>  ──►  <b>Grafana</b>
  /health             sonda HTTP            séries temporais    painéis
  /conversions?limit=1  por fora                                e alertas

  Airflow metrics ───────────────────────►  <b>Prometheus</b>

  PostgreSQL (analytics) ─────────────────────────────────►  <b>Grafana</b>
  count, max(event_ts), reconciliação
</code></pre>

<p class="big" style="font-size:28px;margin-top:18px">Observability começa por saber<br><span class="lime">que pergunta queremos responder</span>.</p>

<p class="note">Não está instalado, de propósito. Está escrito em <code>docs/observability-roadmap.md</code> — três serviços novos no <code>docker-compose.yml</code> e uma pasta de configuração.</p>

<!--
**Objetivo** · Dar o caminho sem o percorrer. A sala sai a saber o que pedir, não a saber configurar Prometheus.

**Dizer** — o Blackbox Exporter testa a API *por fora*, como um cliente qualquer: faz um pedido HTTP e produz métricas sobre a resposta (`probe_success`, `probe_duration_seconds`, `probe_http_status_code`). A API não precisa de saber que está a ser observada.

Dois pormenores que vêm diretamente da tarde de hoje:
1. Sondar só o `/health` não deteta o modo `slow`. Sonda-se também um endpoint de dados.
2. *Observer effect*: uma sonda é um pedido como outro qualquer. No modo `rate_limit`, consome quota. É por isso que o healthcheck do Docker desta formação aponta para `/admin/mode` e não para `/health`.

A terceira seta é a que quase toda a gente esquece: as métricas de *dados* não vêm do Airflow nem da API — vêm dos próprios dados. Ou se consulta a base diretamente, ou se regista cada run numa tabela (`pipeline_run_log`: janela, linhas extraídas/validadas/carregadas, inseridas vs atualizadas, resultado dos checks, duração). A pipeline já produz estes números — estão nos XComs e nos logs. Falta guardá-los.

E um que é específico deste projeto: a **diferença de reconciliação** é a melhor métrica de dados que temos. Um gráfico com `revenue_diff` por dia diria, sozinho, se a pipeline está a dizer a verdade.

**Tempo** 6 min
-->

---

<p class="kicker">Fecho</p>

## O sistema completo

<div class="cols">
<div>

<pre class="diagram sm"><code>   <b>API</b>            ← producer
    ↓
  <b>Airflow</b>          ← orquestra
    ↓
  <b>Contract</b>         ← Pydantic
    ↓
  <b>Pandas</b>           ← transforma
    ↓
 <b>PostgreSQL</b>        ← upsert, chave composta
    ↓
 <b>Analytics</b>         ← soma, depois divide
</code></pre>

<div class="chips" style="margin-top:10px">
<span class="chip ok">retries</span>
<span class="chip ok">idempotency</span>
<span class="chip ok">quality</span>
<span class="chip ok">reconciliação</span>
<span class="chip">observability</span>
</div>

</div>
<div>
<div class="card hot">
<p class="tag">Takeaways</p>
<ul style="font-size:17px;color:#F5F5F5">
<li><strong>Grain antes de código.</strong></li>
<li><strong>Escolher a chave é escolher o grain.</strong></li>
<li><strong>Airflow orquestra; não transforma.</strong></li>
<li><strong>Retry é para falhas transitórias.</strong></li>
<li><strong>Soma primeiro, divide depois. E nulo não é zero.</strong></li>
<li><strong>Reprocessar exige idempotência.</strong></li>
</ul>
</div>
</div>
</div>

<!--
**Objetivo** · Fechar o círculo com o slide 2 e deixar seis frases que cabem na cabeça.

**Dizer** — é o mesmo desenho da abertura, com uma diferença: agora cada seta tem um nome e uma razão. Percorrer de cima a baixo em trinta segundos e parar em cada *chip* para dizer onde é que ele vive no código.

Ler os takeaways devagar, um de cada vez, e para cada um pedir à sala o momento da tarde em que ele apareceu. Se não se lembrarem de algum, esse é o que vale a pena repetir.

A última chip, *observability*, está a cinzento de propósito: é a única das cinco que ainda não existe.

**Números que vale a pena deixar** — 95 testes automáticos a passar, em 1 a 2 segundos, sem Airflow e sem API ligados. É isso que o desenho «o pipeline não importa o Airflow» compra.

**Deixar trabalho** — o README tem os exercícios, agrupados por tema. Os três que recomendo: pôr `retries=0` e repetir o cenário do 500; escrever o ROAS semanal nas duas versões, certa e errada; e trocar `DO UPDATE` por `DO NOTHING` e ver o que muda.

**Tempo** 5 min
-->

---

<!-- _class: statement -->

<p class="kicker">Fecho &nbsp;·&nbsp; discussão</p>

<p class="huge">Se esta pipeline estivesse<br>em produção amanhã,<br><span class="lime">o que ainda faltaria?</span></p>

<p class="note">Sem respostas no slide. A sala tem 8 minutos.</p>

<!--
**Objetivo** · Terminar com a sala a falar, não comigo. E recolher, sem parecer avaliação, o que ficou e o que não ficou.

**Como conduzir** — escrever as respostas no quadro à medida que saem. Não corrigir, não ordenar. Quando a lista parar, agrupá-la em voz alta.

**Respostas prováveis, e o que dizer de cada uma**
- *Observabilidade e alertas* — já temos o roteiro: `docs/observability-roadmap.md`.
- *Secrets* — hoje está tudo num `.env`. Em produção: um gestor de segredos, e o `DATABASE_URL` nunca em texto no disco de um worker.
- *Segurança* — o Airflow desta aula não tem login. E o `/admin/mode` não tem autenticação nenhuma. Nenhuma das duas sobrevive a produção.
- *CI/CD* — os 95 testes existem e correm em 1-2 s; falta corrê-los automaticamente a cada push.
- *SLA* — "os dados de ontem às 6h" é uma promessa. Sem ela escrita, não há como dizer se a pipeline está atrasada.
- *Quarentena* — falhar tudo por treze registos maus não escala.
- *Escala* — `standalone` e `LocalExecutor` num container. Em produção: componentes separados, executor distribuído (Celery, Kubernetes), base de metadados gerida com backups.
- *Backups e recuperação* — e já agora: quanto tempo demora a reconstruir o warehouse do zero? Com backfill idempotente, é uma pergunta com resposta.
- *Governança* — quem é dono de cada tabela, quem a pode ler, quanto tempo se guarda. E quem decide a definição de cada métrica.
- *SCD tipo 2* — hoje perdemos o histórico das dimensões. Se uma campanha mudar de nome, os relatórios antigos mudam com ela.

Se a sala não mencionar **secrets** nem **SLA**, pô-los eu: são os dois mais esquecidos e os dois mais caros.

**Fechar** — "Hoje construímos a coisa. Da próxima, aprendemos a confiar nela sem olhar para ela."

**Tempo** 8 min
-->

---

<!-- _class: statement -->

<p class="kicker">Anexo · referência</p>

# O catálogo<br><strong>ao detalhe</strong>

<p class="note" style="font-size:20px">As cinco páginas seguintes não se leem em aula. São para projetar quando alguém perguntar «e esta coluna, o que é?», e para ler depois.</p>

<p class="note">Versão completa, com linhagem e glossário: <code>docs/data-catalog.md</code>.</p>

<!--
**Objetivo** · Separar claramente o que é aula do que é referência.

**Como usar** — não percorrer estas páginas de fio a pavio. Servem para três momentos: alguém pergunta pelo significado de uma coluna; alguém quer saber de onde vem um número; ou no fim, como material de leitura.

Se a sessão estiver a correr bem e sobrarem dez minutos, a página da linhagem (a última) é a que mais vale a pena mostrar: é o mapa de «este número veio daqui».

**Tempo** 0 min em aula
-->

---

<p class="kicker">Anexo · referência</p>

## As quatro dimensões

<table class="sm">
<tr><th>Dimensão</th><th>Colunas</th><th>Nota</th></tr>
<tr><td>dim_workspace</td><td><code>workspace_id</code> <strong class="lime">PK</strong> · <code>name</code></td><td>2 linhas</td></tr>
<tr><td>dim_traffic_source</td><td><code>traffic_source_id</code> <strong class="lime">PK</strong> · <code>name</code> · <code>currency_code</code> · <code>deleted</code></td><td><em>soft delete</em>: não se apaga, as facts antigas apontam para cá</td></tr>
<tr><td>dim_campaign</td><td><code>campaign_id</code> <strong class="lime">PK</strong> · <code>name</code> · <code>geo</code> · <code>traffic_source_id</code> FK · <code>workspace_id</code> FK · <code>is_paused</code> · <code>created</code></td><td><code>geo</code> é ISO-2 ou <code>WW</code> (worldwide)</td></tr>
<tr><td>dim_offer</td><td><code>offer_id</code> <strong class="lime">PK</strong> · <code>name</code> · <code>country_code</code>? · <code>affiliate_network_id</code> · <code>affiliate_network_name</code> · <code>payout</code> · <code>currency_code</code> · <code>deleted</code></td><td><code>country_code</code> nulo = oferta global</td></tr>
</table>

<div class="cols tight">
<div class="card"><p class="tag">Em todas</p><p><code>loaded_at</code> e <code>updated_at</code>: quando a linha apareceu e quando foi recarregada.</p></div>
<div class="card"><p class="tag">SCD tipo 1</p><p>Mudar o nome de uma campanha substitui o antigo. Perde-se o histórico — é uma escolha, não um esquecimento.</p></div>
<div class="card hot"><p class="tag">A rede de afiliação</p><p>Vive como <strong>atributos da oferta</strong>, sem dimensão própria. Passa a dimensão quando tiver atributos seus.</p></div>
</div>

<!--
**Objetivo** · Referência das dimensões, com as três decisões que não se veem no DDL.

**Se perguntarem pelo `deleted`** — é *soft delete*: a fonte de tráfego já não está ativa, mas a linha fica. Se a apagássemos, todas as conversões antigas ficariam órfãs. A regra geral num warehouse: dimensões não se apagam, marcam-se.

**Se perguntarem pelo `payout` da oferta** — é o valor acordado por conversão, na moeda da oferta. Não é o mesmo que a `revenue` de uma conversão concreta, que pode variar. O `payout` é o *contrato comercial*; a `revenue` é o que realmente aconteceu.

**Se perguntarem porque é que `affiliate_network` não é dimensão** — porque só tem `id` e `name`. No dia em que tiver condições de pagamento, moeda e contacto, passa a dimensão e `dim_offer` ganha uma FK.
-->

---

<p class="kicker">Anexo · referência</p>

## fact_conversions

<p class="note" style="margin-bottom:10px">1 linha = 1 conversão (um postback) · ≈ 170 por dia</p>

<table class="sm">
<tr><th>Coluna</th><th>Tipo</th><th>Nulo?</th><th>De onde vem</th></tr>
<tr><td>click_id</td><td>TEXT</td><td>não</td><td>32 hex, da origem · <strong class="lime">PK</strong></td></tr>
<tr><td>conversion_type_id</td><td>INTEGER</td><td>não</td><td>1 = principal, 2 = secundária · <strong class="lime">PK</strong></td></tr>
<tr><td>postback_timestamp</td><td>TIMESTAMPTZ</td><td>não</td><td>quando a rede nos reportou · <strong class="lime">PK</strong> · janela de extração</td></tr>
<tr><td>visit_timestamp</td><td>TIMESTAMPTZ</td><td>não</td><td>quando o utilizador clicou</td></tr>
<tr><td>visit_date</td><td>DATE</td><td>não</td><td><em>calculada</em> no transform · a data dos relatórios</td></tr>
<tr><td>campaign_id</td><td>TEXT</td><td>não</td><td>FK → <code>dim_campaign</code></td></tr>
<tr><td>traffic_source_id</td><td>TEXT</td><td>não</td><td>FK → <code>dim_traffic_source</code> · tem de bater com a da campanha</td></tr>
<tr><td>offer_id</td><td>TEXT</td><td>não</td><td>FK → <code>dim_offer</code></td></tr>
<tr><td>country_code</td><td>CHAR(2)</td><td>não</td><td>país do visitante, ISO-2</td></tr>
<tr><td>revenue</td><td>NUMERIC(14,4)</td><td>não</td><td>USD · métrica aditiva · <code>CHECK >= 0</code></td></tr>
<tr><td>revenue_original_currency</td><td>NUMERIC(14,4)</td><td>não</td><td>o mesmo, na moeda da oferta</td></tr>
</table>

<!--
**Objetivo** · Referência da fact central.

**As três perguntas que esta tabela costuma levantar**

*Porquê duas receitas?* Porque o anunciante paga numa moeda e nós reportamos noutra. Guardar as duas evita ter de reconstituir a taxa de câmbio do dia — que ninguém guarda e que muda.

*Porquê `traffic_source_id` aqui, se a campanha já o tem?* Porque vem assim da origem, e porque é um check: se não bater com o da campanha, há incoerência entre sistemas. Está no `quality_check`.

*O que é o `conversion_type_id`?* O tipo de conversão: o 1 é a principal (o depósito, a compra), o 2 é uma secundária (um upsell, um segundo depósito). É por isso que o mesmo `click_id` pode ter duas linhas — e é por isso que a chave é composta.

**Não existe** `cost` nem `profit` nem `roi` por conversão, embora a origem os tenha. São derivados, e derivados não se guardam por linha.
-->

---

<p class="kicker">Anexo · referência</p>

## fact_daily_control &nbsp;e&nbsp; as views

<div class="cols">
<div>

<p class="note" style="margin-bottom:8px">1 linha = 1 campanha × 1 dia · 6 por dia</p>

<table class="sm">
<tr><th>Coluna</th><th>Tipo</th><th>De onde vem</th></tr>
<tr><td>date</td><td>DATE</td><td>o dia · <strong class="lime">PK</strong></td></tr>
<tr><td>campaign_id</td><td>TEXT</td><td>FK · <strong class="lime">PK</strong></td></tr>
<tr><td>revenue</td><td>NUMERIC(12,2)</td><td>receita do dia, backoffice</td></tr>
<tr><td>investment</td><td>NUMERIC(12,2)</td><td>investimento do dia</td></tr>
<tr><td>is_manual</td><td>BOOLEAN</td><td>alguém escreveu à mão</td></tr>
</table>

<p class="note">Duas casas decimais, não quatro: por isso a reconciliação tem tolerância de 0,05.</p>

</div>
<div>

<table class="sm">
<tr><th>View</th><th>1 linha =</th></tr>
<tr><td>v_campaign_daily</td><td>1 campanha × 1 dia · todas as métricas</td></tr>
<tr><td>v_traffic_source_daily</td><td>1 fonte × 1 dia · a fonte vem do click</td></tr>
<tr><td>v_offer_daily</td><td>1 oferta × 1 dia · <strong class="red">sem custo</strong></td></tr>
<tr><td>v_reconciliation_daily</td><td>1 campanha × 1 dia · eventos vs daily control</td></tr>
</table>

<p class="note"><code>v_offer_daily</code> não tem CPA nem ROAS: o tráfego compra-se para uma <em>campanha</em>, não para uma oferta. A ausência é informação.</p>

</div>
</div>

<!--
**Objetivo** · Fechar o inventário: a terceira fact e a camada que as equipas de negócio vão usar.

**Sobre o `is_manual`** — é a coluna mais honesta do modelo. Reconhece que há uma pessoa no circuito e dá à pipeline uma forma de saber quando não deve reclamar. Sem ela, o check de reconciliação dispararia todos os dias e seria desligado ao fim de uma semana — que é como morrem os alertas.

**Sobre as views** — é isto que o Power BI ou o Streamlit devem consumir, nunca as facts diretamente. E quem agregar por cima (semana, mês) tem de voltar a somar as colunas aditivas e recalcular os rácios.

**Sobre `v_reconciliation_daily`** — é uma view *de controlo*, não de análise. Existe para o `quality_check` a consultar, e é também o melhor sítio para ir ver, à mão, porque é que um dia não bate certo.
-->

---

<p class="kicker">Anexo · referência</p>

## Glossário de métricas

<div class="cols">
<div class="card hot">
<p class="tag">Aditivas — guardadas</p>
<table class="sm" style="margin:0">
<tr><td>cost</td><td><code>fact_campaign_costs</code></td></tr>
<tr><td>clicks</td><td><code>fact_campaign_costs</code></td></tr>
<tr><td>impressions</td><td><code>fact_campaign_costs</code></td></tr>
<tr><td>revenue</td><td><code>fact_conversions</code></td></tr>
<tr><td>conversions</td><td><code>count(*)</code></td></tr>
</table>
</div>
<div class="card">
<p class="tag">Derivadas — calculadas nas views</p>
<table class="sm" style="margin:0">
<tr><td>CPC</td><td><code>cost / clicks</code></td><td>CR</td><td><code>conv / clicks</code></td></tr>
<tr><td>CPM</td><td><code>cost / impr × 1000</code></td><td>CPA</td><td><code>cost / conv</code></td></tr>
<tr><td>CTR</td><td><code>clicks / impr</code></td><td>EPC</td><td><code>revenue / clicks</code></td></tr>
<tr><td>ROAS</td><td><code>revenue / cost</code></td><td>profit</td><td><code>revenue − cost</code></td></tr>
<tr><td>ROI</td><td><code>profit / cost</code></td><td></td><td></td></tr>
</table>
</div>
</div>

<div class="chips" style="margin-top:14px">
<span class="chip ok">soma primeiro, divide depois</span>
<span class="chip ok">NULLIF em todas as divisões</span>
<span class="chip ok">nulo não é zero</span>
<span class="chip ok">cada fact ao seu grain (fan-out)</span>
<span class="chip ok">custo no dia da hora, conversão no dia da visita</span>
</div>

<!--
**Objetivo** · A página que se fotografa. Cinco métricas guardadas, nove calculadas, cinco regras.

**As cinco regras, em uma frase cada**
1. *Soma primeiro, divide depois* — um rácio não é aditivo.
2. *NULLIF* — dividir por zero dá indefinido, não erro nem zero.
3. *Nulo não é zero* — o CTR e o CPM só contam as linhas que reportam impressions.
4. *Fan-out* — agregar cada fact ao seu grain antes de juntar.
5. *Datas* — o custo conta no dia da sua hora, a conversão no dia da visita.

**Se alguém perguntar pelo CTR** — repare que precisa de `impressions`, que só alguns providers reportam. É a métrica mais frágil do conjunto e a que mais vale a pena acompanhar de perto.

**Se alguém perguntar pelo `profit`** — aqui é `revenue − cost`. Não subtrai o `payout` da oferta. Numa plataforma onde o payout é custo do negócio, o lucro líquido seria `revenue − cost − payout`. É uma definição, e definições devem ter dono.
-->

---

<p class="kicker">Anexo · referência</p>

## Linhagem e regras por camada

<pre class="diagram sm"><code>API /conversions     ─► raw_conversions.json     ─► <b>validate</b> ─► <b>transform</b> ─► transformed_*.csv ─► <b>fact_conversions</b>
API /campaign-costs  ─► raw_campaign_costs.json  ─► <b>validate</b> ─► <b>transform</b> ─► transformed_*.csv ─► <b>fact_campaign_costs</b>
API /daily-control   ─► raw_daily_control.json   ─► <b>validate</b> ─► <b>transform</b> ─► transformed_*.csv ─► <b>fact_daily_control</b>
API /campaigns ...   ─► (idem)                                                                            ─► <b>dim_*</b>

                              fact_* + dim_*  ─► v_campaign_daily · v_traffic_source_daily · v_offer_daily
                              fact_* + fact_daily_control  ─► v_reconciliation_daily ─► <b>quality_check</b>
</code></pre>

<div class="cols tight">
<div class="card"><p class="tag">Camada 1 · contrato</p><p>Pydantic, na entrada: schema, tipos, enums, constraints de campo, hora certa.</p></div>
<div class="card"><p class="tag">Camada 2 · base de dados</p><p>Constraints: PKs compostas, FKs, <code>CHECK >= 0</code>, <code>NOT NULL</code>.</p></div>
<div class="card hot"><p class="tag">Camada 3 · conjunto</p><p>SQL, depois do load: contagem, freshness, duplicados, FKs, coerência, reconciliação.</p></div>
</div>

<!--
**Objetivo** · O mapa «este número veio daqui», e a ideia de que a qualidade não vive num sítio só.

**Dizer** — a linhagem responde à pergunta que mais vezes se faz num incidente: *de onde veio este valor?* Com quatro setas sabe-se o caminho inteiro, e sabe-se onde ir procurar: o ficheiro em bruto está em `data/staging/<janela>/` e pode ser aberto.

As três camadas são defesas sucessivas, não alternativas. A primeira recusa dados mal formados; a segunda impede estados impossíveis na base; a terceira apanha o que só se vê no conjunto. Cada uma apanha coisas que as outras não apanham — e, repare-se, **a terceira é a única que compara com uma fonte externa**.

**Se houver tempo** — pedir à sala que escolha um número de um relatório deles e tente desenhar esta linha para trás. Quase sempre há um passo em que ninguém sabe o que acontece.
-->
