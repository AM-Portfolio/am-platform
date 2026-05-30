#!/usr/bin/env python3
"""Idempotent sync of novu-workflows.json to Novu (Development) and promote to Production."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import httpx


def strip_quotes(value: str) -> str:
    return value.strip().strip('"')


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def build_steps(raw_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for index, step in enumerate(raw_steps):
        step_type = step["type"]
        name = step.get("name") or step_type.replace("_", " ").title()
        if step_type == "email":
            template = {
                "type": "email",
                "subject": step.get("subject", "Notification"),
                "content": f"<p>{step.get('template', '')}</p>",
            }
        else:
            template = {
                "type": step_type,
                "subject": step.get("subject", name),
                "content": step.get("template", ""),
            }
        steps.append({"name": name, "template": template, "active": True})
    return steps


def get_notification_group_id(client: httpx.Client, base_url: str, headers: dict[str, str]) -> str:
    response = client.get(f"{base_url}/v1/notification-groups", headers=headers)
    if response.status_code >= 400:
        print(f"Failed to list notification groups: {response.status_code} {response.text[:300]}")
        sys.exit(1)
    groups = response.json().get("data", [])
    if not groups:
        print("No notification groups found in Novu Development environment.")
        sys.exit(1)
    return str(groups[0]["_id"])


def find_existing_template(
    client: httpx.Client, base_url: str, headers: dict[str, str], trigger_id: str
) -> dict[str, Any] | None:
    response = client.get(
        f"{base_url}/v1/notification-templates",
        headers=headers,
        params={"page": 0, "limit": 100},
    )
    if response.status_code >= 400:
        print(f"Failed to list workflows: {response.status_code} {response.text[:300]}")
        sys.exit(1)
    for item in response.json().get("data", []):
        triggers = item.get("triggers") or []
        if triggers and triggers[0].get("identifier") == trigger_id:
            return item
    return None


def promote_dev_changes(
    client: httpx.Client,
    base_url: str,
    *,
    admin_email: str,
    admin_password: str,
    dev_environment_id: str,
) -> None:
    login = client.post(
        f"{base_url}/v1/auth/login",
        json={"email": admin_email, "password": admin_password},
    )
    if login.status_code >= 400:
        print(f"Novu admin login failed: {login.status_code} {login.text[:300]}")
        sys.exit(1)
    token = login.json().get("data", {}).get("token")
    if not token:
        print("Novu admin login returned no token.")
        sys.exit(1)

    auth_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "novu-environment-id": dev_environment_id,
    }
    pending = client.get(
        f"{base_url}/v1/changes",
        headers=auth_headers,
        params={"promoted": "false"},
    )
    if pending.status_code >= 400:
        print(f"Failed to list pending changes: {pending.status_code} {pending.text[:300]}")
        sys.exit(1)

    changes = pending.json().get("data", [])
    if not changes:
        print("No pending Novu changes to promote.")
        return

    promoted = 0
    for change in changes:
        change_id = change.get("_id")
        if not change_id:
            continue
        apply_resp = client.post(f"{base_url}/v1/changes/{change_id}/apply", headers=auth_headers, json={})
        if apply_resp.status_code >= 400:
            print(f"Failed to promote change {change_id}: {apply_resp.status_code} {apply_resp.text[:200]}")
            sys.exit(1)
        promoted += 1
    print(f"Promoted {promoted} Novu change(s) to Production.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflows", required=True)
    parser.add_argument("--novu-api-url", default="https://novu-api.munish.org")
    parser.add_argument("--novu-api-key", default="", help="Development environment API key")
    parser.add_argument("--novu-admin-email", default="")
    parser.add_argument("--novu-admin-password", default="")
    parser.add_argument("--novu-dev-environment-id", default="")
    args = parser.parse_args()

    api_key = strip_quotes(args.novu_api_key)
    if not api_key or api_key.startswith("<"):
        print("NOVU_DEV_API_KEY / NOVU_API_KEY not set — skipping workflow seed.")
        return

    workflows_path = Path(strip_quotes(args.workflows))
    if not workflows_path.is_file():
        print(f"Workflows file not found: {workflows_path}", file=sys.stderr)
        sys.exit(1)

    workflows = json.loads(workflows_path.read_text(encoding="utf-8"))
    base_url = strip_quotes(args.novu_api_url).rstrip("/")
    headers = {
        "Authorization": f"ApiKey {api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=60.0) as client:
        group_id = get_notification_group_id(client, base_url, headers)

        for workflow in workflows:
            workflow_key = workflow["workflow_key"]
            trigger_id = slugify(workflow_key)
            payload = {
                "name": workflow_key,
                "description": workflow_key,
                "notificationGroupId": group_id,
                "active": True,
                "draft": False,
                "preferenceSettings": {
                    "email": True,
                    "sms": False,
                    "in_app": True,
                    "chat": False,
                    "push": False,
                },
                "tags": [],
                "steps": build_steps(workflow.get("steps", [])),
            }

            existing = find_existing_template(client, base_url, headers, trigger_id)
            if existing:
                template_id = existing["_id"]
                resp = client.put(
                    f"{base_url}/v1/notification-templates/{template_id}",
                    headers=headers,
                    json=payload,
                )
                action = "updated"
            else:
                resp = client.post(
                    f"{base_url}/v1/notification-templates",
                    headers=headers,
                    json=payload,
                )
                action = "created"

            if resp.status_code >= 400:
                print(f"Failed to sync {workflow_key}: {resp.status_code} {resp.text[:300]}")
                sys.exit(1)
            print(f"Workflow {workflow_key} ({trigger_id}) {action} in Development.")

        admin_email = strip_quotes(args.novu_admin_email)
        admin_password = strip_quotes(args.novu_admin_password)
        dev_env_id = strip_quotes(args.novu_dev_environment_id)
        if admin_email and admin_password and dev_env_id:
            promote_dev_changes(
                client,
                base_url,
                admin_email=admin_email,
                admin_password=admin_password,
                dev_environment_id=dev_env_id,
            )
        else:
            print("Novu admin credentials or dev environment id missing — skipped Production promote.")

    print("Novu workflows synced successfully.")


if __name__ == "__main__":
    main()
