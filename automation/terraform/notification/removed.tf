# Novu Helm release and namespace are managed by automation/helm/deploy-novu.ps1.
# Drop Terraform management without destroying cluster resources if ever migrated.

# removed {
#   from = helm_release.novu
#   lifecycle {
#     destroy = false
#   }
# }
