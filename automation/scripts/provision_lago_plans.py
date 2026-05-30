#!/usr/bin/env python3
"""Provision AM fintech plans in Lago (aligned with am-asrax Subscription.tsx)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PLATFORM_ROOT = SCRIPT_DIR.parent.parent
PLANS_PATH = PLATFORM_ROOT / "automation" / "helm" / "lago-plans.json"


def load_env() -> dict[str, str]:
    merged: dict[str, str] = {}
    for name in (".env", ".secrets.env"):
        path = PLATFORM_ROOT / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            merged[key.strip()] = value.strip()
    return merged


def api_request(
    base_url: str,
    api_key: str,
    method: str,
    path: str,
    body: dict | None = None,
) -> tuple[int, dict | list | str]:
    url = f"{base_url.rstrip('/')}{path}"
    data = None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; AM-Platform/1.0; +https://am.asrax.in)",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            payload = json.loads(raw) if raw else {"error": exc.reason}
        except json.JSONDecodeError:
            payload = {"error": raw or exc.reason}
        return exc.code, payload


def ensure_metric(base_url: str, api_key: str, metric: dict) -> None:
    code = metric["code"]
    status, existing = api_request(base_url, api_key, "GET", f"/api/v1/billable_metrics/{code}")
    if status == 200:
        print(f"  metric {code}: exists")
        return
    payload = {
        "billable_metric": {
            "name": metric["name"],
            "code": code,
            "description": metric.get("description", ""),
            "aggregation_type": metric["aggregation_type"],
            "recurring": False,
        }
    }
    if metric.get("field_name"):
        payload["billable_metric"]["field_name"] = metric["field_name"]
    status, result = api_request(base_url, api_key, "POST", "/api/v1/billable_metrics", payload)
    if status not in (200, 201):
        raise RuntimeError(f"Failed to create metric {code}: {status} {result}")
    print(f"  metric {code}: created")


def list_metrics(base_url: str, api_key: str) -> dict[str, str]:
    """Return metric code -> lago_id."""
    status, result = api_request(base_url, api_key, "GET", "/api/v1/billable_metrics?per_page=100")
    if status != 200:
        raise RuntimeError(f"Failed to list metrics: {status} {result}")
    mapping: dict[str, str] = {}
    for item in result.get("billable_metrics", []):
        mapping[item["code"]] = item["lago_id"]
    return mapping


def package_charge(metric_id: str, metric_code: str, free_units: int, overage_inr: str = "10") -> dict:
    """Package charge: included units free, then overage_inr per unit."""
    return {
        "billable_metric_id": metric_id,
        "code": f"{metric_code}_included",
        "charge_model": "package",
        "pay_in_advance": False,
        "invoiceable": True,
        "properties": {
            "amount": overage_inr,
            "free_units": free_units,
            "package_size": 1,
        },
    }


def build_plan_payload(plan: dict, currency: str, metric_ids: dict[str, str]) -> dict:
    limits = plan.get("limits", {})
    features = plan.get("features", [])
    entitlements = plan.get("entitlements", {})
    description = plan["description"]
    if features:
        description += "\n\nFeatures:\n- " + "\n- ".join(features)
    if entitlements:
        description += "\n\nEntitlements: " + json.dumps(entitlements)

    charges = []
    for metric_code, limit in (
        ("document_parses", limits.get("document_parses")),
        ("portfolios", limits.get("portfolios")),
        ("ai_portfolio_summaries", limits.get("ai_portfolio_summaries")),
        ("api_calls", limits.get("api_calls")),
    ):
        if not limit:
            continue
        metric_id = metric_ids.get(metric_code)
        if not metric_id:
            raise RuntimeError(f"Billable metric not found: {metric_code}")
        charges.append(package_charge(metric_id, metric_code, limit))

    amount_cents = int(plan["amount_inr"] * 100)
    return {
        "plan": {
            "name": plan["name"],
            "code": plan["code"],
            "interval": plan["interval"],
            "description": description,
            "amount_cents": amount_cents,
            "amount_currency": currency,
            "pay_in_advance": amount_cents > 0,
            "trial_period": 0,
            "charges": charges,
        }
    }


def ensure_plan(base_url: str, api_key: str, plan: dict, currency: str, metric_ids: dict[str, str]) -> None:
    code = plan["code"]
    status, _ = api_request(base_url, api_key, "GET", f"/api/v1/plans/{code}")
    if status == 200:
        print(f"  plan {code}: exists (skip)")
        return
    payload = build_plan_payload(plan, currency, metric_ids)
    status, result = api_request(base_url, api_key, "POST", "/api/v1/plans", payload)
    if status not in (200, 201):
        raise RuntimeError(f"Failed to create plan {code}: {status} {result}")
    amount = plan["amount_inr"]
    print(f"  plan {code}: created (INR {amount}/{plan['interval']})")


def main() -> int:
    env = load_env()
    base_url = env.get("LAGO_API_URL", "https://lago.munish.org")
    api_key = env.get("LAGO_ORG_API_KEY")
    if not api_key:
        print("ERROR: LAGO_ORG_API_KEY missing in .secrets.env", file=sys.stderr)
        return 1
    if not PLANS_PATH.is_file():
        print(f"ERROR: {PLANS_PATH} not found", file=sys.stderr)
        return 1

    config = json.loads(PLANS_PATH.read_text(encoding="utf-8"))
    currency = config.get("currency", "INR")

    print(f"Lago API: {base_url}")
    print("Ensuring billable metrics...")
    for metric in config["billable_metrics"]:
        ensure_metric(base_url, api_key, metric)

    metric_ids = list_metrics(base_url, api_key)
    print(f"  loaded {len(metric_ids)} metric id(s)")

    print("Ensuring plans...")
    for plan in config["plans"]:
        if plan["code"] in ("am_free", "am_pro", "am_premium"):
            ensure_plan(base_url, api_key, plan, currency, metric_ids)

    # Annual variants (optional — same limits as monthly)
    for plan in config["plans"]:
        if plan["code"] in ("am_pro_annual", "am_premium_annual"):
            ensure_plan(base_url, api_key, plan, currency, metric_ids)

    print("Done. Plans: am_free, am_pro, am_premium (+ annual variants if new).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
