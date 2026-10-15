# Estrutura de dados — campanhas, conversões e custos

Só schema. Sem dados reais, credenciais ou campos pessoais. `?` = opcional/nulo.
Fontes: `pimp-backend` (Django), `ep` / `apg-utils` (Mongo e respostas de API), `external-providers-tasks`.

## 1. Visão geral

```
Voluum ──► Mongo: Conversion, Campaign, CampaignTrafficSourceData
                      │ (agregado diário por campanha)
                      ▼
Postgres: Campaign, TrafficSource, Workspace ──► DailyControl
```

- Conversões e custo ficam no **Mongo**; o Postgres guarda só os agregados diários (`DailyControl`).
- Valores em USD e na moeda da fonte (`*_traffic_source_currency`).
- Modelos Django herdam `BaseModel`: `id`, `uuid`, `created_at`, `updated_at`, `deleted_at?` (soft delete).

## 2. Mongo

### `Conversion` — 1 doc por conversão
Índices: `campaignId`, `clickId`, `visitTimestamp`.

| Grupo | Campos |
|---|---|
| Chaves | `clickId`, `campaignId`, `campaignWorkspaceId`, `trafficSourceId` (str) |
| Datas | `visitTimestamp`, `postbackTimestamp` (datetime) |
| Valores | `revenue`, `revenueInOriginalCurrency`, `allConversionsRevenue`, `cost`, `profit`, `roi` (float) |
| Contagens | `conversions`, `conversionTypeId`, `numberOfOffers` (int) |
| Outros obrigatórios | `costSources: list[str]`, `appendClickIdToOfferUrl`, `campaignUrlConfigured`, `marketplace`, `onlyWhitelistedPostbackIps` (bool) |

Todos os restantes são `str?`/`float?`:
- **Entidades** (`Id`, `Name`, `Notes`, `WorkspaceId`, `WorkspaceName`): `affiliateNetwork*`, `campaign*`, `flow*`, `lander*`, `offer*`, `trafficSource*`, `path*`, `subLander*`
- **Financeiros:** `payout`, `cpa`, `cpc`, `cpm`, `costModel`, `costArgument`, `conversionOriginalCurrency`, `campaignCurrencyCode`, `offerPayoutCurrency`
- **Geo / device:** `countryCode`, `region`, `city`, `isp`, `mobileCarrier`, `language`, `device`, `brand`, `model`, `os`, `browser`, `connectionType`, `userAgent` (+ `*Name`, `*Version`)
- **Tracking:** `ip`, `referrer`, `proxy`, `clientId`, `externalId`, `transactionId`, `conversionType`, `actions`, click/conversion caps
- **Postback:** `postbackUrl`, `incomingPostbackUrl/Ip`, `outgoingPostbackUrl`, `pixelUrl`, `postbackParam1..5`
- **Custom:** `customVariable1..10` e `customVariable1-TS..10-TS`

### `CampaignTrafficSourceData` — custo por hora/dia
`datetime` (idx), `cost`, `campaign_id`, `investment_provider?`, `source_specific_id?` (idx), `clicks?`, `impressions?`, `cpc?`, `cpm?`, `ctr?`

`investment_provider` (16): exoclick, trafficstars, reactiveclicks, clickemistry, dopaclicks, soladsmedia, pushground, trafficgold, traffichunt, propellerads, adextrem, adness, tacoloco, trafficjunky, trafficjunkynewaccount, pushub.

### `Campaign` (relatório Voluum)
`campaignId` (idx), `campaignName`, `campaignCountry?`, `trafficSourceName`, `campaignWorkspaceId`, `campaignUrl`, `clientId`, `created`, `updated`, `visits`, `clicks`, `campaignWorkspaceName?`, `campaignCurrencyCode?`, `conversions?`, `revenue?`, `cost?`, `profit?`, `ctr?`, `cv?`, `epv?`

