---
marp: true
theme: default
size: 16:9
paginate: true
footer: 'SCOPPHU  ·  AI Engineering Course 2026  ·  M02 · extra'
title: 'Apache Airflow — o que e e como se escreve'
author: 'Scopphu · AI Engineering Course'
description: 'Conteudo extra: orquestracao, anatomia e sintaxe do Airflow 3'
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
.code-sm pre code { font-size: 15px; line-height: 1.4; }

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

<p class="kicker">Scopphu · AI Engineering Course 2026 · Módulo 02 · conteúdo extra</p>

# Apache **Airflow**

<p class="big muted" style="font-size:26px">O que é, como está feito por dentro, e como se escreve</p>

<p class="note">Material de apoio à Aula 02. Não é preciso em sala — serve para quem quer perceber a ferramenta, e como referência de sintaxe quando estiverem a escrever o vosso primeiro DAG.</p>

<p class="note">Airflow <strong class="lime">3.3</strong> · é a versão do projeto, e a sintaxe mudou face ao Airflow 2.</p>

<!--
**Como usar este deck** — são ~45 minutos se for falado de fio a pavio, mas não foi pensado para isso. Três usos: (1) uma sessão extra de uma hora para quem quiser; (2) leitura depois da aula; (3) referência aberta ao lado do editor quando escreverem um DAG.

A Aula 02 ensina *porque* existe orquestração. Este deck ensina *a ferramenta*.
-->

---

<p class="kicker">O que é</p>

## O problema: um script não é uma pipeline

<div class="cols">
<div class="card">
<p class="tag">O que um cron faz</p>
<p style="color:#F5F5F5">Corre um comando a uma hora.</p>
<p style="margin-top:8px">E mais nada.</p>
</div>
<div class="card bad">
<p class="tag">O que um cron não faz</p>
<ul>
<li>não sabe que a tarefa B depende da A</li>
<li>não tenta outra vez se falhar</li>
<li>não avisa ninguém</li>
<li>não guarda histórico</li>
<li>não sabe reprocessar o passado</li>
<li>não impede duas execuções em paralelo</li>
</ul>
</div>
</div>

<p class="big" style="margin-top:16px">Um <span class="lime">orquestrador</span> é um cron que sabe<br>o que correu, o que falhou e o que falta.</p>

<!--
**Dizer** — o cron é uma peça excelente e continua a ser a resposta certa para um script sem dependências que corre uma vez por dia. O problema não é o cron: é pedir-lhe o que ele nunca prometeu.

Quando se precisa de um orquestrador: quando há mais do que uma tarefa, quando a falha tem de ser tratada, quando é preciso reprocessar, e quando alguém tem de poder ver o que aconteceu sem entrar na máquina por SSH.

Alternativas ao Airflow, para quem perguntar: Dagster, Prefect, Mage, Kestra, Argo Workflows, e os serviços geridos (Cloud Composer, MWAA, Astronomer). O Airflow é o mais antigo e o mais instalado; os outros são, em geral, mais agradáveis de escrever e menos universais de contratar.
-->

---

<!-- _class: statement -->

<p class="kicker">O que é</p>

## O que o Airflow é — e o que não é

<div class="cols">
<div class="card hot">
<p class="tag">É</p>
<ul>
<li>um <strong>agendador</strong> de fluxos de trabalho</li>
<li>escrito e definido em <strong>Python</strong></li>
<li>com <strong>histórico</strong>, logs e UI</li>
<li>com <strong>retries</strong> e dependências</li>
<li>capaz de <strong>reprocessar o passado</strong></li>
</ul>
</div>
<div class="card bad">
<p class="tag">Não é</p>
<ul>
<li>uma ferramenta de <strong>processamento</strong> de dados</li>
<li>um motor de <strong>streaming</strong> (é batch)</li>
<li>um <strong>ETL</strong> — o ETL é o teu código</li>
<li>uma base de dados</li>
<li>um sítio para correr uma query de 4 horas num worker</li>
</ul>
</div>
</div>

<p class="big" style="font-size:30px;margin-top:18px">Airflow <span class="lime">orquestra</span>. Quem transforma é o teu código.</p>

<!--
**A regra prática** — o Airflow deve ser o mais "burro" possível: diz o que corre, por que ordem, e o que fazer se falhar. Tudo o resto vive em módulos Python normais, testáveis sem Airflow nenhum.

O teste: se eu não conseguir correr a minha lógica de negócio sem o Airflow instalado, a lógica está no sítio errado.

**O anti-padrão mais comum** — pôr o pandas a processar um milhão de linhas dentro de um `PythonOperator` num worker partilhado. Funciona, até ao dia em que não funciona. O Airflow devia estar a *chamar* o motor (a base de dados, o Spark, o dbt) e a esperar.
-->

