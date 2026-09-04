from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from am_mcp_hub.models.db import Integration, OrgIntegration, Organization


@dataclass(frozen=True, slots=True)
class EnabledIntegration:
    slug: str
    display_name: str
    adapter_type: str
    description: str | None
    vault_path: str | None
    settings: dict
    enabled: bool


async def list_integrations(session: AsyncSession, org_slug: str) -> list[EnabledIntegration]:
    org = (
        await session.execute(select(Organization).where(Organization.slug == org_slug))
    ).scalar_one_or_none()
    if org is None:
        return []
    rows = (
        await session.execute(
            select(OrgIntegration, Integration)
            .join(Integration, Integration.id == OrgIntegration.integration_id)
            .where(OrgIntegration.org_id == org.id)
            .order_by(Integration.slug)
        )
    ).all()
    out: list[EnabledIntegration] = []
    for link, integ in rows:
        out.append(
            EnabledIntegration(
                slug=integ.slug,
                display_name=integ.display_name,
                adapter_type=integ.adapter_type,
                description=integ.description,
                vault_path=link.vault_path,
                settings=dict(link.settings or {}),
                enabled=bool(link.enabled),
            )
        )
    return out


async def set_org_integration(
    session: AsyncSession,
    *,
    org_slug: str,
    slug: str,
    enabled: bool | None = None,
    vault_path: str | None = None,
    settings: dict | None = None,
) -> EnabledIntegration:
    org = (
        await session.execute(select(Organization).where(Organization.slug == org_slug))
    ).scalar_one()
    integ = (
        await session.execute(select(Integration).where(Integration.slug == slug))
    ).scalar_one()
    link = (
        await session.execute(
            select(OrgIntegration).where(
                OrgIntegration.org_id == org.id,
                OrgIntegration.integration_id == integ.id,
            )
        )
    ).scalar_one_or_none()
    if link is None:
        link = OrgIntegration(org_id=org.id, integration_id=integ.id, enabled=False)
        session.add(link)
    if enabled is not None:
        link.enabled = enabled
    if vault_path is not None:
        link.vault_path = vault_path or None
    if settings is not None:
        link.settings = settings
    await session.flush()
    return EnabledIntegration(
        slug=integ.slug,
        display_name=integ.display_name,
        adapter_type=integ.adapter_type,
        description=integ.description,
        vault_path=link.vault_path,
        settings=dict(link.settings or {}),
        enabled=bool(link.enabled),
    )


async def enabled_only(session: AsyncSession, org_slug: str) -> list[EnabledIntegration]:
    return [i for i in await list_integrations(session, org_slug) if i.enabled]
