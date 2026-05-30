variable "keycloak_url" {
  type        = string
  description = "The base URL of the Keycloak instance (must include /auth)"
  default     = "https://auth.munish.org/auth"
}

variable "keycloak_admin_username" {
  type        = string
  description = "Username for the Keycloak Master admin console"
  default     = "admin"
}

variable "keycloak_admin_password" {
  type        = string
  description = "Password for the Keycloak Master admin console"
  default     = "adminpassword123"
  sensitive   = true
}

variable "realm_name" {
  type        = string
  description = "The name of the OIDC realm to manage"
  default     = "am-realm"
}

variable "google_client_id" {
  type        = string
  description = "Google OAuth client ID used by Keycloak Google IdP"
  sensitive   = true
}

variable "google_client_secret" {
  type        = string
  description = "Google OAuth client secret used by Keycloak Google IdP"
  sensitive   = true
}

variable "kubeconfig_path" {
  type        = string
  description = "The path to the kubeconfig file for the Kubernetes cluster"
  default     = "../../../VPS/kubeconfig.vps"
}

# PostgreSQL connection configurations (for billing database provisioning)
variable "postgres_host" {
  type        = string
  description = "The hostname/service of the shared PostgreSQL instance"
  default     = "postgresql.infra.svc.cluster.local"
}

variable "postgres_user" {
  type        = string
  description = "The admin username for PostgreSQL connection"
  default     = "postgres"
}

variable "postgres_password" {
  type        = string
  description = "The admin password for PostgreSQL connection"
  sensitive   = true
}

variable "postgres_db" {
  type        = string
  description = "The administrative database to connect to (e.g. portfolio or postgres)"
  default     = "portfolio"
}

variable "subscription_db_name" {
  type        = string
  description = "The logical database name to create for the subscription service"
  default     = "subscription"
}

variable "subscription_db_user" {
  type        = string
  description = "The database user to create for the subscription service"
  default     = "am_subscription_user"
}

variable "subscription_db_password" {
  type        = string
  description = "The database password to set for the subscription service user"
  sensitive   = true
}
