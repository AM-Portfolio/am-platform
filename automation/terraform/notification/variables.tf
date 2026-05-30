variable "kubeconfig_path" {
  type        = string
  description = "Path to kubeconfig for the Kubernetes cluster"
}

variable "mongo_admin_user" {
  type        = string
  description = "MongoDB admin username"
  default     = "admin"
}

variable "mongo_admin_password" {
  type        = string
  description = "MongoDB admin password"
  sensitive   = true
}

variable "notification_db_name" {
  type        = string
  description = "Logical database for am-notification lean layer"
  default     = "notification"
}

variable "notification_db_user" {
  type        = string
  description = "Scoped MongoDB user for am-notification"
  default     = "am_notification_user"
}

variable "notification_db_password" {
  type        = string
  description = "Password for am_notification_user"
  sensitive   = true
}

variable "novu_db_name" {
  type        = string
  description = "Logical database for Novu on shared Mongo cluster"
  default     = "novu"
}

variable "novu_db_user" {
  type        = string
  description = "Scoped MongoDB user for Novu"
  default     = "novu_user"
}

variable "novu_db_password" {
  type        = string
  description = "Password for novu_user"
  sensitive   = true
}

variable "novu_api_url" {
  type        = string
  description = "Novu API base URL for workflow seed script"
  default     = "https://novu-api.munish.org"
}

variable "novu_api_key" {
  type        = string
  description = "Novu Production API key (runtime triggers)"
  sensitive   = true
  default     = ""
}

variable "novu_dev_api_key" {
  type        = string
  description = "Novu Development API key for workflow seed script"
  sensitive   = true
  default     = ""
}

variable "novu_admin_email" {
  type        = string
  description = "Novu dashboard admin email for promoting workflows to Production"
  default     = ""
}

variable "novu_admin_password" {
  type        = string
  description = "Novu dashboard admin password"
  sensitive   = true
  default     = ""
}

variable "novu_dev_environment_id" {
  type        = string
  description = "Novu Development environment Mongo _id"
  default     = ""
}

variable "workflows_json_path" {
  type        = string
  description = "Path to novu-workflows.json"
  default     = ""
}
