variable "keycloak_url" {
  type        = string
  description = "The base URL of the Keycloak instance (must include /auth)"
}

variable "keycloak_admin_username" {
  type        = string
  description = "Username for the Keycloak Master admin console"
}

variable "keycloak_admin_password" {
  type        = string
  description = "Password for the Keycloak Master admin console"
  sensitive   = true
}

variable "realm_name" {
  type        = string
  description = "The name of the OIDC realm to manage"
}

variable "environment" {
  type        = string
  description = "Deployment environment: dev | preprod | prod"
  validation {
    condition     = contains(["dev", "preprod", "prod"], var.environment)
    error_message = "environment must be one of: dev, preprod, prod."
  }
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

variable "valid_redirect_uris" {
  type        = list(string)
  description = "Allowed redirect URIs for the AM Web public client — set per environment"
  default     = []
}

variable "web_origins" {
  type        = list(string)
  description = "Allowed web origins (CORS) for the AM Web public client — set per environment"
  default     = []
}

variable "verify_email" {
  type        = bool
  description = "Whether to require email verification on new registrations (should be true for prod)"
  default     = false
}

# Zoho (or other) SMTP for Keycloak realm email (verify / reset / required actions).
# Leave smtp_host empty to skip configuring smtp_server on the realm.
variable "smtp_host" {
  type        = string
  description = "SMTP host (e.g. smtppro.zoho.in)"
  default     = ""
}

variable "smtp_port" {
  type        = string
  description = "SMTP port as string (Keycloak provider expects string)"
  default     = "465"
}

variable "smtp_from" {
  type        = string
  description = "From email address (must match authenticated mailbox/alias)"
  default     = ""
}

variable "smtp_from_display_name" {
  type        = string
  description = "From display name shown in clients"
  default     = "Asrax Accounts"
}

variable "smtp_user" {
  type        = string
  description = "SMTP auth username (full email)"
  default     = ""
  sensitive   = true
}

variable "smtp_password" {
  type        = string
  description = "SMTP auth password (Zoho app password)"
  default     = ""
  sensitive   = true
}

variable "smtp_ssl" {
  type        = bool
  description = "Use SSL (typical for port 465)"
  default     = true
}

variable "smtp_starttls" {
  type        = bool
  description = "Use STARTTLS (typical for port 587)"
  default     = false
}
