import json

import pytest

from pipeline import validate
from tests.test_schemas import CAMPAIGN, CONVERSION, COST, DAILY, OFFER, UUID_A, UUID_B


def meta_with(tmp_path, **overrides):
    data = {
        "workspaces": [{"workspace_id": UUID_A, "name": "w"}],
        "traffic_sources": [{"traffic_source_id": UUID_B, "name": "s", "currency_code": "USD", "deleted": False}],
        "campaigns": [CAMPAIGN],
        "offers": [OFFER],
        "conversions": [CONVERSION],
        "campaign_costs": [COST],
        "daily_control": [DAILY],
        **overrides,
    }
    files = {}
    for name, rows in data.items():
        p = tmp_path / f"raw_{name}.json"
        p.write_text(json.dumps(rows))
        files[name] = str(p)
    return {"run_dir": str(tmp_path), "files": files}


def test_valid_data_passes(tmp_path):
    out = validate.run_validate(meta_with(tmp_path))
    assert out["validated"]["conversions"] == 1 and len(out["validated"]) == 7


def test_schema_drift_fails_validate(tmp_path):
    drifted = {k: v for k, v in CONVERSION.items() if k != "revenue"} | {"revenue_amount": 35.0}
    with pytest.raises(validate.ContractViolation, match="conversions"):
        validate.run_validate(meta_with(tmp_path, conversions=[drifted]))


def test_invalid_values_fail_validate(tmp_path):
    with pytest.raises(validate.ContractViolation, match="campaign_costs"):
        validate.run_validate(meta_with(tmp_path, campaign_costs=[{**COST, "cost": -1}]))
    with pytest.raises(validate.ContractViolation):
        validate.run_validate(meta_with(tmp_path, conversions=[{**CONVERSION, "revenue": -5}]))
    with pytest.raises(validate.ContractViolation):
        validate.run_validate(meta_with(tmp_path, conversions=[{**CONVERSION, "country_code": "PRT"}]))


def test_reports_all_problems_not_just_the_first():
    rows = [{**CONVERSION, "revenue": -1}, {**CONVERSION, "country_code": "xx"}, CONVERSION]
    problems = validate.validate_records("conversions", rows)
    assert problems.pop("__invalid_records__") == 2
    assert {field for field, _ in problems} == {"revenue", "country_code"}