---

<p class="kicker">O que é</p>

## Cinco palavras, e já se percebe tudo

<div class="cols tight">
<div class="card hot"><p class="tag">DAG</p><p style="color:#F5F5F5">O fluxo.</p><p style="margin-top:6px">Um grafo de tarefas, sem ciclos. É um ficheiro Python.</p></div>
<div class="card"><p class="tag">Task</p><p style="color:#F5F5F5">Um passo.</p><p style="margin-top:6px">Um nó do grafo.</p></div>
<div class="card"><p class="tag">Operator</p><p style="color:#F5F5F5">O tipo de passo.</p><p style="margin-top:6px">Correr Python, um bash, uma query…</p></div>
</div>
<div class="spacer"></div>
<div class="cols tight">
<div class="card"><p class="tag">DAG run</p><p style="color:#F5F5F5">Uma execução do fluxo.</p><p style="margin-top:6px">Uma por período agendado.</p></div>
<div class="card hot"><p class="tag">Data interval</p><p style="color:#F5F5F5">A fatia de tempo que a run processa.</p><p style="margin-top:6px"><code>[início, fim)</code></p></div>
</div>

<pre class="diagram" style="margin-top:18px"><code>  <b>DAG</b>  tracking_pipeline
   │
   ├── <b>task</b> extract      (<b>operator</b>: PythonOperator)
   ├── <b>task</b> validate     ──►  <b>DAG run</b> de 3 Out  ──►  <b>data interval</b> [3 Out 00:00, 4 Out 00:00)
   └── <b>task</b> load
</code></pre>

<!--
**Dizer** — se alguém levar só estas cinco palavras, consegue ler qualquer DAG e falar com qualquer equipa de dados.

A distinção que mais confunde no início é **DAG vs DAG run**: o DAG é a *definição* (o ficheiro, a receita); a run é uma *execução concreta* dessa definição, para um período concreto. Mil runs partilham o mesmo DAG.

E **data interval** é o que distingue o Airflow de um agendador normal: uma run não é "as 4h de hoje", é "o dia de ontem, processado às 4h de hoje". A run sabe que fatia de dados lhe pertence.
-->

---

<p class="kicker">Por dentro</p>

## Os componentes

<pre class="diagram sm"><code>   ficheiros .py          <b>DAG processor</b>  lê os ficheiros, de poucos em poucos segundos
   na pasta dags/              │
                               ▼
                         <b>metadata DB</b>  (PostgreSQL)  o estado: DAGs, runs, tasks, XComs, retries
                           ▲       ▲
                           │       │
     <b>Scheduler</b> ────────────┘       └──────────── <b>API server / UI</b>   o que vês em :8080
     decide o que corre
     e quando
           │
           ▼
     <b>Executor</b> ──► <b>Workers</b>   executam a task     <b>Triggerer</b>  espera, sem gastar worker
     Local · Celery · Kubernetes
</code></pre>

<div class="cols tight" style="margin-top:14px">
<div class="card"><p class="tag">Nesta formação</p><p><code>airflow standalone</code>: tudo num container, <code>LocalExecutor</code>, sem login.</p></div>
<div class="card"><p class="tag">Em produção</p><p>Componentes separados, executor distribuído, base de metadados gerida com backups, autenticação.</p></div>
<div class="card hot"><p class="tag">A peça central</p><p>A <strong>metadata DB</strong>. É ela que sabe tudo. Perdê-la é perder o histórico — e é por isso que leva backup.</p></div>
</div>

<!--
**Dizer** — percorrer o desenho de cima para baixo. O ponto a fixar: **nada disto fala diretamente com nada**; tudo passa pela base de metadados. O scheduler escreve "esta task está pronta", o worker lê, executa e escreve o resultado, a UI lê. É um quadro branco partilhado.

Consequências práticas disso:
- Se a base de metadados estiver lenta, o Airflow inteiro fica lento, mesmo que as tasks sejam rápidas.
- Se se meter um DataFrame no XCom, está-se a meter um DataFrame nessa base de dados.
- Dois schedulers podem correr ao mesmo tempo (alta disponibilidade) porque o estado está todo lá.

**O triggerer** é o componente que mais gente desconhece: serve para as tasks *deferrable*, que esperam por algo (um ficheiro, uma API) sem ocupar um worker. Um sensor clássico ocupa um slot durante horas; um deferrable liberta-o.
-->

---

<p class="kicker">Sintaxe</p>

## Um DAG é um ficheiro Python

