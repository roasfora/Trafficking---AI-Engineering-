"""O contrato: cada teste e um exemplo de erro de validacao."""

import pytest
from pydantic import ValidationError

from api.schemas import Campaign, CampaignCost, Conversion, DailyControl, Offer, Page

UUID_A = "10d9a805-00a4-5b34-9866-1db19f4b2e63"
UUID_B = "20ef27c1-0000-5b34-9866-1db19f4b2e63"
UUID_C = "30a8dd00-1111-5b34-9866-1db19f4b2e63"

CONVERSION = {
    "click_id": "0a4b80dcb69980f7d65d38bbeb3af23e",
    "campaign_id": UUID_A,
    "traffic_source_id": UUID_B,
    "offer_id": UUID_C,
    "visit_timestamp": "2026-10-01T10:00:00+00:00",
    "postback_timestamp": "2026-10-01T10:05:00+00:00",
    "revenue": 55.0,
    "revenue_original_currency": 55.0,
    "conversion_type_id": 1,
    "country_code": "PT",
}
COST = {
    "datetime": "2026-10-01T10:00:00+00:00",
    "campaign_id": UUID_A,
    "investment_provider": "exoclick",
    "cost": 12.5,
    "clicks": 30,
    "impressions": 2500,
}
CAMPAIGN = {
    "campaign_id": UUID_A, "name": "c", "geo": "PT", "traffic_source_id": UUID_B,
    "workspace_id": UUID_C, "is_paused": False, "created": "2026-06-01T00:00:00+00:00",
}
OFFER = {
    "offer_id": UUID_A, "name": "o", "affiliate_network_id": UUID_B,
    "affiliate_network_name": "n", "payout": 10.0, "currency_code": "USD", "deleted": False,
}
DAILY = {"date": "2026-10-01", "campaign_id": UUID_A, "revenue": 10.0, "investment": 5.0, "is_manual": False}


def error_fields(model, payload):
    with pytest.raises(ValidationError) as exc:
        model.model_validate(payload)
    return {e["loc"][0] for e in exc.value.errors()}


def test_valid_payloads():
    for model, payload in [(Conversion, CONVERSION), (CampaignCost, COST), (Campaign, CAMPAIGN),
                           (Offer, OFFER), (DailyControl, DAILY)]:
        model.model_validate(payload)


def test_optional_fields():
    assert Offer.model_validate(OFFER).country_code is None  # ausente
    assert Offer.model_validate({**OFFER, "country_code": None}).country_code is None
    cost = CampaignCost.model_validate({k: v for k, v in COST.items() if k not in ("clicks", "impressions")})
    assert cost.clicks is None and cost.impressions is None  # NULL != 0


@pytest.mark.parametrize("field", ["click_id", "postback_timestamp", "revenue", "country_code", "campaign_id"])
def test_required_fields(field):
    assert error_fields(Conversion, {k: v for k, v in CONVERSION.items() if k != field}) == {field}


def test_negative_money_is_rejected():
    assert error_fields(Conversion, {**CONVERSION, "revenue": -5}) == {"revenue"}
    assert error_fields(Conversion, {**CONVERSION, "revenue_original_currency": -1}) == {"revenue_original_currency"}
    assert error_fields(CampaignCost, {**COST, "cost": -0.01}) == {"cost"}
    assert error_fields(DailyControl, {**DAILY, "investment": -1}) == {"investment"}


def test_zero_money_is_allowed():
    assert Conversion.model_validate({**CONVERSION, "revenue": 0}).revenue == 0


@pytest.mark.parametrize("country", ["PRT", "P", "pt", "P1", ""])
def test_country_must_be_two_uppercase_letters(country):
    assert error_fields(Conversion, {**CONVERSION, "country_code": country}) == {"country_code"}


def test_geo_accepts_ww_but_not_garbage():
    Campaign.model_validate({**CAMPAIGN, "geo": "WW"})
    assert error_fields(Campaign, {**CAMPAIGN, "geo": "WORLD"}) == {"geo"}


def test_timestamp_must_be_a_datetime_with_timezone():
    assert error_fields(Conversion, {**CONVERSION, "visit_timestamp": "ontem"}) == {"visit_timestamp"}
    assert error_fields(Conversion, {**CONVERSION, "postback_timestamp": "2026-10-01T10:00:00"}) == {"postback_timestamp"}


def test_ids_respect_their_type():
    assert error_fields(Conversion, {**CONVERSION, "campaign_id": 123}) == {"campaign_id"}  # int != uuid str
    assert error_fields(Conversion, {**CONVERSION, "campaign_id": "123"}) == {"campaign_id"}
    assert error_fields(Conversion, {**CONVERSION, "campaign_id": UUID_A.upper()}) == {"campaign_id"}
    assert error_fields(Conversion, {**CONVERSION, "click_id": "abc"}) == {"click_id"}
    assert error_fields(Conversion, {**CONVERSION, "conversion_type_id": "1"}) == {"conversion_type_id"}
    assert error_fields(Conversion, {**CONVERSION, "conversion_type_id": 0}) == {"conversion_type_id"}


def test_enums_are_closed_sets():
    assert error_fields(CampaignCost, {**COST, "investment_provider": "facebook"}) == {"investment_provider"}


def test_counts_cannot_be_negative():
    assert error_fields(CampaignCost, {**COST, "clicks": -1}) == {"clicks"}
    assert error_fields(CampaignCost, {**COST, "impressions": 1.5}) == {"impressions"}


def test_custom_rule_cost_datetime_must_be_top_of_the_hour():
    assert error_fields(CampaignCost, {**COST, "datetime": "2026-10-01T10:30:00+00:00"}) == {"datetime"}


def test_schema_drift_renamed_field_breaks_the_contract():
    drifted = {k: v for k, v in CONVERSION.items() if k != "revenue"} | {"revenue_amount": 55.0}
    # um campo desapareceu (revenue) E apareceu um desconhecido (extra=forbid)
    assert error_fields(Conversion, drifted) == {"revenue", "revenue_amount"}


def test_page_envelope():
    page = Page[Conversion](data=[CONVERSION], count=1, total=437, limit=1, offset=0)
    assert page.total == 437
    with pytest.raises(ValidationError):
        Page[Conversion](data=[], count=-1, total=0, limit=1, offset=0)
