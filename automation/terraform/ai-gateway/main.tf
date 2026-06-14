terraform {
  required_version = ">= 1.5.0"
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.23.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 2.12.0, < 3.0.0"
    }
  }
}

provider "kubernetes" {
  config_path = var.kubeconfig_path
}

provider "helm" {
  kubernetes {
    config_path = var.kubeconfig_path
  }
}

module "ai_gateway" {
  source = "../modules/ai-gateway"

  kubeconfig_path           = var.kubeconfig_path
  litellm_master_key        = var.litellm_master_key
  deepseek_api_key          = var.deepseek_api_key
  google_api_key            = var.google_api_key
  langfuse_public_key       = var.langfuse_public_key
  langfuse_secret_key       = var.langfuse_secret_key
  langfuse_nextauth_secret  = var.langfuse_nextauth_secret
  langfuse_host             = var.langfuse_host
  langfuse_db_password      = var.langfuse_db_password
  litellm_db_password       = var.litellm_db_password
  together_api_key          = var.together_api_key
}
