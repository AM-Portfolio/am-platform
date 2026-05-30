terraform {
  required_providers {
    keycloak = {
      source  = "mrparkers/keycloak"
      version = ">= 4.4.0"
    }
  }
  required_version = ">= 1.5.0"
}

provider "keycloak" {
  client_id = "admin-cli"
  username  = var.keycloak_admin_username
  password  = var.keycloak_admin_password
  url       = var.keycloak_url
}

# =========================================================
# MODULES
# =========================================================

module "keycloak" {
  source = "./modules/keycloak"

  keycloak_url            = var.keycloak_url
  keycloak_admin_username = var.keycloak_admin_username
  keycloak_admin_password = var.keycloak_admin_password
  realm_name              = var.realm_name
  google_client_id        = var.google_client_id
  google_client_secret    = var.google_client_secret
}

module "billing" {
  source = "./modules/billing"

  kubeconfig_path           = "${path.cwd}/${var.kubeconfig_path}"
  postgres_host             = var.postgres_host
  postgres_user             = var.postgres_user
  postgres_password         = var.postgres_password
  postgres_db               = var.postgres_db
  subscription_db_name      = var.subscription_db_name
  subscription_db_user      = var.subscription_db_user
  subscription_db_password  = var.subscription_db_password
}