```python
from datetime import datetime, timedelta
from airflow.sdk import DAG
from airflow.providers.standard.operators.python import PythonOperator

with DAG(
    dag_id="exemplo",                      # unico; e o nome na UI
    start_date=datetime(2026, 10, 1),      # a partir de quando faz sentido correr
    schedule="@daily",                     # de quanto em quanto tempo
    catchup=False,                         # nao recuperar o passado ao ativar
) as dag:
    a = PythonOperator(task_id="a", python_callable=funcao_a)
    b = PythonOperator(task_id="b", python_callable=funcao_b)
    a >> b                                 # b so corre depois de a ter sucesso
```

<p class="note">O ficheiro vive na pasta <code>dags/</code>. O DAG processor lê-o de poucos em poucos segundos — <strong class="lime">o ficheiro é executado</strong>, não é lido como texto.</p>

<!--
**Dizer** — é Python normal. Não há YAML, não há DSL. O ficheiro corre de cima a baixo e o que ele *constrói* é o grafo.

Isso tem uma consequência enorme, que é o erro nº 1 de quem começa: **o código ao nível do módulo corre a cada leitura do ficheiro**, de 30 em 30 segundos ou menos, mesmo que nenhuma run esteja a acontecer. Um `pd.read_csv()` ou uma chamada a uma API no topo do ficheiro é uma chamada de 30 em 30 segundos, para sempre. Por isso é que no nosso DAG os imports pesados estão *dentro* das funções.

**`dag_id`** é a identidade: muda-se o nome e o Airflow passa a ver um DAG novo, sem histórico.

**`start_date`** não é "quando começar a correr agora" — é a data a partir da qual existem períodos. Com `catchup=False`, serve sobretudo para definir o primeiro intervalo.
-->

---

<p class="kicker">Sintaxe</p>

## O mesmo DAG, com a TaskFlow API

<div class="code-sm">

```python
from airflow.sdk import dag, task

@dag(start_date=datetime(2026, 10, 1), schedule="@daily", catchup=False)
def exemplo():
    @task
    def extrair() -> dict:
        return {"linhas": 172}            # o retorno vai para o XCom, sozinho

    @task
    def carregar(dados: dict):
        print(dados["linhas"])            # recebe-o como argumento

    carregar(extrair())                   # a dependencia e a chamada da funcao

exemplo()
```

</div>

<div class="cols tight">
<div class="card hot"><p class="tag">Ganha-se</p><p>XCom implícito, menos cerimónia.</p></div>
<div class="card"><p class="tag">Perde-se</p><p>A fronteira entre orquestração e lógica fica menos óbvia.</p></div>
<div class="card"><p class="tag">No projeto</p><p>Estilo clássico: ver o <code>&gt;&gt;</code> ensina melhor.</p></div>
</div>

<!--
**Dizer** — os dois estilos coexistem e podem misturar-se no mesmo DAG. A TaskFlow é mais recente e é o que a documentação oficial usa hoje.

A diferença que interessa: na TaskFlow, **passar o resultado de uma função a outra cria a dependência**. Não é preciso `>>`. Por baixo, o Airflow continua a usar o XCom — e continua a valer a regra de não lá meter datasets.

**Porque é que o projeto da aula usa o estilo clássico** — porque torna visível que o DAG é só uma lista de passos e setas, e que o trabalho vive noutro ficheiro. Na TaskFlow é tentador escrever a lógica toda dentro das funções `@task`, e aí volta-se a ter o negócio preso ao Airflow.
-->

---

<p class="kicker">Sintaxe</p>

## Dependências

```python
a >> b                      # b depois de a
a << b                      # a depois de b  (menos usado, confunde)

a >> [b, c] >> d            # b e c em paralelo, d espera pelos dois

from airflow.sdk import chain, cross_downstream
chain(a, b, c, d)           # a >> b >> c >> d
cross_downstream([a, b], [c, d])   # cada um dos primeiros liga a cada um dos segundos
```

<pre class="diagram" style="margin-top:14px"><code>        ┌─► <b>b</b> ─┐
  <b>a</b> ──┤        ├──► <b>d</b>
        └─► <b>c</b> ─┘
</code></pre>

<p class="note">Uma task só arranca quando <strong>todas</strong> as anteriores tiveram sucesso. Se uma falha, as seguintes ficam <code>upstream_failed</code> — nunca chegam a correr.</p>

<!--
**Dizer** — o `>>` é só açúcar sintático: por baixo chama `set_downstream`. Lê-se como uma seta e é por isso que pegou.

A regra do `upstream_failed` é a mais importante deste slide, e é uma funcionalidade: dados maus não chegam ao destino porque as tasks seguintes simplesmente não correm. Na UI distinguem-se por cor — vermelho (correu e falhou) vs cinzento-escuro (nunca correu).

