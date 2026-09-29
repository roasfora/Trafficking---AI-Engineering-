<!--
DOCUMENTO SINTÉTICO — material de formação.
A Meridian Digital é uma empresa fictícia. Nenhum dado neste ficheiro é real.
-->

# Postmortem — perda de conversões, setembro de 2026

> Documento interno · publicado em 2026-09-29 · dono: Data & Tracking (Hugo Camelo)
> Leitura obrigatória para Client Services e Performance.

## Resumo

Entre **8 e 19 de setembro de 2026**, aproximadamente **31% das conversões** das
campanhas de Meta Ads da Northline Media e da Vela Gaming não foram registadas.
O impacto estimado no reporting foi de **~148 000 EUR de receita atribuída**.

## Cronologia

- **8 set** — atualização do CMP (plataforma de consentimento) num cliente altera a
  ordem de carregamento de scripts. O pixel passa a disparar antes do consentimento.
- **8–15 set** — os algoritmos de bidding recebem menos sinal e reduzem entrega. O CPA
  reportado sobe. Ninguém liga as duas coisas.
- **16 set** — um gestor de conta nota que o número de conversões em plataforma não bate
  com o back-office do cliente.
- **17 set** — Data & Tracking confirma a causa.
- **18–19 set** — correção implementada e validada com uma conversão real de teste.
- **22 set** — reprocessamento parcial via Conversions API para o período afetado.

## Causa raiz

Não havia monitorização de volume de conversões server-side. A única deteção possível
era manual, por comparação com o back-office do cliente — e essa comparação era mensal.

## O que mudou

1. Alerta automático quando o volume diário de conversões cai mais de 25% face à
   média das 4 semanas anteriores.
2. Teste de ponta a ponta obrigatório no onboarding e após qualquer alteração de CMP.
3. Reconciliação semanal, e não mensal, entre plataforma e back-office.
4. Este documento passou a ser leitura obrigatória na fase 2 do onboarding.

## Lição

O problema não foi o bug. Foi terem passado **onze dias** até alguém perceber. Não
tínhamos forma de saber que estávamos a perder dados — só de descobrir tarde.
