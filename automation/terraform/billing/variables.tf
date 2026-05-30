variable "kubeconfig_path" {
  type        = string
  description = "The path to the kubeconfig file for the Kubernetes cluster"
}

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
