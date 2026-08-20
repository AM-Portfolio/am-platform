from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from am_mcp_hub.core.config import get_settings
from am_mcp_hub.models.db import Integration, OrgIntegration, Organization

DEFAULT_INTEGRATIONS: list[dict[str, str]] = [
    {
        "slug": "github",
        "display_name": "GitHub",
        "adapter_type": "github",
        "description": "GitHub MCP / REST tools (token via Vault path)",
    },
    {
        "slug": "vault",
        "display_name": "Vault",
        "adapter_type": "vault",
        "description": "HashiCorp Vault list/read via VAULT_ADDR + token ref",
    },
    {
        "slug": "litellm",
        "display_name": "LiteLLM",
        "adapter_type": "litellm",
        "description": "LiteLLM proxy health and model list",
    },
    {
        "slug": "am-qa-agent",
        "display_name": "AM QA Agent",
        "adapter_type": "qa_agent",
        "description": "Public QA agent health/catalog on am-*.asrax.in/qa",
    },
    {
        "slug": "am-tool-agent",
        "display_name": "AM Tool Agent",
        "adapter_type": "tool_agent",
        "description": "Public tool agent health on am-*.asrax.in/tools",
    },
    {
        "slug": "google-workspace",
        "display_name": "Google Workspace",
        "adapter_type": "google_workspace",
        "description": "One Google MCP (Gmail/Drive/Docs/…) via workspace-mcp; explore with official MCP Inspector",
    },
]


async def seed_catalog(session: AsyncSession) -> None:
    settings = get_settings()
    org = (
        await session.execute(
            select(Organization).where(Organization.slug == settings.default_org_slug)
        )
    ).scalar_one_or_none()
    if org is None:
        org = Organization(slug=settings.default_org_slug, name=settings.default_org_name)
        session.add(org)
        await session.flush()

    for item in DEFAULT_INTEGRATIONS:
        existing = (
            await session.execute(select(Integration).where(Integration.slug == item["slug"]))
        ).scalar_one_or_none()
        if existing is None:
            integ = Integration(
                slug=item["slug"],
                display_name=item["display_name"],
                adapter_type=item["adapter_type"],
                description=item["description"],
                default_config={},
            )
            session.add(integ)
            await session.flush()
        else:
            integ = existing

        link = (
            await session.execute(
                select(OrgIntegration).where(
                    OrgIntegration.org_id == org.id,
                    OrgIntegration.integration_id == integ.id,
                )
            )
        ).scalar_one_or_none()
        if link is None:
            session.add(
                OrgIntegration(
                    org_id=org.id,
                    integration_id=integ.id,
                    enabled=True,
                    vault_path=None,
                    settings={},
                )
            )
