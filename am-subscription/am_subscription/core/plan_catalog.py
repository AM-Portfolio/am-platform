from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from am_platform_common import NotFoundError

from am_subscription.core.config import get_settings
from am_subscription.schemas.subscription import (
    PlanDTO,
    PlanEntitlementsDTO,
    PlanLimitsDTO,
)


class PlanCatalog:
    def __init__(self, config_path: str) -> None:
        self._path = Path(config_path)
        self._plans: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        data = json.loads(self._path.read_text(encoding="utf-8"))
        for plan in data.get("plans", []):
            self._plans[plan["code"]] = plan

    def list_plans(self, *, interval: str | None = None) -> list[PlanDTO]:
        plans = []
        for raw in self._plans.values():
            if interval and raw.get("interval") != interval:
                continue
            plans.append(self._to_dto(raw))
        return sorted(plans, key=lambda p: p.amount_inr)

    def get_plan(self, code: str) -> PlanDTO:
        raw = self._plans.get(code)
        if not raw:
            raise NotFoundError(message=f"Unknown plan code: {code}")
        return self._to_dto(raw)

    def resolve_plan_code(self, plan_code: str, billing_interval: str) -> str:
        if plan_code.endswith("_annual") or plan_code.endswith("_yearly"):
            return plan_code
        if billing_interval == "yearly":
            annual_code = f"{plan_code}_annual"
            if annual_code in self._plans:
                return annual_code
        return plan_code

    @staticmethod
    def _to_dto(raw: dict) -> PlanDTO:
        limits = raw.get("limits", {})
        entitlements = raw.get("entitlements", {})
        return PlanDTO(
            code=raw["code"],
            name=raw["name"],
            interval=raw["interval"],
            description=raw["description"],
            amount_inr=raw["amount_inr"],
            features=raw.get("features", []),
            limits=PlanLimitsDTO(**limits),
            entitlements=PlanEntitlementsDTO(**entitlements),
        )


@lru_cache(maxsize=1)
def get_plan_catalog() -> PlanCatalog:
    settings = get_settings()
    return PlanCatalog(settings.plans_config_path)
