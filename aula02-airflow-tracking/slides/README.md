# Slides — Aula 02 · Data Pipelines com Apache Airflow

Os slides da formação, em **[Marp](https://marp.app/)** (Markdown → HTML / PDF / PPTX).

```
slides/
├── README.md            este ficheiro
├── .marprc.yml          configuração do Marp (html: true — obrigatório)
├── aula02-airflow.md    a aula: 42 slides + 6 de anexo, com speaker notes
├── extra-airflow.md     conteúdo extra: 20 slides sobre o Airflow e a sua sintaxe
└── assets/              vazio por agora; imagens iriam para aqui
```

Cada deck vive num único ficheiro: o tema CSS está em `<style>` no topo do
ficheiro, e as **speaker notes** são comentários HTML (`<!-- ... -->`)
no fim de cada slide. Não há dependências de imagens — os diagramas são
desenhados em CSS e em texto monoespaçado.

---

## Ver os slides

### Opção 1 · VS Code (recomendado para editar)

1. Instalar a extensão **Marp for VS Code** (`marp-team.marp-vscode`).
2. Abrir `aula02-airflow.md` e carregar no ícone de pré-visualização (`Ctrl/Cmd + K, V`).
3. **Ligar o HTML** — sem isto os diagramas e os cartões desaparecem. Em
   *Settings* (JSON), ou em `.vscode/settings.json`:

   ```json
   { "markdown.marp.html": true }
   ```

A pré-visualização atualiza enquanto se escreve.

### Opção 2 · Servidor local com recarregamento

```bash
npx @marp-team/marp-cli@latest -s .
# abre http://localhost:8080
```

Serve a pasta e recarrega a cada gravação. Lê o `.marprc.yml`, por isso o HTML
já vem ligado.

### Opção 3 · Modo apresentador (com as notas)

```bash
npx @marp-team/marp-cli@latest aula02-airflow.md -o aula02-airflow.html
```

Abrir o HTML no browser e carregar em **`p`**: abre uma segunda janela com as
speaker notes, o cronómetro e o slide seguinte. É assim que se dá a aula.

---

## Exportar

Todas as exportações precisam de uma instalação do **Chrome ou Chromium** (o Marp
usa-o para renderizar). Se não for encontrado automaticamente, indicar o caminho:

```bash
export CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
```

### PDF

```bash
npx @marp-team/marp-cli@latest aula02-airflow.md --pdf -o aula02-airflow.pdf
```

Com as notas impressas por baixo de cada slide (útil para levar em papel):

```bash
npx @marp-team/marp-cli@latest aula02-airflow.md --pdf --pdf-notes -o aula02-airflow-notas.pdf
```

### PowerPoint

```bash
npx @marp-team/marp-cli@latest aula02-airflow.md --pptx -o aula02-airflow.pptx
```

Cada slide vai como **imagem** — fica fiel ao original, mas não se edita no
PowerPoint. As speaker notes são exportadas como notas do PowerPoint.

Para um `.pptx` com texto editável existe `--pptx-editable`, ainda
**experimental**: o layout sofre, sobretudo nos diagramas em CSS. Se o objetivo
for editar no PowerPoint, mais vale refazer o slide lá.

### Imagens

```bash
npx @marp-team/marp-cli@latest aula02-airflow.md --images png   # um PNG por slide
npx @marp-team/marp-cli@latest aula02-airflow.md --image png    # só o primeiro slide (capa)
```

---

## Dependências

| | |
|---|---|
| **Node.js 18+** | para o `npx` / `marp-cli` |
| **Chrome ou Chromium** | só para exportar PDF, PPTX e imagens |
| **Tipos de letra** | Arial (ou Helvetica) e Courier New — presentes em macOS e Windows. Em Linux, instalar `ttf-mscorefonts-installer` ou `fonts-liberation` (as Liberation são clones métricos e o resultado é igual). |

Não é preciso instalar nada globalmente: o `npx @marp-team/marp-cli@latest`
resolve tudo. Quem der a aula muitas vezes pode instalar:
`npm install -g @marp-team/marp-cli`.

---

## A aula, em resumo

5 horas, 42 slides, 8 demos. O detalhe de cada slide está nas speaker notes.
Há ainda **6 páginas de anexo** (43–48) que não se dão em aula — ver abaixo.

| Bloco | Slides | Horário | Tema |
|---|---|---|---|
| Abertura | 1–5 | 0:00–0:30 | o problema, a arquitetura, o que não é esta aula |
| O domínio e o modelo | 6–16 | 0:30–1:30 | grain · facts e dimensions · **data catalog** · chaves compostas · duas datas · métricas · nulo ≠ zero |
| API e data contract | 17–20 | 1:30–1:58 | o producer · Pydantic · schema drift |
| ETL | 21–24 | 1:58–2:20 | extract · validate · transform · load |
| *Intervalo* | | 2:20–2:35 | |
| Apache Airflow | 25–28 | 2:35–3:15 | porquê · o DAG · data interval · catchup e backfill |
| Failures | 29–33 | 3:15–4:00 | retries · 500 · 429 · API lenta · schema drift |
| Idempotência e qualidade | 34–38 | 4:00–4:35 | upsert · validate vs quality check · reconciliação |
| Observabilidade e fecho | 39–42 | 4:35–5:00 | os três níveis · roadmap · takeaways |

**Equilíbrio:** ≈150 min de exposição, ≈80 min de demos ao vivo, ≈40 min de
discussão e exercícios, 15 min de intervalo, 15 min de folga.

### Demos

| | Slide | O que se mostra |
|---|---|---|
| 1 | 17 | a API em `/docs`, o envelope de paginação e duas linhas da mesma hora |
| 2 | 26 | a pipeline inteira a correr em verde |
| 3 | 31 | `http_500` — três tentativas e `upstream_failed` |
| 4 | 31 | `rate_limit` — o retry que recupera à terceira |
| 5 | 32 | `slow` — o `/health` verde e o `extract` em timeout |
| 6 | 33 | `schema_drift` — 200 OK e o Pydantic a falhar em 172 de 172 |
| 7 | 35 | o mesmo dia três vezes: 516 linhas vs 172, e a receita a triplicar |
| 8 | 37 | adulterar o daily control e ver a reconciliação falhar |

Os comandos de cada demo estão nas speaker notes do slide respetivo. Repor
sempre a API no fim: `curl -X POST localhost:8000/admin/mode/healthy`.

### Se a sessão estiver atrasada

Cortar por esta ordem, do menos doloroso para o mais:

1. **28** · catchup vs backfill → 30 segundos em cima do slide 27 *(−9 min)*
2. **11** · uma entrada do catálogo → fica como leitura em `docs/data-catalog.md` *(−6 min)*
3. **23** · transform → mostrar no código em vez de no slide *(−6 min)*
4. **32** · API lenta → é a demo mais lenta, ~1,5 min só de esperas *(−9 min)*
5. **40** · Prometheus/Grafana → apontar para `docs/observability-roadmap.md` *(−6 min)*
6. **41** · o sistema completo → os takeaways fecham sozinhos *(−5 min)*

Nunca cortar: 7, 9, 10, 12, 15, 19, 20, 25, 26, 27, 30, 31, 35, 36, 37, 38, 42.

---

## Editar

**Uma ideia por slide.** Código com 15 linhas no máximo. Se um slide precisar de
um parágrafo, esse parágrafo pertence às speaker notes.

Classes disponíveis no tema (ver o `<style>` no topo do ficheiro):

| Classe | Para quê |
|---|---|
| `.kicker` | a etiqueta lima por cima do título |
| `.big` / `.huge` | frases-chave (38 px / 46 px) |
| `.lime` / `.red` / `.muted` / `.note` | cores e texto secundário |
| `.cols` | colunas lado a lado (`<div class="cols">` com filhos) |
| `.card` + `.hot` / `.bad` | cartões; `hot` = destaque lima, `bad` = falha |
| `.tag` | a etiqueta pequena dentro de um cartão |
| `.chips` + `.chip` / `.chip.ok` / `.chip.bad` | pastilhas |
| `.flow` + `.box` / `.arrow` | diagramas de fluxo horizontais |
| `pre.diagram` | diagramas em texto; `<b>` fica lima |
| `.demo` | a etiqueta **DEMO** no kicker |
| `_class: lead` / `_class: statement` | slide centrado verticalmente |

Paleta: `#0D0D0D` fundo · `#F5F5F5` texto · `#C8F03C` destaque · `#FF5C5C` falhas.
Dois destaques e mais nada — é o que mantém o deck consistente com o resto do curso.

Depois de editar, confirmar sempre com uma exportação para PDF: a
pré-visualização do VS Code é tolerante com conteúdo a mais, o PDF não.

---

## Anexo · o catálogo ao detalhe (slides 43–48)

As últimas seis páginas do deck da aula **não contam para as cinco horas**. São
referência: as quatro dimensões coluna a coluna, `fact_conversions`,
`fact_daily_control` e as views, o glossário de métricas, e a linhagem com as
três camadas de qualidade.

Servem para três momentos: alguém pergunta o que significa uma coluna; alguém
quer saber de onde vem um número; ou como leitura depois da aula. A versão
completa é o [data catalog](../docs/data-catalog.md) do projeto.

Para exportar só a aula, sem o anexo:

```bash
npx @marp-team/marp-cli@latest aula02-airflow.md --pdf -o aula-completa.pdf
qpdf aula-completa.pdf --pages . 1-42 -- aula02-airflow-sem-anexo.pdf
```

---

## Conteúdo extra · Apache Airflow (`extra-airflow.md`)

Um segundo deck, de 20 slides, que **não faz parte das cinco horas**. Responde à
pergunta que a aula deliberadamente não responde — *o que é o Airflow e como se
escreve* — e serve como referência de sintaxe para quem for escrever o primeiro
DAG.

| | |
|---|---|
| O que é | orquestrador vs cron · o que o Airflow é e não é · as cinco palavras |
| Por dentro | scheduler, DAG processor, executor, workers, metadata DB, triggerer |
| Sintaxe | `with DAG` e operators · TaskFlow (`@dag`/`@task`) · dependências · schedule e timetables · data interval e templating · XCom · retries e timeouts · trigger rules · sensors · branching e task groups · connections e variables |
| Operação | a CLI essencial · os cinco erros de quem começa |

Escrito para **Airflow 3.3**, a versão do projeto — a sintaxe mudou face ao
Airflow 2 (imports em `airflow.sdk` e nos providers, `data_interval_*` em vez de
`execution_date`).

```bash
npx @marp-team/marp-cli@latest extra-airflow.md --pdf -o extra-airflow.pdf
```

Três formas de o usar: uma sessão extra de ~1 hora; leitura depois da aula; ou
aberto ao lado do editor como referência.

---

## O projeto

Estes slides acompanham o projeto em [`..`](../README.md) — a pipeline que corre
nas demos. O README do projeto e o [data catalog](../docs/data-catalog.md) são a
referência detalhada (arquitetura, tabela a tabela, os 7 cenários de falha, os
exercícios); os slides são o fio condutor da aula.

Os números que aparecem nos slides vêm do projeto e estão verificados: ≈170
conversões, ≈190 linhas de custo horário e 6 de daily control por dia; 95 testes
a passar; a demo de idempotência dá 516 linhas contra 172, e 13 595 USD de
receita contra 4 532.