**Paralelismo** — `[b, c]` correm ao mesmo tempo *se houver slots*. Quantos há depende do executor e de três limites: `parallelism` (global), `max_active_tasks_per_dag`, e os pools. Numa máquina só, com `LocalExecutor`, o paralelismo é o número de processos que ela aguenta.

**Ciclos são proibidos** — é o D de DAG: *directed acyclic graph*. Tentar fechar um ciclo dá erro ao carregar o ficheiro.
-->

---

<p class="kicker">Sintaxe</p>

## Operators: o tipo de cada passo

<table class="sm">
<tr><th>Operator</th><th>Para quê</th><th>Vem de</th></tr>
<tr><td>PythonOperator</td><td>correr uma função Python</td><td><code>providers.standard</code></td></tr>
<tr><td>BashOperator</td><td>correr um comando</td><td><code>providers.standard</code></td></tr>
<tr><td>EmptyOperator</td><td>um nó que não faz nada (marcar início/fim)</td><td><code>providers.standard</code></td></tr>
<tr><td>SQLExecuteQueryOperator</td><td>correr SQL numa connection</td><td><code>providers.common.sql</code></td></tr>
<tr><td>DockerOperator · KubernetesPodOperator</td><td>correr um container</td><td>provider próprio</td></tr>
<tr><td>S3 · BigQuery · Snowflake · Slack · dbt…</td><td>centenas, um por sistema</td><td>provider próprio</td></tr>
</table>

<p class="note">No Airflow 3 quase tudo vive em <strong>providers</strong> — pacotes instalados à parte. Daí os imports longos: <code>from airflow.providers.standard.operators.python import PythonOperator</code>.</p>

<p class="big" style="font-size:26px;margin-top:10px">Na dúvida: <span class="lime">PythonOperator</span> a chamar o teu módulo.</p>

<!--
**Dizer** — há centenas de operators e a tentação é procurar sempre o operator "certo" para cada coisa. Na prática, para quem está a começar, um `PythonOperator` que chama uma função bem escrita resolve 90 % dos casos e mantém o código testável.

Os operators de sistema (BigQuery, S3, Snowflake) valem a pena quando trazem coisas difíceis de reimplementar: gestão de credenciais, paginação, retries específicos do serviço, e integração com o lineage.

**Hooks** — por baixo de quase todos os operators está um *hook*, que é a classe que fala com o sistema. Se precisares de algo que o operator não faz, usas o hook diretamente dentro de uma função Python.

**Nota de versão** — se encontrarem `from airflow.operators.python import PythonOperator` em exemplos antigos, é Airflow 2. No 3 mudou para o caminho dos providers.
-->

---

<p class="kicker">Sintaxe</p>

## Quando corre: schedule

```python
schedule="@daily"                    # presets: @hourly @daily @weekly @monthly
schedule="0 4 * * *"                 # cron: todos os dias as 04:00
schedule=timedelta(hours=6)          # de 6 em 6 horas
schedule=None                        # so a mao
schedule=[meu_asset]                 # quando outro DAG produzir este asset
```

<div class="cols">
<div class="card bad">
<p class="tag">Armadilha do Airflow 3</p>
<p style="color:#F5F5F5">Um <code>schedule="@daily"</code> simples <strong>já não cria data intervals</strong>.</p>
</div>
<div class="card hot">
<p class="tag">O que o projeto usa</p>

```python
from airflow.timetables.interval \
    import CronDataIntervalTimetable

schedule=CronDataIntervalTimetable(
    "@daily", timezone="UTC")
```
</div>
</div>

<!--
**Dizer** — a parte das presets e do cron não tem mistério. A armadilha tem, e é recente: no Airflow 3 a noção de intervalo deixou de ser automática em alguns timetables, e um DAG com `@daily` simples pode receber `data_interval_start = None`.

Como o nosso código depende da janela, o projeto declara o timetable explicitamente. Se encontrarem `data_interval_start` a `None` num DAG do Airflow 3, é quase sempre isto.

**Assets (antes chamados datasets)** — a forma moderna de encadear DAGs: em vez de o DAG B correr "às 5h e esperar que o A já tenha acabado", o A declara que *produz* um asset e o B declara que *consome*. O B corre quando o asset for atualizado. É melhor do que sensores ou do que adivinhar horas.

**Timezone** — o `start_date` e o schedule devem ser conscientes do fuso. A boa prática é manter tudo em UTC e converter só na apresentação.
-->

---

<p class="kicker">Sintaxe</p>

## Que fatia corre: data interval e templating

<pre class="diagram"><code>  3 Out 00:00 ─────────── a fatia desta run ─────────── 4 Out 00:00
  <b>[</b> data_interval_start                       data_interval_end <b>)</b>
                                                             ▲
                                                 a run arranca aqui
