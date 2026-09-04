"""Unit tests for ai_chat_tokens catalog wiring (Sprint B0)."""

from am_subscription.schemas.subscription import PlanLimitsDTO
from am_subscription.services.entitlement_service import ACTION_TO_METRIC


def test_ai_chat_action_maps_to_token_metric():
    assert ACTION_TO_METRIC["ai.chat"] == "ai_chat_tokens"


def test_plan_limits_include_ai_chat_tokens_default():
    limits = PlanLimitsDTO()
    assert limits.ai_chat_tokens == 0


def test_plan_limits_accept_ai_chat_tokens_from_catalog():
    limits = PlanLimitsDTO(
        document_parses=5,
        portfolios=1,
        ai_portfolio_summaries=1,
        api_calls=1000,
        ai_chat_tokens=100_000,
    )
    assert limits.ai_chat_tokens == 100_000
    dumped = limits.model_dump()
    assert dumped["ai_chat_tokens"] == 100_000


def test_lago_plans_json_has_ai_chat_tokens_metric_and_limits():
    import json
    from pathlib import Path

    # Prefer service-mounted catalog path shape; fall back to automation file.
    candidates = [
        Path(__file__).resolve().parents[2] / "automation" / "helm" / "lago-plans.json",
        Path(__file__).resolve().parents[3] / "automation" / "helm" / "lago-plans.json",
    ]
    path = next((p for p in candidates if p.is_file()), None)
    assert path is not None, "lago-plans.json not found"
    data = json.loads(path.read_text(encoding="utf-8"))
    codes = {m["code"] for m in data["billable_metrics"]}
    assert "ai_chat_tokens" in codes
    metric = next(m for m in data["billable_metrics"] if m["code"] == "ai_chat_tokens")
    assert metric["aggregation_type"] == "sum_agg"
    assert metric.get("field_name") == "tokens"

    by_code = {p["code"]: p for p in data["plans"]}
    assert by_code["am_free"]["limits"]["ai_chat_tokens"] == 100_000
    assert by_code["am_pro"]["limits"]["ai_chat_tokens"] == 1_000_000
    assert by_code["am_premium"]["limits"]["ai_chat_tokens"] == 1_000_000
