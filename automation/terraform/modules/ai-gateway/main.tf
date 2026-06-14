# ============================================================
# Terraform Module: ai-gateway
# Provisions the full AM AI infrastructure in Kubernetes:
#   - am-ai namespace
#   - LiteLLM proxy (OpenAI-compatible LLM router)
#   - Langfuse (LLM observability + tracing)
#   - Qdrant (vector store)
#   - MLflow (experiment tracking)
#   - Ollama (local Qwen2.5-VL vision model)
# ============================================================

terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.23.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = ">= 2.12.0"
    }
  }
}

# ── Namespace ────────────────────────────────────────────────
resource "kubernetes_namespace" "am_ai" {
  metadata {
    name = "am-ai"
    labels = {
      "app.kubernetes.io/managed-by" = "terraform"
      "am.platform/tier"             = "ai"
    }
  }
}

# ── LiteLLM Secret ───────────────────────────────────────────
resource "kubernetes_secret" "litellm_secrets" {
  metadata {
    name      = "litellm-secrets"
    namespace = kubernetes_namespace.am_ai.metadata[0].name
  }
  data = {
    LITELLM_MASTER_KEY  = var.litellm_master_key
    DEEPSEEK_API_KEY    = var.deepseek_api_key
    GOOGLE_API_KEY      = var.google_api_key
    LANGFUSE_PUBLIC_KEY = var.langfuse_public_key
    LANGFUSE_SECRET_KEY = var.langfuse_secret_key
    TOGETHER_API_KEY    = var.together_api_key
    DATABASE_URL        = "postgresql://litellm:${var.litellm_db_password}@postgresql.infra.svc.cluster.local:5432/litellm"
    username            = "litellm"
    password            = var.litellm_db_password
    masterkey           = var.litellm_master_key
  }
}

# ── LiteLLM ConfigMap (model routing config) ─────────────────
resource "kubernetes_config_map" "litellm_config" {
  metadata {
    name      = "litellm-config"
    namespace = kubernetes_namespace.am_ai.metadata[0].name
  }
  data = {
    "litellm_config.yaml" = templatefile("${path.module}/litellm_config.yaml.tpl", {
      langfuse_host       = var.langfuse_host
    })
  }
}

# ── LiteLLM Helm Release ─────────────────────────────────────
resource "helm_release" "litellm" {
  name       = "litellm"
  chart      = "oci://ghcr.io/berriai/litellm-helm"
  version    = "1.88.1"
  namespace  = kubernetes_namespace.am_ai.metadata[0].name

  values = [file("${path.module}/../../../helm/ai-gateway/litellm-values.yaml")]

  set {
    name  = "environmentSecrets[0]"
    value = kubernetes_secret.litellm_secrets.metadata[0].name
  }

  depends_on = [kubernetes_namespace.am_ai, kubernetes_config_map.litellm_config]
}

# ── Langfuse Helm Release ────────────────────────────────────
resource "helm_release" "langfuse" {
  name       = "langfuse"
  repository = "https://langfuse.github.io/langfuse-k8s"
  chart      = "langfuse"
  version    = "1.0.0"
  namespace  = kubernetes_namespace.am_ai.metadata[0].name

  values = [file("${path.module}/../../../helm/ai-gateway/langfuse-values.yaml")]

  set_sensitive {
    name  = "langfuse.nextauth.secret.value"
    value = var.langfuse_nextauth_secret
  }

  # External Postgres: pass all individual fields so the chart builds DATABASE_URL correctly
  set {
    name  = "postgresql.host"
    value = "postgresql.infra.svc.cluster.local"
  }
  set {
    name  = "postgresql.port"
    value = "5432"
  }
  set {
    name  = "postgresql.auth.username"
    value = "langfuse"
  }
  set_sensitive {
    name  = "postgresql.auth.password"
    value = var.langfuse_db_password
  }
  set {
    name  = "postgresql.auth.database"
    value = "langfuse"
  }
  # directUrl is used for migrations only — keep it for prisma migrate
  set_sensitive {
    name  = "postgresql.directUrl"
    value = "postgresql://langfuse:${var.langfuse_db_password}@postgresql.infra.svc.cluster.local:5432/langfuse"
  }

  depends_on = [kubernetes_namespace.am_ai]
}

# ── Qdrant StatefulSet (via Helm) ────────────────────────────
resource "helm_release" "qdrant" {
  name       = "qdrant"
  repository = "https://qdrant.github.io/qdrant-helm"
  chart      = "qdrant"
  version    = "0.9.1"
  namespace  = kubernetes_namespace.am_ai.metadata[0].name

  values = [file("${path.module}/../../../helm/ai-gateway/qdrant-values.yaml")]

  depends_on = [kubernetes_namespace.am_ai]
}

# ── MLflow Helm Release ──────────────────────────────────────
resource "helm_release" "mlflow" {
  name       = "mlflow"
  repository = "https://community-charts.github.io/helm-charts"
  chart      = "mlflow"
  version    = "0.7.19"
  namespace  = kubernetes_namespace.am_ai.metadata[0].name

  values = [file("${path.module}/../../../helm/ai-gateway/mlflow-values.yaml")]

  depends_on = [kubernetes_namespace.am_ai]
}