</code></pre>

```python
BashOperator(task_id="x", bash_command="echo {{ ds }}")      # 2026-10-03

def minha_funcao(data_interval_start=None, data_interval_end=None, **ctx):
    ...                      # o Airflow injeta o contexto nos argumentos
```

<table class="sm" style="margin-top:10px">
<tr><th>Variável</th><th>Valor</th><th>Variável</th><th>Valor</th></tr>
<tr><td>{{ ds }}</td><td>2026-10-03</td><td>{{ data_interval_start }}</td><td>datetime do início</td></tr>
<tr><td>{{ ds_nodash }}</td><td>20261003</td><td>{{ data_interval_end }}</td><td>datetime do fim</td></tr>
<tr><td>{{ params.x }}</td><td>parâmetro do DAG</td><td>{{ dag_run.conf }}</td><td>o que veio no trigger</td></tr>
</table>

<!--
**Dizer** — há duas formas de uma task saber que período está a processar:
1. **Templating Jinja** nos campos que o suportam (`bash_command`, SQL, caminhos). O Airflow substitui `{{ ds }}` antes de executar.
2. **Contexto injetado**: uma função Python que declare `data_interval_start` (ou `**context`) recebe-o.

A regra de ouro: **nunca chamar `datetime.now()` dentro de uma task**. Se o fizeres, a run de ontem reprocessada hoje processa hoje — e o backfill deixa de funcionar. A data vem sempre de fora.

**`params` vs `conf`** — `params` são os parâmetros declarados no DAG (com default, e editáveis na UI ao disparar à mão); `dag_run.conf` é o JSON que veio no trigger. O nosso projeto usa `conf` para permitir `--conf '{"date": "2026-10-03"}'`.

**Nota de versão** — `execution_date` e `{{ next_ds }}` são Airflow 1/2 e desapareceram. Hoje é `logical_date` e os `data_interval_*`.
-->

---

<p class="kicker">Sintaxe</p>

## XCom: passar informação entre tasks

```python
def a(ti):
    ti.xcom_push(key="caminho", value="/staging/20261003/clicks.json")
    return {"linhas": 172}                      # vai para a chave "return_value"

def b(ti):
    meta = ti.xcom_pull(task_ids="a")           # {"linhas": 172}
    caminho = ti.xcom_pull(task_ids="a", key="caminho")
```

<div class="cols">
<div class="card hot">
<p class="tag">O que lá pôr</p>
<p>Caminhos, contagens, identificadores, pequenos dicionários. <strong>Metadados.</strong></p>
</div>
<div class="card bad">
<p class="tag">O que não lá pôr</p>
<p>DataFrames, listas de milhares de registos, ficheiros. O XCom <strong>é a base de metadados</strong> — enche-se depressa.</p>
</div>
</div>

<p class="note">O padrão correto: os dados vão para um sítio partilhado (ficheiro, S3, uma tabela) e <strong class="lime">pelo XCom viaja só o caminho</strong>.</p>

<!--
**Dizer** — XCom quer dizer *cross-communication*. É o único canal oficial entre tasks, e é deliberadamente pequeno.

Porquê: cada task pode correr noutro processo, noutra máquina, noutro dia (num retry). Não há memória partilhada. O que há é uma tabela na base de metadados onde uma task escreve e outra lê.

Há *XCom backends* personalizados (guardar em S3 e deixar só a referência na base) para quem quer passar objetos maiores sem inchar a base. É uma boa solução — mas a solução mais simples continua a ser escrever um ficheiro e passar o caminho, que é o que o nosso projeto faz.

**Na TaskFlow API** isto é automático: o `return` de um `@task` vai para o XCom e o argumento da função seguinte lê-o. Conveniente — e exatamente por isso é fácil lá meter um DataFrame sem reparar.
-->

---

<p class="kicker">Sintaxe</p>

## Quando falha: retries e timeouts

```python
default_args = {
    "retries": 2,                               # 1 tentativa + 2 = 3 no total
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,          # 5, 10, 20 min...
    "max_retry_delay": timedelta(hours=1),
    "execution_timeout": timedelta(minutes=30), # mata a tentativa
}

with DAG(..., default_args=default_args) as dag:
    t = PythonOperator(task_id="t", python_callable=f, retries=0)   # anula o default
```

<div class="cols tight">
<div class="card hot"><p class="tag">retries</p><p>Para erros <strong>transitórios</strong>: 500, timeout, 429, deadlock.</p></div>
<div class="card bad"><p class="tag">retries=0</p><p>Para erros <strong>determinísticos</strong>: schema errado, valor impossível, bug.</p></div>
<div class="card"><p class="tag">execution_timeout</p><p>Sem ele, uma chamada pendurada fica a correr para sempre e ocupa um slot.</p></div>
</div>

