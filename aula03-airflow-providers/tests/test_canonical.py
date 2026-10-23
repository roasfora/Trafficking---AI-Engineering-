from decimal import Decimal

import pytest
from pydantic import ValidationError

from contracts.canonical import CampaignDailyStat

OK = dict(date="2026-10-20", provider="erobella", campaign_id="0b6116c0-9ed5-5398-8df0-72911f86933f",
          source_specific_id="label-a", currency="EUR", impressions=100, clicks=5, cost="1.2345")


def fields(**overrides):
    with pytest.raises(ValidationError) as exc:
        CampaignDailyStat.model_validate({**OK, **overrides})
    return {e["loc"][0] for e in exc.value.errors()}


def test_valid_and_optional_source_specific_id():
    assert CampaignDailyStat.model_validate(OK).cost == Decimal("1.2345")
    no_label = {k: v for k, v in OK.items() if k != "source_specific_id"}
    assert CampaignDailyStat.model_validate(no_label).source_specific_id is None


def test_only_base_metrics_no_ratios():
    assert fields(cpc="0.4") == {"cpc"}  # extra="forbid": cpc/cpm/ctr nao fazem parte do modelo


def test_constraints():
    assert fields(cost="-0.01") == {"cost"}
    assert fields(clicks=-1) == {"clicks"}
    assert fields(impressions="100") == {"impressions"}  # estrito
    assert fields(cost="1.23456") == {"cost"}  # mais de 4 casas
    assert fields(currency="eur") == {"currency"} and fields(currency="EURO") == {"currency"}
    assert fields(provider="google") == {"provider"}
    assert fields(campaign_id="abc") == {"campaign_id"}
    assert fields(source_specific_id="") == {"source_specific_id"}


def test_currency_is_required():
    with pytest.raises(ValidationError):
        CampaignDailyStat.model_validate({k: v for k, v in OK.items() if k != "currency"})
