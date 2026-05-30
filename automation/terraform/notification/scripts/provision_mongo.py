#!/usr/bin/env python3
"""Provision scoped MongoDB users on the shared infra cluster (idempotent)."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys


def run_kubectl(kubeconfig: str, args: list[str]) -> str:
    cmd = ["kubectl", "--kubeconfig", kubeconfig, *args]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        sys.exit(result.returncode)
    return result.stdout


def strip_quotes(value: str) -> str:
    return value.strip().strip('"')


def provision_user(
    kubeconfig: str,
    admin_user: str,
    admin_password: str,
    db_name: str,
    db_user: str,
    db_password: str,
) -> None:
    script = f"""
const targetDb = "{db_name}";
const targetUser = "{db_user}";
const targetPwd = "{db_password}";
const adminDb = db.getSiblingDB("admin");
const userDb = db.getSiblingDB(targetDb);
try {{
  userDb.createCollection("_provision_marker");
}} catch (e) {{}}
const existing = adminDb.system.users.findOne({{ user: targetUser }});
if (existing) {{
  adminDb.updateUser(targetUser, {{ pwd: targetPwd, roles: [{{ role: "readWrite", db: targetDb }}] }});
  print("Updated user " + targetUser + " on db " + targetDb);
}} else {{
  userDb.createUser({{
    user: targetUser,
    pwd: targetPwd,
    roles: [{{ role: "readWrite", db: targetDb }}]
  }});
  print("Created user " + targetUser + " on db " + targetDb);
}}
"""
    run_kubectl(
        kubeconfig,
        [
            "exec",
            "mongodb-0",
            "-n",
            "infra",
            "--",
            "mongosh",
            "--quiet",
            f"mongodb://{admin_user}:{admin_password}@localhost:27017/admin?authSource=admin",
            "--eval",
            script,
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kubeconfig", required=True)
    parser.add_argument("--mongo-user", default="admin")
    parser.add_argument("--mongo-password", required=True)
    parser.add_argument("--notification-db", default="notification")
    parser.add_argument("--notification-user", default="am_notification_user")
    parser.add_argument("--notification-password", required=True)
    parser.add_argument("--novu-db", default="novu")
    parser.add_argument("--novu-user", default="novu_user")
    parser.add_argument("--novu-password", required=True)
    args = parser.parse_args()

    kubeconfig = strip_quotes(args.kubeconfig)
    admin_user = strip_quotes(args.mongo_user)
    admin_password = strip_quotes(args.mongo_password)

    print(json.dumps({"step": "provision_notification_user", "db": args.notification_db}))
    provision_user(
        kubeconfig,
        admin_user,
        admin_password,
        strip_quotes(args.notification_db),
        strip_quotes(args.notification_user),
        strip_quotes(args.notification_password),
    )

    print(json.dumps({"step": "provision_novu_user", "db": args.novu_db}))
    provision_user(
        kubeconfig,
        admin_user,
        admin_password,
        strip_quotes(args.novu_db),
        strip_quotes(args.novu_user),
        strip_quotes(args.novu_password),
    )

    print("MongoDB users provisioned successfully.")


if __name__ == "__main__":
    main()
