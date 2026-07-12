#!/usr/bin/env python3
"""
run_terraform.py - python wrapper for running Terraform independently on modules.
Usage: python automation/scripts/run_terraform.py [keycloak|billing|notification] [init|plan|apply|output]
"""
import sys
import os
import subprocess
import platform
import urllib.request
import zipfile
import json
import secrets

TERRAFORM_VERSION = "1.9.8"
PLATFORM = "windows" if os.name == "nt" else ("darwin" if platform.system() == "Darwin" else "linux")
ARCH = "amd64"
EXE = "terraform.exe" if os.name == "nt" else "terraform"

SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
PLATFORM_ROOT  = os.path.dirname(os.path.dirname(SCRIPT_DIR))          # am-platform/
BIN_DIR        = os.path.join(PLATFORM_ROOT, "automation", ".bin")
TF_BIN         = os.path.join(BIN_DIR, EXE)


def _load_env_file(path: str) -> dict[str, str]:
    if not os.path.isfile(path):
        return {}
    values: dict[str, str] = {}
    with open(path, encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _export_terraform_vars(target_folder: str) -> None:
    """Map platform env files to target Terraform folder's auto.tfvars.json."""
    secrets_path = os.path.join(PLATFORM_ROOT, ".secrets.env")
    env_path = os.path.join(PLATFORM_ROOT, ".env")
    app_env = os.environ.get("APP_ENV") or _load_env_file(env_path).get("APP_ENV", "")
    env_secrets = (
        _load_env_file(os.path.join(PLATFORM_ROOT, f".secrets.{app_env}.env"))
        if app_env
        else {}
    )
    # Prefer env-specific secrets (e.g. .secrets.preprod.env) over legacy .secrets.env
    merged = {**_load_env_file(env_path), **_load_env_file(secrets_path), **env_secrets}

    sub_pwd = merged.get("AM_SUBSCRIPTION_DB_PASSWORD")
    if not sub_pwd or sub_pwd.startswith("<"):
        sub_pwd = secrets.token_hex(16)
        print("Generated new subscription DB password and appending to .secrets.env")
        try:
            with open(secrets_path, "a", encoding="utf-8") as f:
                f.write(f"\n# Auto-generated subscription database password\nAM_SUBSCRIPTION_DB_PASSWORD={sub_pwd}\n")
        except Exception as e:
            print(f"Warning: Could not append password to .secrets.env: {e}")
        merged["AM_SUBSCRIPTION_DB_PASSWORD"] = sub_pwd

    tf_vars = {}

    if target_folder == "keycloak":
        mapping = {
            "GOOGLE_CLIENT_ID": "google_client_id",
            "GOOGLE_CLIENT_SECRET": "google_client_secret",
            "KEYCLOAK_URL": "keycloak_url",
            "KEYCLOAK_ADMIN_USER": "keycloak_admin_username",
            "KEYCLOAK_ADMIN_PASSWORD": "keycloak_admin_password",
            "KEYCLOAK_REALM": "realm_name",
            "KEYCLOAK_SMTP_HOST": "smtp_host",
            "KEYCLOAK_SMTP_PORT": "smtp_port",
            "KEYCLOAK_SMTP_FROM": "smtp_from",
            "KEYCLOAK_SMTP_FROM_DISPLAY_NAME": "smtp_from_display_name",
            "KEYCLOAK_SMTP_USER": "smtp_user",
            "KEYCLOAK_SMTP_PASSWORD": "smtp_password",
        }
        for env_key, tf_key in mapping.items():
            val = merged.get(env_key)
            if val and not val.startswith("<"):
                tf_vars[tf_key] = val
        if merged.get("KEYCLOAK_SMTP_SSL", "").lower() in ("true", "1", "yes"):
            tf_vars["smtp_ssl"] = True
        elif merged.get("KEYCLOAK_SMTP_SSL", "").lower() in ("false", "0", "no"):
            tf_vars["smtp_ssl"] = False
        if merged.get("KEYCLOAK_SMTP_STARTTLS", "").lower() in ("true", "1", "yes"):
            tf_vars["smtp_starttls"] = True
        elif merged.get("KEYCLOAK_SMTP_STARTTLS", "").lower() in ("false", "0", "no"):
            tf_vars["smtp_starttls"] = False

    elif target_folder == "billing":
        mapping = {
            "POSTGRES_HOST": "postgres_host",
            "POSTGRES_USER": "postgres_user",
            "POSTGRES_PASSWORD": "postgres_password",
            "POSTGRES_DB": "postgres_db",
            "AM_SUBSCRIPTION_DB_NAME": "subscription_db_name",
            "AM_SUBSCRIPTION_DB_USER": "subscription_db_user",
            "AM_SUBSCRIPTION_DB_PASSWORD": "subscription_db_password"
        }
        for env_key, tf_key in mapping.items():
            val = merged.get(env_key)
            if val and not val.startswith("<"):
                tf_vars[tf_key] = val

        # Resolve and pass absolute kubeconfig path
        kubeconfig_abs = os.path.abspath(os.path.join(PLATFORM_ROOT, "..", "VPS", "kubeconfig.vps"))
        tf_vars["kubeconfig_path"] = kubeconfig_abs

    elif target_folder == "notification":
        notif_pwd = merged.get("AM_NOTIFICATION_DB_PASSWORD")
        if not notif_pwd or notif_pwd.startswith("<"):
            notif_pwd = secrets.token_hex(16)
            print("Generated new notification DB password and appending to .secrets.env")
            try:
                with open(secrets_path, "a", encoding="utf-8") as f:
                    f.write(f"\n# Auto-generated notification database password\nAM_NOTIFICATION_DB_PASSWORD={notif_pwd}\n")
            except Exception as e:
                print(f"Warning: Could not append password to .secrets.env: {e}")
            merged["AM_NOTIFICATION_DB_PASSWORD"] = notif_pwd

        novu_pwd = merged.get("NOVU_DB_PASSWORD")
        if not novu_pwd or novu_pwd.startswith("<"):
            novu_pwd = secrets.token_hex(16)
            print("Generated new Novu DB password and appending to .secrets.env")
            try:
                with open(secrets_path, "a", encoding="utf-8") as f:
                    f.write(f"\n# Auto-generated Novu MongoDB password\nNOVU_DB_PASSWORD={novu_pwd}\n")
            except Exception as e:
                print(f"Warning: Could not append Novu password to .secrets.env: {e}")
            merged["NOVU_DB_PASSWORD"] = novu_pwd

        mapping = {
            "MONGODB_ADMIN_USER": "mongo_admin_user",
            "MONGODB_ADMIN_PASSWORD": "mongo_admin_password",
            "AM_NOTIFICATION_DB_NAME": "notification_db_name",
            "AM_NOTIFICATION_DB_USER": "notification_db_user",
            "AM_NOTIFICATION_DB_PASSWORD": "notification_db_password",
            "NOVU_DB_NAME": "novu_db_name",
            "NOVU_DB_USER": "novu_db_user",
            "NOVU_DB_PASSWORD": "novu_db_password",
            "NOVU_API_URL": "novu_api_url",
            "NOVU_API_KEY": "novu_api_key",
            "NOVU_DEV_API_KEY": "novu_dev_api_key",
            "NOVU_ADMIN_EMAIL": "novu_admin_email",
            "NOVU_ADMIN_PASSWORD": "novu_admin_password",
            "NOVU_DEV_ENVIRONMENT_ID": "novu_dev_environment_id",
        }
        for env_key, tf_key in mapping.items():
            val = merged.get(env_key)
            if val and not val.startswith("<"):
                tf_vars[tf_key] = val

        kubeconfig_abs = os.path.abspath(os.path.join(PLATFORM_ROOT, "..", "VPS", "kubeconfig.vps"))
        tf_vars["kubeconfig_path"] = kubeconfig_abs

    target_tf_dir = os.path.join(PLATFORM_ROOT, "automation", "terraform", target_folder)
    vars_path = os.path.join(target_tf_dir, "generated.auto.tfvars.json")
    
    with open(vars_path, "w", encoding="utf-8") as f:
        json.dump(tf_vars, f, indent=2)
    print(f"Generated auto.tfvars at {vars_path}")


DOWNLOAD_URL = (
    f"https://releases.hashicorp.com/terraform/{TERRAFORM_VERSION}/"
    f"terraform_{TERRAFORM_VERSION}_{PLATFORM}_{ARCH}.zip"
)


def ensure_terraform():
    """Downloads and extracts Terraform binary if not already present."""
    if os.path.isfile(TF_BIN):
        return TF_BIN

    print(f"Terraform binary not found — downloading v{TERRAFORM_VERSION}…")
    os.makedirs(BIN_DIR, exist_ok=True)
    zip_path = os.path.join(BIN_DIR, "terraform.zip")

    try:
        urllib.request.urlretrieve(DOWNLOAD_URL, zip_path)
    except Exception as exc:
        print(f"ERROR: Failed to download Terraform: {exc}")
        print(f"Please download manually from: {DOWNLOAD_URL}")
        print(f"and place the '{EXE}' binary in: {BIN_DIR}")
        sys.exit(1)

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(BIN_DIR)

    os.remove(zip_path)

    if not os.path.isfile(TF_BIN):
        print(f"ERROR: Binary not found at {TF_BIN} after extraction.")
        sys.exit(1)

    if PLATFORM != "windows":
        os.chmod(TF_BIN, 0o755)

    print(f"Terraform v{TERRAFORM_VERSION} ready at {TF_BIN}")
    return TF_BIN


def run(cmd: list[str], target_tf_dir: str):
    print(f"\n>>> Running in {target_tf_dir}: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, cwd=target_tf_dir)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main():
    if len(sys.argv) < 3:
        print("Usage: python run_terraform.py [keycloak|billing|notification] [init|plan|apply|output]")
        sys.exit(1)

    folder = sys.argv[1].lower()
    action = sys.argv[2].lower()

    if folder not in ("keycloak", "billing", "notification"):
        print(f"ERROR: Invalid folder '{folder}'. Must be 'keycloak', 'billing', or 'notification'.")
        sys.exit(1)

    target_tf_dir = os.path.join(PLATFORM_ROOT, "automation", "terraform", folder)
    if not os.path.isdir(target_tf_dir):
        print(f"ERROR: Directory '{target_tf_dir}' does not exist.")
        sys.exit(1)

    tf = ensure_terraform()
    _export_terraform_vars(folder)

    if action == "init":
        run([tf, "init", "-upgrade"], target_tf_dir)
    elif action == "plan":
        run([tf, "plan"], target_tf_dir)
    elif action == "apply":
        run([tf, "apply", "-auto-approve"], target_tf_dir)
    elif action == "output":
        run([tf, "output"], target_tf_dir)
    else:
        print(f"ERROR: Unknown action '{action}'. Use: init, plan, apply, output")
        sys.exit(1)


if __name__ == "__main__":
    main()
