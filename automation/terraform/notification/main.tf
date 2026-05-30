terraform {
  required_providers {
    null = {
      source  = "hashicorp/null"
      version = ">= 3.2.0"
    }
  }
  required_version = ">= 1.5.0"
}

locals {
  workflows_path = var.workflows_json_path != "" ? var.workflows_json_path : abspath("${path.module}/../../helm/novu-workflows.json")
}

# =========================================================
# MONGO — scoped users on shared infra MongoDB cluster
# (Novu Helm is deployed via automation/helm/deploy-novu.ps1)
# =========================================================

resource "null_resource" "provision_mongo" {
  triggers = {
    notification_user     = var.notification_db_user
    notification_password = var.notification_db_password
    notification_db       = var.notification_db_name
    novu_user             = var.novu_db_user
    novu_password         = var.novu_db_password
    novu_db               = var.novu_db_name
  }

  provisioner "local-exec" {
    command = join(" ", [
      "python", "${path.module}/scripts/provision_mongo.py",
      "--kubeconfig", "\"${var.kubeconfig_path}\"",
      "--mongo-password", "\"${var.mongo_admin_password}\"",
      "--mongo-user", "\"${var.mongo_admin_user}\"",
      "--notification-db", "\"${var.notification_db_name}\"",
      "--notification-user", "\"${var.notification_db_user}\"",
      "--notification-password", "\"${var.notification_db_password}\"",
      "--novu-db", "\"${var.novu_db_name}\"",
      "--novu-user", "\"${var.novu_db_user}\"",
      "--novu-password", "\"${var.novu_db_password}\"",
    ])
  }
}

resource "null_resource" "provision_novu_workflows" {
  depends_on = [null_resource.provision_mongo]

  triggers = {
    workflows_file = filesha256(local.workflows_path)
    novu_api_url   = var.novu_api_url
    novu_dev_api_key = var.novu_dev_api_key
  }

  provisioner "local-exec" {
    command = join(" ", [
      "python", "${path.module}/scripts/provision_novu_workflows.py",
      "--workflows", "\"${local.workflows_path}\"",
      "--novu-api-url", "\"${var.novu_api_url}\"",
      "--novu-api-key", "\"${var.novu_dev_api_key != "" ? var.novu_dev_api_key : var.novu_api_key}\"",
      "--novu-admin-email", "\"${var.novu_admin_email}\"",
      "--novu-admin-password", "\"${var.novu_admin_password}\"",
      "--novu-dev-environment-id", "\"${var.novu_dev_environment_id}\"",
    ])
  }
}