<!--
**Dizer** — o `default_args` aplica-se a todas as tasks do DAG, e cada task pode sobrepor-se. É assim que o nosso projeto põe `retries=0` só no `validate` e no `quality_check`.

**O cálculo que ninguém faz** — com `retries=3`, `retry_delay=5min` e backoff exponencial, uma task demora 5+10+20 = 35 minutos a desistir, mais o tempo das tentativas. Se o DAG tem um SLA de uma hora, já o gastou todo. Vale a pena fazer a conta antes de configurar.

**Duas camadas de timeout** — o timeout da *biblioteca* (o cliente HTTP, o driver da base de dados) e o `execution_timeout` da task. O primeiro deve ser bastante menor, para que a falha venha com uma mensagem decente em vez de um processo morto.

**`sla`** — existe, e envia uma notificação se a task demorar mais do que o esperado. É uma funcionalidade com história de ser confusa; em muitas equipas prefere-se medir a duração em métricas e alertar fora do Airflow.
-->

---

<p class="kicker">Sintaxe</p>

## Trigger rules: quando é que uma task arranca

<table class="sm">
<tr><th>Regra</th><th>A task corre quando…</th><th>Para quê</th></tr>
<tr><td>all_success</td><td>todas as anteriores tiveram sucesso</td><td><strong class="lime">o default</strong></td></tr>
<tr><td>all_done</td><td>todas acabaram, com sucesso ou não</td><td>limpeza, notificação final</td></tr>
<tr><td>one_failed</td><td>pelo menos uma falhou</td><td>alerta</td></tr>
<tr><td>one_success</td><td>pelo menos uma teve sucesso</td><td>caminhos alternativos</td></tr>
<tr><td>none_failed_min_one_success</td><td>nenhuma falhou e pelo menos uma correu</td><td>depois de um <em>branch</em></td></tr>
<tr><td>always</td><td>sempre</td><td>raro, e perigoso</td></tr>
</table>

```python
notificar = PythonOperator(task_id="notificar", python_callable=avisar,
                           trigger_rule="all_done")
```

<!--
**Dizer** — 95 % das tasks ficam no default. As trigger rules existem para dois casos concretos: a tarefa de limpeza que tem de correr mesmo quando algo falhou (`all_done`), e a tarefa de alerta que só corre quando algo falhou (`one_failed`).

**O erro típico** — pôr `all_done` numa task de carga "para ela correr na mesma". Isso desliga a proteção: dados maus passam a chegar ao destino. Se a task a seguir ao `validate` tiver `all_done`, o `validate` deixou de servir para alguma coisa.

**Depois de um branch** — é o caso em que o default não serve: se um `BranchPythonOperator` escolheu um de dois caminhos, o outro fica `skipped`, e uma task que junte os dois nunca correria com `all_success`. Daí o `none_failed_min_one_success`.

Para notificações, hoje prefere-se `on_failure_callback` ao nível do DAG ou da task — é mais direto do que uma task com `one_failed`.
-->

---

<p class="kicker">Sintaxe</p>

## Esperar por alguma coisa: sensors

```python
from airflow.providers.standard.sensors.filesystem import FileSensor

espera = FileSensor(
    task_id="espera_ficheiro",
    filepath="/data/entrada/{{ ds }}.csv",
    poke_interval=60,            # verifica de minuto a minuto
    timeout=60 * 60 * 6,         # desiste ao fim de 6 horas
    mode="reschedule",           # LIBERTA o slot entre verificacoes
)
```

<div class="cols">
<div class="card bad">
<p class="tag">mode="poke" (default)</p>
<p>Ocupa um worker durante toda a espera. Seis sensores a esperar seis horas bloqueiam seis slots.</p>
</div>
<div class="card hot">
<p class="tag">mode="reschedule" ou deferrable</p>
<p>Liberta o slot entre verificações. Os <em>deferrable</em> passam a espera para o <strong>triggerer</strong> e são o caminho moderno.</p>
</div>
</div>

<!--
**Dizer** — um sensor é uma task que não faz nada a não ser perguntar "já?". Há sensores para ficheiros, para tabelas, para outros DAGs, para APIs.

O problema clássico do Airflow em equipas grandes é exatamente este: dezenas de sensores em `poke` a ocupar todos os slots, e as tasks reais à espera de vez. Daí as duas alternativas do cartão verde.

**A alternativa melhor, quando é possível** — não esperar. Se o que se espera é outro DAG, usa-se *assets* (o DAG B corre quando o A produz o dado) em vez de um sensor a adivinhar. Esperar é sempre a segunda melhor opção.

