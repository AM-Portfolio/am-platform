import sys
import os
import subprocess
import argparse
import tempfile

def run_kubectl_cmd(kubeconfig, args):
    cmd = ["kubectl", "--kubeconfig", kubeconfig] + args
    print(f"Running: {' '.join(cmd)}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error: {res.stderr}")
        sys.exit(res.returncode)
    return res.stdout

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kubeconfig", required=True)
    parser.add_argument("--pg-password", required=True)
    parser.add_argument("--pg-user", default="postgres")
    parser.add_argument("--pg-db", default="portfolio")
    parser.add_argument("--sub-db", default="subscription")
    parser.add_argument("--sub-user", default="am_subscription_user")
    parser.add_argument("--sub-password", required=True)
    args = parser.parse_args()

    # Strip any extra quotes passed by shell escaping on Windows
    args.kubeconfig = args.kubeconfig.strip('"')
    args.pg_password = args.pg_password.strip('"')
    args.pg_user = args.pg_user.strip('"')
    args.pg_db = args.pg_db.strip('"')
    args.sub_db = args.sub_db.strip('"')
    args.sub_user = args.sub_user.strip('"')
    args.sub_password = args.sub_password.strip('"')

    # Step 1: Check if database exists
    check_db_cmd = [
        "exec", "postgresql-0", "-n", "infra", "--",
        "env", f"PGPASSWORD={args.pg_password}",
        "psql", "-U", args.pg_user, "-d", args.pg_db, "-t", "-c",
        f"SELECT count(*) FROM pg_database WHERE datname = '{args.sub_db}';"
    ]
    db_count = run_kubectl_cmd(args.kubeconfig, check_db_cmd).strip()
    print(f"Database {args.sub_db} count: {db_count}")

    # Step 2: Check if role exists
    check_role_cmd = [
        "exec", "postgresql-0", "-n", "infra", "--",
        "env", f"PGPASSWORD={args.pg_password}",
        "psql", "-U", args.pg_user, "-d", args.pg_db, "-t", "-c",
        f"SELECT count(*) FROM pg_roles WHERE rolname = '{args.sub_user}';"
    ]
    role_count = run_kubectl_cmd(args.kubeconfig, check_role_cmd).strip()
    print(f"Role {args.sub_user} count: {role_count}")

    # Step 3: Write SQL script to temporary file for user creation
    sql_content = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{args.sub_user}') THEN
        CREATE ROLE {args.sub_user} WITH LOGIN PASSWORD '{args.sub_password}';
    ELSE
        ALTER ROLE {args.sub_user} WITH PASSWORD '{args.sub_password}';
    END IF;
END
$$;
"""
    
    # Write to local temp file (using relative path to avoid drive letter colon in kubectl cp)
    local_sql_path = "./provision.sql"
    with open(local_sql_path, "w", encoding="utf-8") as f:
        f.write(sql_content)

    try:
        # Copy to postgresql-0 pod /tmp/provision.sql
        print("Copying SQL script to PostgreSQL pod...")
        run_kubectl_cmd(args.kubeconfig, ["cp", local_sql_path, "infra/postgresql-0:/tmp/provision.sql"])

        # Execute script to setup user
        print("Executing user provisioning SQL...")
        run_kubectl_cmd(args.kubeconfig, [
            "exec", "postgresql-0", "-n", "infra", "--",
            "env", f"PGPASSWORD={args.pg_password}",
            "psql", "-U", args.pg_user, "-d", args.pg_db, "-f", "/tmp/provision.sql"
        ])

        # If DB count is '0', create the database
        if db_count == "0" or db_count == "":
            print(f"Creating database {args.sub_db}...")
            run_kubectl_cmd(args.kubeconfig, [
                "exec", "postgresql-0", "-n", "infra", "--",
                "env", f"PGPASSWORD={args.pg_password}",
                "psql", "-U", args.pg_user, "-d", args.pg_db, "-c",
                f"CREATE DATABASE {args.sub_db} OWNER {args.sub_user};"
            ])
        else:
            print(f"Database {args.sub_db} already exists, skipping creation.")

        # Grant privileges
        print(f"Granting privileges on database {args.sub_db} to {args.sub_user}...")
        run_kubectl_cmd(args.kubeconfig, [
            "exec", "postgresql-0", "-n", "infra", "--",
            "env", f"PGPASSWORD={args.pg_password}",
            "psql", "-U", args.pg_user, "-d", args.pg_db, "-c",
            f"GRANT ALL PRIVILEGES ON DATABASE {args.sub_db} TO {args.sub_user};"
        ])

    finally:
        # Clean up local file
        if os.path.exists(local_sql_path):
            os.remove(local_sql_path)
        # Clean up pod file
        run_kubectl_cmd(args.kubeconfig, ["exec", "postgresql-0", "-n", "infra", "--", "rm", "-f", "/tmp/provision.sql"])

    print("PostgreSQL User and Database provisioned successfully!")

if __name__ == "__main__":
    main()
