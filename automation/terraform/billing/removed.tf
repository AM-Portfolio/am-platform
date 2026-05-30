# Lago Helm release and namespace are managed by automation/helm/deploy-lago.ps1.
# These blocks drop Terraform management without destroying cluster resources.

removed {
  from = helm_release.lago

  lifecycle {
    destroy = false
  }
}

removed {
  from = kubernetes_namespace.billing

  lifecycle {
    destroy = false
  }
}
