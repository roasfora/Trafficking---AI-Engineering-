import pandas as pd

from pipeline import transform
from tests.test_schemas import COST, CONVERSION, OFFER


def conv(**overrides):
    return {**CONVERSION, **overrides}


def test_normalises_timestamps_to_utc_and_derives_visit_date():
    df = transform.transform("conversions", [conv(visit_timestamp="2026-10-01T23:30:00+01:00",
                                                  postback_timestamp="2026-10-01T23:40:00+01:00")])
    ts = df.loc[0, "visit_timestamp"]
    assert str(ts.tz) == "UTC" and ts.hour == 22  # 23:30+01:00 == 22:30Z
    assert df.loc[0, "visit_date"].isoformat() == "2026-10-01"


def test_visit_date_follows_utc_not_the_original_offset():
    df = transform.transform("conversions", [conv(visit_timestamp="2026-10-02T00:30:00+01:00",
                                                  postback_timestamp="2026-10-02T00:40:00+01:00")])
    assert df.loc[0, "visit_date"].isoformat() == "2026-10-01"  # 23:30Z do dia anterior


def test_normalises_strings():
    row = transform.transform("conversions", [conv(country_code=" pt ", click_id=" " + CONVERSION["click_id"] + " ")]).iloc[0]
    assert row["country_code"] == "PT"
    assert row["click_id"] == CONVERSION["click_id"]


def test_provider_is_lowercased_and_optional_ints_stay_null():
    df = transform.transform("campaign_costs", [{**COST, "investment_provider": " ExoClick ", "clicks": None, "impressions": None}])
    assert df.loc[0, "investment_provider"] == "exoclick"
    assert df["clicks"].dtype == "Int64" and pd.isna(df.loc[0, "clicks"]) and pd.isna(df.loc[0, "impressions"])
    assert df.loc[0, "cost_date"].isoformat() == "2026-10-01"


def test_enforces_types():
    df = transform.transform("conversions", [conv(revenue=1.234567)])
    assert df.loc[0, "revenue"] == 1.2346 and df["revenue"].dtype == "float64"
    assert df["conversion_type_id"].dtype == "Int64"
    assert transform.transform("offers", [OFFER])["deleted"].dtype == "bool"


def test_removes_duplicates_by_the_composite_key():
    other_type = conv(conversion_type_id=2)  # mesmo click, outro tipo: NAO e duplicado
    df = transform.transform("conversions", [conv(), conv(), other_type])
    assert len(df) == 2
    assert df["conversion_type_id"].tolist() == [1, 2]


def test_same_click_different_postback_time_is_a_different_row():
    later = conv(postback_timestamp="2026-10-01T11:00:00+00:00")
    assert len(transform.transform("conversions", [conv(), later])) == 2


def test_column_order_matches_the_table():
    for name, spec in transform.SPECS.items():
        assert list(transform.transform(name, []).columns) == spec.columns


def test_empty_input_does_not_crash():
    for name in transform.SPECS:
        assert len(transform.transform(name, [])) == 0


def test_daily_control_dates_and_rounding():
    df = transform.transform("daily_control", [{"date": "2026-10-01", "campaign_id": "x", "revenue": 10.123, "investment": 5.0, "is_manual": False}])
    assert df.loc[0, "date"].isoformat() == "2026-10-01" and df.loc[0, "revenue"] == 10.12


def test_optional_country_stays_null():
    assert pd.isna(transform.transform("offers", [OFFER]).loc[0, "country_code"])


def test_csv_roundtrip_keeps_types(tmp_path):
    rows = [conv(country_code="NA"), conv(conversion_type_id=2)]
    df = transform.transform("conversions", rows)
    path = tmp_path / "c.csv"
    df.to_csv(path, index=False)
    back = transform.read_transformed(path, "conversions")
    assert back["country_code"].tolist() == ["NA", "PT"]  # "NA" nao pode virar NaN
    assert str(back["postback_timestamp"].dt.tz) == "UTC"
    assert back.loc[0, "visit_date"].isoformat() == "2026-10-01"
    assert back["conversion_type_id"].dtype == "Int64" and back["revenue"].dtype == "float64"
    assert back["click_id"].dtype in ("object", "str")


def test_csv_roundtrip_keeps_nulls_and_all_digit_ids(tmp_path):
    cost = {**COST, "clicks": None, "impressions": None}
    df = transform.transform("campaign_costs", [cost])
    path = tmp_path / "k.csv"
    df.to_csv(path, index=False)
    back = transform.read_transformed(path, "campaign_costs")
    assert pd.isna(back.loc[0, "clicks"]) and back["clicks"].dtype == "Int64"
    # um click_id so com digitos nao pode virar numero
    df = transform.transform("conversions", [conv(click_id="1" * 32)])
    df.to_csv(path, index=False)
    assert transform.read_transformed(path, "conversions").loc[0, "click_id"] == "1" * 32