### Entidades Voluum (só o essencial)
- **TrafficSource:** `id`, `name` (idx), `type`, `deleted`, `currencyCode?`, `createdTime`, `updatedTime`, `clickIdVariable?`, `costVariable?`, `externalIds?`, `customVariables[]`
- **Workspace:** `id` (idx), `name`, `memberships[]` (contém dados pessoais — não partilhar)
- **AffiliateNetwork:** `id`, `name`, `currencyCode`, `postbackUrl`, `conversionTrackingMethod`, `deleted`
- **Offer:** `id`, `name`, `url`, `country{code,name}`, `affiliateNetwork{id}`, `payout`, `capConfiguration?`, `currencyCode`, `deleted`
- **Lander / Flow / DefaultPath / Country / Domain:** existem, não detalhados aqui.

## 3. Postgres — Voluum (pimp-backend)

| Modelo | Campos |
|---|---|
| `Campaign` | `voluum_id?`, `geo` (ISO-2, default `WW`), `name`, `traffic_source` FK, `workspace` FK?, `is_off_voluum`, `is_paused` |
| `TrafficSource` | `voluum_id`, `name`, `deleted`, `currency` (default `USD`), `postback_url?`, `workspace` FK? |
| `Workspace` | `voluum_id`, `name`, `owner` FK → Account |
| `AffiliateNetwork`, `Offer` | `voluum_id` (único), `name` |
| `VoluumHourlyPerformance` | `datetime`, `campaign` FK, `affiliate_network` FK, `offer` FK, `account` FK?, `cost?`, `clicks?`, `visits?`, `impressions?`, `cpv?`, `ctr?`, `cv?`, `epc?`, `epv?`, `revenue?`, `cr?` — UNIQUE `(datetime, campaign, affiliate_network, offer)` |

## 4. Postgres — Daily Control

| Modelo | Campos | UNIQUE |
|---|---|---|
| `traffickin.DailyControl` | `date`, `campaign` FK, `account` FK?, `investment?`, `investment_traffic_source_currency?`, `revenue`, `revenue_traffic_source_currency`, `is_manual`, `note?` | `(date, campaign, account)` |
| `TrafficSourceDailyMetric` | `date`, `traffic_source` FK, `metric_type` (revenue/cost), `value` dec(12,4) — sem `BaseModel` | `(date, traffic_source, metric_type)` |
| `irregular` / `traffickin_social` `DailyControl` | `date`, `geo`, `traffic_source_prefix`, `account` FK?, `revenue`, `revenue_traffic_source_currency`, `investment?`, `investment_traffic_source_currency?`, `investment_with_fee?`, `is_manual` | `(date, geo, account, traffic_source_prefix)` |
| `Provider` | `name` (único), `fee` dec(10,2) | — |
| `DailyControlProvider` | `daily_control` FK, `provider` FK, `fee`, `investment`, `investment_with_fee?` | — |
| `viceroi.DailyControl` | `date`, `investment`, `revenue`, `investment_offer_currency`, `revenue_offer_currency`, `offer` FK, `advertiser` FK, `affiliate` FK, `account` FK? | — |

Valores monetários: dec(12,2) (provider: dec(10,2)).

## 5. Relações

```
Workspace 1─* TrafficSource 1─* Campaign 1─* DailyControl
Campaign 1─* VoluumHourlyPerformance *─1 (AffiliateNetwork, Offer)
DailyControl(irregular|social) 1─* DailyControlProvider *─1 Provider
Mongo: Conversion.campaignId / CampaignTrafficSourceData.campaign_id ──► Campaign.campaignId
Mongo: Campaign.trafficSourceName ──► TrafficSource.name
```

## 6. Dataset sintético mínimo
1. `campaigns`: `campaign_id`, `name`, `geo`, `traffic_source`, `workspace_id`, `is_paused`, `created`
2. `conversions`: `click_id`, `campaign_id`, `visit_timestamp`, `postback_timestamp`, `revenue`, `revenue_original_currency`, `conversion_type_id`, `country_code`, `offer_id`, `traffic_source_id`
3. `campaign_costs`: `datetime` (hora), `campaign_id`, `cost`, `clicks`, `impressions`, `investment_provider`
4. `daily_control`: `date`, `campaign_id`, `revenue`, `investment`, `is_manual`
5. Opcional: `hourly_performance`, `alerts`, `exchange_rate`
