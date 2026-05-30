terraform {
  required_providers {
    null = {
      source  = "hashicorp/null"
      version = ">= 3.2.0"
    }
  }
}

# =========================================================
# POSTGRES — logical subscription database & user
# (Lago Helm chart is deployed via automation/helm/deploy-lago.ps1)
# =========================================================

resource "null_resource" "provision_db" {
  triggers = {
    sub_user     = var.subscription_db_user
    sub_password = var.subscription_db_password
    sub_db       = var.subscription_db_name
  }

  provisioner "local-exec" {
    command = "python ${path.module}/scripts/provision_db.py --kubeconfig \"${var.kubeconfig_path}\" --pg-password \"${var.postgres_password}\" --pg-user \"${var.postgres_user}\" --pg-db \"${var.postgres_db}\" --sub-db \"${var.subscription_db_name}\" --sub-user \"${var.subscription_db_user}\" --sub-password \"${var.subscription_db_password}\""
  }
}