**`timeout` é obrigatório na prática** — um sensor sem timeout espera para sempre, e ninguém repara durante semanas.
-->

---

<p class="kicker">Sintaxe</p>

## Organizar: branching e task groups

<div class="cols">
<div>

```python
from airflow.sdk import task

@task.branch
def escolher(**ctx) -> str:
    if e_fim_do_mes(ctx["ds"]):
        return "fecho_mensal"
    return "fecho_diario"
```

<p class="note">Devolve o <code>task_id</code> do caminho a seguir. Os outros ficam <code>skipped</code>.</p>

</div>
<div>

```python
from airflow.sdk import TaskGroup

with TaskGroup("carregar") as carregar:
    PythonOperator(task_id="dimensoes", ...)
    PythonOperator(task_id="factos", ...)

extrair >> carregar >> verificar
```

<p class="note">Agrupa tasks numa caixa que se abre e fecha na UI. É só organização visual — e vale muito num DAG com 40 tasks.</p>

</div>
</div>

<!--
**Dizer** — duas ferramentas de arrumação, nenhuma essencial para começar.

**Branching** — útil quando o caminho depende dos dados ou da data. O cuidado: as tasks do caminho não escolhido ficam `skipped`, e `skipped` propaga-se. Se houver uma task que junte os dois caminhos, precisa de `trigger_rule="none_failed_min_one_success"`.

**TaskGroup** — substituiu os antigos SubDAGs, que eram uma fonte de problemas e foram removidos. Um TaskGroup não é uma unidade de execução: é uma caixa na UI. As tasks continuam a ser tasks normais, com o id prefixado (`carregar.dimensoes`).

**Geração dinâmica** — há ainda o `expand()` (*dynamic task mapping*), que cria N tasks a partir de uma lista calculada em tempo de execução: `processar.expand(ficheiro=listar_ficheiros())`. É poderoso e é a resposta certa para "quero uma task por cliente".
-->

---

<p class="kicker">Sintaxe</p>

## Onde vivem os segredos: connections e variables

```python
from airflow.sdk import Variable
from airflow.providers.postgres.hooks.postgres import PostgresHook

limite = Variable.get("limite_rejeicao", default_var=0.01)
hook   = PostgresHook(postgres_conn_id="analytics")   # host, user, pass vem da connection
df     = hook.get_pandas_df("SELECT * FROM fact_conversions LIMIT 10")
```

<div class="cols tight">
<div class="card"><p class="tag">Connection</p><p>Como falar com um sistema: host, porta, utilizador, password, extras. Identificada por um <code>conn_id</code>.</p></div>
<div class="card"><p class="tag">Variable</p><p>Um valor de configuração com nome. Útil — mas ler uma no topo do ficheiro é uma query à base a cada leitura.</p></div>
<div class="card hot"><p class="tag">Nunca</p><p>Credenciais no código ou no git. Em produção: um <em>secrets backend</em> (Vault, AWS Secrets Manager).</p></div>
</div>

<p class="note">O nosso projeto não usa connections: lê o <code>DATABASE_URL</code> do ambiente. É mais simples de ensinar — e é também uma simplificação.</p>

<!--
**Dizer** — connections e variables vivem na base de metadados e editam-se na UI ou pela CLI. A vantagem face a variáveis de ambiente: mudam-se sem reiniciar nada, e ficam auditadas.

**A armadilha das Variables** — `Variable.get()` ao nível do módulo é uma query à base de metadados **a cada leitura do ficheiro DAG**, ou seja, de 30 em 30 segundos. Dentro de uma função, é uma query por execução. Há quem use um único Variable com um JSON para reduzir o número de leituras.

**Secrets backend** — em produção, as connections não ficam na base do Airflow: ficam num gestor de segredos, e o Airflow vai lá buscá-las. Configura-se uma vez e passa a ser transparente.

**Para o nosso caso** — o passo seguinte natural seria trocar o `DATABASE_URL` por uma connection `analytics`, e usar um `PostgresHook` em vez de abrir a ligação à mão. É um bom exercício.
-->

---

<p class="kicker">Operação</p>

## A CLI que vale a pena saber

```bash
airflow dags list                          # que DAGs existem
airflow dags list-import-errors            # porque e que o meu DAG nao aparece
airflow dags unpause tracking_pipeline     # ativar
airflow dags trigger tracking_pipeline --conf '{"date": "2026-10-03"}'

airflow tasks test tracking_pipeline extract 2026-10-03    # corre UMA task, sem gravar estado
airflow dags test tracking_pipeline 2026-10-03             # corre o DAG inteiro, local

airflow backfill create --dag-id tracking_pipeline \
    --from-date 2026-10-01 --to-date 2026-10-05

airflow db check                           # a base de metadados responde?
```

