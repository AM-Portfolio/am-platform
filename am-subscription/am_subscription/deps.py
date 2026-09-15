from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from am_subscription.core.config import SubscriptionSettings, get_settings
from am_subscription.core.database import get_db_session
from am_subscription.core.plan_catalog import PlanCatalog, get_plan_catalog
from am_subscription.providers.lago_provider import LagoProvider
from am_subscription.services.entitlement_service import (
    EntitlementService,
    MeteringService,
)
from am_subscription.services.event_publisher import EventPublisher
from am_subscription.services.grant_service import GrantService
from am_subscription.services.referral_service import ReferralService
from am_subscription.services.subscription_service import SubscriptionService


@lru_cache(maxsize=1)
def get_lago_provider() -> LagoProvider:
    return LagoProvider(get_settings())


@lru_cache(maxsize=1)
def get_event_publisher() -> EventPublisher:
    return EventPublisher(get_settings())


def get_subscription_service(
    session: AsyncSession = Depends(get_db_session),
    catalog: PlanCatalog = Depends(get_plan_catalog),
    provider: LagoProvider = Depends(get_lago_provider),
    events: EventPublisher = Depends(get_event_publisher),
    settings: SubscriptionSettings = Depends(get_settings),
) -> SubscriptionService:
    return SubscriptionService(
        session, catalog, provider, events, settings.default_plan_code
    )


def get_entitlement_service(
    session: AsyncSession = Depends(get_db_session),
    catalog: PlanCatalog = Depends(get_plan_catalog),
    events: EventPublisher = Depends(get_event_publisher),
) -> EntitlementService:
    return EntitlementService(session, catalog, events)


def get_metering_service(
    session: AsyncSession = Depends(get_db_session),
    provider: LagoProvider = Depends(get_lago_provider),
    events: EventPublisher = Depends(get_event_publisher),
) -> MeteringService:
    return MeteringService(session, provider, events)


def get_referral_service(
    session: AsyncSession = Depends(get_db_session),
    settings: SubscriptionSettings = Depends(get_settings),
) -> ReferralService:
    service = ReferralService(session, settings)
    service.lifetime_cap = settings.referral_lifetime_cap
    service.daily_cap = settings.referral_daily_cap
    return service


def get_grant_service(
    session: AsyncSession = Depends(get_db_session),
    settings: SubscriptionSettings = Depends(get_settings),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    referral_service: ReferralService = Depends(get_referral_service),
    provider: LagoProvider = Depends(get_lago_provider),
    events: EventPublisher = Depends(get_event_publisher),
) -> GrantService:
    return GrantService(
        session,
        settings,
        subscription_service,
        referral_service,
        provider,
        events,
    )
