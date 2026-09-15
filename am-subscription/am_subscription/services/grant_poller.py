"""Background poller for delayed grants and timed-Pro expiry."""

from __future__ import annotations

import asyncio

from am_subscription.core.config import get_settings
from am_subscription.core.database import get_session_factory
from am_subscription.core.log_utils import get_logger
from am_subscription.core.plan_catalog import get_plan_catalog
from am_subscription.providers.lago_provider import LagoProvider
from am_subscription.services.event_publisher import EventPublisher
from am_subscription.services.grant_service import GrantService
from am_subscription.services.referral_service import ReferralService
from am_subscription.services.subscription_service import SubscriptionService

logger = get_logger("grant_poller")


class GrantPoller:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        settings = get_settings()
        if not settings.grant_poller_enabled:
            logger.info("Grant poller disabled")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "Grant poller started",
            extra={"interval_seconds": settings.grant_poller_interval_seconds},
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Grant poller stopped")

    async def _loop(self) -> None:
        settings = get_settings()
        interval = max(5, int(settings.grant_poller_interval_seconds))
        while self._running:
            try:
                await self.tick()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("grant_poller_tick_failed")
            await asyncio.sleep(interval)

    async def tick(self) -> dict[str, int]:
        settings = get_settings()
        factory = get_session_factory()
        async with factory() as session:
            catalog = get_plan_catalog()
            provider = LagoProvider(settings)
            events = EventPublisher(settings)
            subs = SubscriptionService(
                session, catalog, provider, events, settings.default_plan_code
            )
            referrals = ReferralService(session, settings)
            grants = GrantService(
                session, settings, subs, referrals, provider, events
            )
            due = await grants.process_due_schedules()
            expired = await grants.process_expiries()
            if due or expired:
                logger.info(
                    "grant_poller_tick",
                    extra={"schedules_done": due, "expiries": expired},
                )
            return {"schedules_done": due, "expiries": expired}


grant_poller_instance = GrantPoller()