<p class="note"><code>tasks test</code> é a melhor ferramenta de depuração do Airflow: corre a task no terminal, com o contexto todo, sem tocar no histórico.</p>

<!--
**Dizer** — a UI é confortável, mas quase tudo se faz mais depressa pela CLI, e a CLI é o que se usa em scripts e em CI.

**`list-import-errors`** é o primeiro comando a correr quando um DAG "desapareceu". Nove em cada dez vezes é um erro de sintaxe ou um import que falha — e a UI não o mostra em lado nenhum óbvio.

**`tasks test`** merece destaque: corre a função com o contexto real (data interval incluído), imprime o log no terminal e **não escreve nada na base de metadados**. É como se corre um breakpoint num DAG.

**`dags test`** faz o mesmo para o DAG inteiro. Substituiu o antigo `airflow dags backfill --dry-run` como forma de experimentar.

Num container: `docker compose exec airflow airflow dags list`. O `airflow` repetido é normal — o primeiro é o serviço, o segundo é o comando.
-->

---

<p class="kicker">Operação</p>

## Os cinco erros de quem começa

<div class="cols tight">
<div class="card bad"><p class="tag">1 · código no topo</p><p>Uma chamada à API ou um <code>read_csv</code> ao nível do módulo corre <strong>a cada leitura do ficheiro</strong>, não a cada run.</p></div>
<div class="card bad"><p class="tag">2 · <code>datetime.now()</code></p><p>Dentro de uma task, destrói o backfill: reprocessar ontem passa a processar hoje.</p></div>
<div class="card bad"><p class="tag">3 · dados no XCom</p><p>Um DataFrame no XCom é um DataFrame na base de metadados.</p></div>
</div>
<div class="spacer"></div>
<div class="cols tight">
<div class="card bad"><p class="tag">4 · <code>catchup=True</code> distraído</p><p>Um <code>start_date</code> de 2020 e o scheduler cria centenas de runs ao ativar o DAG.</p></div>
<div class="card bad"><p class="tag">5 · a task que faz tudo</p><p>Uma só task com 400 linhas: não há retry parcial, não há paralelismo, e o log é ilegível.</p></div>
<div class="card hot"><p class="tag">E o bónus</p><p>Lógica de negócio dentro do DAG. Se não se testa sem Airflow, está no sítio errado.</p></div>
</div>

<!--
**Dizer** — esta é a página a guardar. Todos os cinco são erros que se cometem uma vez e nunca mais.

Detalhe do **1**: o ficheiro DAG não é lido, é *executado*. Tudo o que estiver fora de uma função corre a cada parse. Além do custo, é imprevisível: a função pode falhar e o DAG desaparece da UI sem explicação óbvia.

Detalhe do **5**: a granularidade certa de uma task é "uma coisa que faz sentido repetir sozinha". Se falhar o load, quero repetir o load — não a extração inteira. Mas o exagero oposto também existe: cem tasks minúsculas tornam a UI ilegível e o overhead do scheduler passa a dominar.

**A pergunta de revisão para qualquer DAG** — "se esta run falhar a meio e eu carregar em *Clear*, o que acontece?" Se a resposta não for "corre outra vez e dá o mesmo resultado", falta idempotência.
-->

---

<!-- _class: statement -->

<p class="kicker">Fecho</p>

## Em três frases

<p class="huge">Um DAG é um ficheiro <span class="lime">Python</span> que<br>descreve passos e dependências.</p>

<p class="big">Uma run processa uma <span class="lime">fatia de tempo</span>,<br>não «agora».</p>

<p class="big">O Airflow <span class="lime">decide e regista</span>.<br>Quem faz o trabalho é o teu código.</p>

<p class="note" style="margin-top:20px">A seguir: abrir <code>dags/tracking_pipeline.py</code> e reconhecer cada uma destas peças. São 137 linhas e estão lá todas.</p>

<!--
**Fechar** — pedir à sala que abra o DAG do projeto e aponte, no ficheiro, cada conceito deste deck: o `with DAG`, os operators, o `>>`, o timetable, os `default_args`, o `retries=0` em duas tasks, e o `xcom_pull` entre elas.

Se conseguirem fazer isso, sabem Airflow que chegue para construir a primeira pipeline. O resto — Celery, Kubernetes, assets, dynamic mapping — aprende-se quando o problema aparecer, e não antes.

**Documentação** — `airflow.apache.org/docs`. A secção *Core Concepts* é boa e curta; os *Howto Guides* resolvem a maioria das dúvidas práticas.
-->
