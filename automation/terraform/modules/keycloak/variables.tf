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
