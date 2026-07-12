terraform {
  required_providers {
    keycloak = {
      source  = "mrparkers/keycloak"
      version = ">= 4.4.0"
    }
  }
}

# =========================================================
# 1. REALM
# =========================================================

resource "keycloak_realm" "am_realm" {
  realm        = var.realm_name
  enabled      = true
  display_name = "AM Ecosystem Realm"

  # Password & Login Policy
  reset_password_allowed         = true
  registration_allowed           = true
  registration_email_as_username = true
  login_with_email_allowed       = true
  duplicate_emails_allowed       = false
  verify_email                   = false # Enable in production

  # Session TTLs (recommended baseline)
  sso_session_idle_timeout = "30m"
  sso_session_max_lifespan = "10h"
  access_token_lifespan    = "24h"

  # Password policy: min length + mixed case + digits
  password_policy = "length(8) and lowerCase(1) and upperCase(1) and digits(1)"

  # Brute-force protection
  security_defenses {
    brute_force_detection {
      permanent_lockout                = false
      max_login_failures               = 10
      wait_increment_seconds           = 60
      quick_login_check_milli_seconds  = 1000
      minimum_quick_login_wait_seconds = 60
      max_failure_wait_seconds         = 900
    }
  }
}

# =========================================================
# 2. REALM-LEVEL ROLES
# =========================================================

resource "keycloak_role" "role_user" {
  realm_id    = keycloak_realm.am_realm.id
  name        = "user"
  description = "Standard portal user - can login to AM apps"
}

resource "keycloak_role" "role_admin" {
  realm_id    = keycloak_realm.am_realm.id
  name        = "admin"
  description = "AM ecosystem administrator"
}

resource "keycloak_role" "role_viewer" {
  realm_id    = keycloak_realm.am_realm.id
  name        = "viewer"
  description = "Read-only access across AM apps"
}

resource "keycloak_role" "role_service" {
  realm_id    = keycloak_realm.am_realm.id
  name        = "service"
  description = "Internal microservice account - not for human users"
}

# =========================================================
# 3. DEFAULT ROLES (auto-assigned to every new user)
# =========================================================

resource "keycloak_default_roles" "default_roles" {
  realm_id      = keycloak_realm.am_realm.id
  default_roles = ["user"]

  depends_on = [keycloak_role.role_user]
}

# =========================================================
# 4. CLIENTS
# =========================================================

# ---------------------------------------------------------
# 4a. PUBLIC CLIENT — AM Modern UI (am.munish.org / asrax.in)
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_web_client" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-web-client"
  name        = "AM Investment Portal (Web UI)"
  description = "Public OIDC client for browser-based web apps"
  enabled     = true

  access_type                  = "PUBLIC"
  standard_flow_enabled        = true  # Auth Code Flow
  implicit_flow_enabled        = false
  direct_access_grants_enabled = false
  service_accounts_enabled     = false

  valid_redirect_uris = [
    "http://localhost:9000/*",
    "https://am.munish.org/*",
    "https://am.asrax.in/*",
    "https://am-dev.asrax.in/*",
  ]

  web_origins = [
    "http://localhost:9000",
    "https://am.munish.org",
    "https://am.asrax.in",
    "https://am-dev.asrax.in",
  ]

  login_theme = ""
}

# ---------------------------------------------------------
# 4b. PUBLIC CLIENT — AM Diagnostic / Dev UI (port 9001)
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_diagnostic_client" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-diagnostic-client"
  name        = "AM Diagnostic & Testing UI"
  description = "Public OIDC client for the internal diagnostic dashboard"
  enabled     = true

  access_type                  = "PUBLIC"
  standard_flow_enabled        = true
  implicit_flow_enabled        = false
  direct_access_grants_enabled = false
  service_accounts_enabled     = false

  valid_redirect_uris = [
    "http://localhost:9001/*",
    "http://am.munish.org/diagnostic/*",
  ]

  web_origins = [
    "http://localhost:9001",
    "http://am.munish.org",
  ]
}

# ---------------------------------------------------------
# 4c. CONFIDENTIAL CLIENT — AM Identity Service (am-identity)
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_identity_service" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-identity-service"
  name        = "AM Identity Backend Service"
  description = "Confidential client for the am-identity FastAPI microservice"
  enabled     = true

  access_type                  = "CONFIDENTIAL"
  standard_flow_enabled        = false
  implicit_flow_enabled        = false
  direct_access_grants_enabled = true
  service_accounts_enabled     = true
}

resource "keycloak_openid_client_service_account_realm_role" "identity_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_identity_service.service_account_user_id
  role                    = keycloak_role.role_service.name

  depends_on = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4d. CONFIDENTIAL CLIENT — AM API Gateway (am-gateway)
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_gateway_client" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-gateway-client"
  name        = "AM API Gateway"
  description = "Confidential client for the API gateway token introspection"
  enabled     = true

  access_type                  = "CONFIDENTIAL"
  standard_flow_enabled        = false
  implicit_flow_enabled        = false
  direct_access_grants_enabled = false
  service_accounts_enabled     = true
}

resource "keycloak_openid_client_service_account_realm_role" "gateway_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_gateway_client.service_account_user_id
  role                    = keycloak_role.role_service.name

  depends_on = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4e. CONFIDENTIAL CLIENT — AM Gateway Streaming Service
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_gateway_streaming_service" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-gateway-streaming-service"
  name        = "AM Gateway Streaming Service"
  description = "Confidential client for gateway streaming services"
  enabled     = true

  access_type                  = "CONFIDENTIAL"
  standard_flow_enabled        = false
  implicit_flow_enabled        = false
  direct_access_grants_enabled = false
  service_accounts_enabled     = true
}

resource "keycloak_openid_client_service_account_realm_role" "gateway_streaming_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_gateway_streaming_service.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4f. CONFIDENTIAL CLIENT — AM MCP Service
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_mcp_service" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-mcp-service"
  name        = "AM MCP Service"
  description = "Confidential client for MCP services"
  enabled     = true

  access_type                  = "CONFIDENTIAL"
  standard_flow_enabled        = false
  implicit_flow_enabled        = false
  direct_access_grants_enabled = false
  service_accounts_enabled     = true
}

resource "keycloak_openid_client_service_account_realm_role" "mcp_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_mcp_service.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4g. CONFIDENTIAL CLIENT — AM Fin Agent Service
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_fin_agent_service" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-fin-agent-service"
  name        = "AM Fin Agent Service"
  description = "Confidential client for fin-agent services"
  enabled     = true

  access_type                  = "CONFIDENTIAL"
  standard_flow_enabled        = false
  implicit_flow_enabled        = false
  direct_access_grants_enabled = false
  service_accounts_enabled     = true
}

resource "keycloak_openid_client_service_account_realm_role" "fin_agent_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_fin_agent_service.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4h. CONFIDENTIAL CLIENT — AM Doc Intelligence Service
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_doc_intelligence_service" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-doc-intelligence-service"
  name        = "AM Doc Intelligence Service"
  description = "Confidential client for document intelligence services"
  enabled     = true

  access_type                  = "CONFIDENTIAL"
  standard_flow_enabled        = false
  implicit_flow_enabled        = false
  direct_access_grants_enabled = false
  service_accounts_enabled     = true
}

resource "keycloak_openid_client_service_account_realm_role" "doc_intelligence_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_doc_intelligence_service.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4i. CONFIDENTIAL CLIENT — AM Analysis Service
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_analysis_service" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-analysis-service"
  name        = "AM Analysis Service"
  description = "Internal service client for analysis microservice"
  enabled     = true

  access_type                  = "CONFIDENTIAL"
  standard_flow_enabled        = false
  implicit_flow_enabled        = false
  direct_access_grants_enabled = false
  service_accounts_enabled     = true
}

resource "keycloak_openid_client_service_account_realm_role" "analysis_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_analysis_service.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4j. CONFIDENTIAL CLIENT — AM Market Data Service
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_market_service" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-market-service"
  name        = "AM Market Data Service"
  description = "Internal service client for market data microservice"
  enabled     = true

  access_type                  = "CONFIDENTIAL"
  standard_flow_enabled        = false
  service_accounts_enabled     = true
}

resource "keycloak_openid_client_service_account_realm_role" "market_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_market_service.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4k. CONFIDENTIAL CLIENT — AM Market Data Dedicated Service
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_market_data_service" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-market-data-service"
  name        = "AM Market Data Dedicated Service"
  description = "Internal service client for dedicated market-data module"
  enabled     = true

  access_type                  = "CONFIDENTIAL"
  standard_flow_enabled        = false
  implicit_flow_enabled        = false
  direct_access_grants_enabled = false
  service_accounts_enabled     = true
}

resource "keycloak_openid_client_service_account_realm_role" "market_data_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_market_data_service.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4l. CONFIDENTIAL CLIENT — AM Market Parser Service
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_market_parser_service" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-market-parser-service"
  name        = "AM Market Parser Service"
  description = "Internal service client for market parser module"
  enabled     = true

  access_type                  = "CONFIDENTIAL"
  standard_flow_enabled        = false
  implicit_flow_enabled        = false
  direct_access_grants_enabled = false
  service_accounts_enabled     = true
}

resource "keycloak_openid_client_service_account_realm_role" "market_parser_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_market_parser_service.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4m. CONFIDENTIAL CLIENT — AM Portfolio Service
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_portfolio_service" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-portfolio-service"
  name        = "AM Portfolio Service"
  description = "Internal service client for portfolio microservice"
  enabled     = true

  access_type              = "CONFIDENTIAL"
  standard_flow_enabled    = false
  service_accounts_enabled = true
}

resource "keycloak_openid_client_service_account_realm_role" "portfolio_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_portfolio_service.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4n. CONFIDENTIAL CLIENT — AM Trade Service
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_trade_service" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-trade-service"
  name        = "AM Trade Management Service"
  description = "Internal service client for trade management microservice"
  enabled     = true

  access_type              = "CONFIDENTIAL"
  standard_flow_enabled    = false
  service_accounts_enabled = true
}

resource "keycloak_openid_client_service_account_realm_role" "trade_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_trade_service.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4o. CONFIDENTIAL CLIENT — AM Subscription Service
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_subscription_service" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-subscription-service"
  name        = "AM Subscription Service"
  description = "Internal service client for subscription lifecycle service"
  enabled     = true

  access_type              = "CONFIDENTIAL"
  standard_flow_enabled    = false
  service_accounts_enabled = true
}

resource "keycloak_openid_client_service_account_realm_role" "subscription_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_subscription_service.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4p. CONFIDENTIAL CLIENT — AM Notification Service
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_notification_service" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-notification-service"
  name        = "AM Notification Service"
  description = "Internal service client for notification delivery service"
  enabled     = true

  access_type              = "CONFIDENTIAL"
  standard_flow_enabled    = false
  service_accounts_enabled = true
}

resource "keycloak_openid_client_service_account_realm_role" "notification_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_notification_service.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4j. PUBLIC CLIENT — AM Android App
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_android_client" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-android-client"
  name        = "AM Android App"
  description = "Public OIDC client for the AM Android mobile application"
  enabled     = true

  access_type                  = "PUBLIC"
  standard_flow_enabled        = true  # Auth Code + PKCE
  implicit_flow_enabled        = false
  direct_access_grants_enabled = false
  service_accounts_enabled     = false

  valid_redirect_uris = [
    "com.am.portfolio://*",            # Android deep-link scheme
    "com.asrax.portfolio://*",         # Asrax brand deep-link
    "http://localhost:9000/*",          # Dev/emulator fallback
  ]

  web_origins = ["+"]
}

# ---------------------------------------------------------
# 4k. PUBLIC CLIENT — AM iOS App
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_ios_client" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-ios-client"
  name        = "AM iOS App"
  description = "Public OIDC client for the AM iOS mobile application"
  enabled     = true

  access_type                  = "PUBLIC"
  standard_flow_enabled        = true  # Auth Code + PKCE
  implicit_flow_enabled        = false
  direct_access_grants_enabled = false
  service_accounts_enabled     = false

  valid_redirect_uris = [
    "com.am.portfolio://*",            # iOS custom URL scheme
    "com.asrax.portfolio://*",
    "https://am.munish.org/app/callback", # Universal link fallback
    "https://am.asrax.in/app/callback",
    "http://localhost:9000/*",          # Dev/simulator fallback
  ]

  web_origins = ["+"]
}

# ---------------------------------------------------------
# 4r. CONFIDENTIAL CLIENT — am-lago-client
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_lago_client" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-lago-client"
  name        = "AM Lago Client"
  description = "Confidential client for Lago integrations"
  enabled     = true

  access_type              = "CONFIDENTIAL"
  standard_flow_enabled    = false
  service_accounts_enabled = true
}

resource "keycloak_openid_client_service_account_realm_role" "lago_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_lago_client.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4s. CONFIDENTIAL CLIENT — am-analysis-client
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_analysis_client" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-analysis-client"
  name        = "AM Analysis Client"
  description = "Confidential client for Analysis microservice"
  enabled     = true

  access_type              = "CONFIDENTIAL"
  standard_flow_enabled    = false
  service_accounts_enabled = true
}

resource "keycloak_openid_client_service_account_realm_role" "analysis_client_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_analysis_client.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4t. CONFIDENTIAL CLIENT — am-market-client
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_market_client" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-market-client"
  name        = "AM Market Client"
  description = "Confidential client for Market Data microservice"
  enabled     = true

  access_type              = "CONFIDENTIAL"
  standard_flow_enabled    = false
  service_accounts_enabled = true
}

resource "keycloak_openid_client_service_account_realm_role" "market_client_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_market_client.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4u. CONFIDENTIAL CLIENT — am-market-data-client
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_market_data_client" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-market-data-client"
  name        = "AM Market Data Client"
  description = "Confidential client for Market Data microservice"
  enabled     = true

  access_type              = "CONFIDENTIAL"
  standard_flow_enabled    = false
  service_accounts_enabled = true
}

resource "keycloak_openid_client_service_account_realm_role" "market_data_client_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_market_data_client.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4v. CONFIDENTIAL CLIENT — am-parser-client
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_parser_client" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-parser-client"
  name        = "AM Parser Client"
  description = "Confidential client for Parser microservice"
  enabled     = true

  access_type              = "CONFIDENTIAL"
  standard_flow_enabled    = false
  service_accounts_enabled = true
}

resource "keycloak_openid_client_service_account_realm_role" "parser_client_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_parser_client.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4w. CONFIDENTIAL CLIENT — am-doc-a-client
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_doc_a_client" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-doc-a-client"
  name        = "AM Doc A Client"
  description = "Confidential client for Document A integration"
  enabled     = true

  access_type              = "CONFIDENTIAL"
  standard_flow_enabled    = false
  service_accounts_enabled = true
}

resource "keycloak_openid_client_service_account_realm_role" "doc_a_client_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_doc_a_client.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4x. CONFIDENTIAL CLIENT — am-doc-b-client
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_doc_b_client" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-doc-b-client"
  name        = "AM Doc B Client"
  description = "Confidential client for Document B integration"
  enabled     = true

  access_type              = "CONFIDENTIAL"
  standard_flow_enabled    = false
  service_accounts_enabled = true
}

resource "keycloak_openid_client_service_account_realm_role" "doc_b_client_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_doc_b_client.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4y. CONFIDENTIAL CLIENT — am-doc-c-client
# ---------------------------------------------------------
resource "keycloak_openid_client" "am_doc_c_client" {
  realm_id    = keycloak_realm.am_realm.id
  client_id   = "am-doc-c-client"
  name        = "AM Doc C Client"
  description = "Confidential client for Document C integration"
  enabled     = true

  access_type              = "CONFIDENTIAL"
  standard_flow_enabled    = false
  service_accounts_enabled = true
}

resource "keycloak_openid_client_service_account_realm_role" "doc_c_client_svc_role" {
  realm_id                = keycloak_realm.am_realm.id
  service_account_user_id = keycloak_openid_client.am_doc_c_client.service_account_user_id
  role                    = keycloak_role.role_service.name
  depends_on              = [keycloak_role.role_service]
}

# ---------------------------------------------------------
# 4q. GOOGLE IDENTITY PROVIDER (Enterprise SSO onboarding)
# ---------------------------------------------------------
resource "keycloak_oidc_google_identity_provider" "google_idp" {
  realm                 = keycloak_realm.am_realm.id
  enabled               = true
  store_token           = false
  trust_email           = true

  client_id     = var.google_client_id
  client_secret = var.google_client_secret

  default_scopes               = "openid profile email"
  first_broker_login_flow_alias = "first broker login"
}

# =========================================================
# 5. TOKEN CLAIM MAPPERS
# =========================================================

# --- WEB CLIENT ---
resource "keycloak_openid_user_realm_role_protocol_mapper" "web_realm_roles_mapper" {
  realm_id   = keycloak_realm.am_realm.id
  client_id  = keycloak_openid_client.am_web_client.id
  name       = "realm-roles-mapper"
  claim_name = "roles"

  multivalued         = true
  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

resource "keycloak_openid_hardcoded_claim_protocol_mapper" "web_platform_mapper" {
  realm_id         = keycloak_realm.am_realm.id
  client_id        = keycloak_openid_client.am_web_client.id
  name             = "platform-mapper"
  claim_name       = "platform"
  claim_value      = "web"
  claim_value_type = "String"

  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

# --- DIAGNOSTIC CLIENT ---
resource "keycloak_openid_user_realm_role_protocol_mapper" "diagnostic_realm_roles_mapper" {
  realm_id   = keycloak_realm.am_realm.id
  client_id  = keycloak_openid_client.am_diagnostic_client.id
  name       = "realm-roles-mapper"
  claim_name = "roles"

  multivalued         = true
  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

resource "keycloak_openid_hardcoded_claim_protocol_mapper" "diagnostic_platform_mapper" {
  realm_id         = keycloak_realm.am_realm.id
  client_id        = keycloak_openid_client.am_diagnostic_client.id
  name             = "platform-mapper"
  claim_name       = "platform"
  claim_value      = "web"
  claim_value_type = "String"

  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

# --- ANDROID CLIENT ---
resource "keycloak_openid_user_realm_role_protocol_mapper" "android_realm_roles_mapper" {
  realm_id   = keycloak_realm.am_realm.id
  client_id  = keycloak_openid_client.am_android_client.id
  name       = "realm-roles-mapper"
  claim_name = "roles"

  multivalued         = true
  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

resource "keycloak_openid_hardcoded_claim_protocol_mapper" "android_platform_mapper" {
  realm_id         = keycloak_realm.am_realm.id
  client_id        = keycloak_openid_client.am_android_client.id
  name             = "platform-mapper"
  claim_name       = "platform"
  claim_value      = "android"
  claim_value_type = "String"

  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

# --- iOS CLIENT ---
resource "keycloak_openid_user_realm_role_protocol_mapper" "ios_realm_roles_mapper" {
  realm_id   = keycloak_realm.am_realm.id
  client_id  = keycloak_openid_client.am_ios_client.id
  name       = "realm-roles-mapper"
  claim_name = "roles"

  multivalued         = true
  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

resource "keycloak_openid_hardcoded_claim_protocol_mapper" "ios_platform_mapper" {
  realm_id         = keycloak_realm.am_realm.id
  client_id        = keycloak_openid_client.am_ios_client.id
  name             = "platform-mapper"
  claim_name       = "platform"
  claim_value      = "ios"
  claim_value_type = "String"

  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

# =========================================================
# 6. CLIENT SCOPES
# =========================================================

resource "keycloak_openid_client_scope" "am_user_scope" {
  realm_id    = keycloak_realm.am_realm.id
  name        = "am-user"
  description = "Standard AM user claims: profile, email, roles, and platform"
}

# =========================================================
# 7. USER ID PROTOCOL MAPPERS
# =========================================================

resource "keycloak_openid_user_property_protocol_mapper" "web_userid_mapper" {
  realm_id         = keycloak_realm.am_realm.id
  client_id        = keycloak_openid_client.am_web_client.id
  name             = "userId-mapper"
  user_property    = "id"
  claim_name       = "userId"
  claim_value_type = "String"

  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

resource "keycloak_openid_user_property_protocol_mapper" "diagnostic_userid_mapper" {
  realm_id         = keycloak_realm.am_realm.id
  client_id        = keycloak_openid_client.am_diagnostic_client.id
  name             = "userId-mapper"
  user_property    = "id"
  claim_name       = "userId"
  claim_value_type = "String"

  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

resource "keycloak_openid_user_property_protocol_mapper" "identity_service_userid_mapper" {
  realm_id         = keycloak_realm.am_realm.id
  client_id        = keycloak_openid_client.am_identity_service.id
  name             = "userId-mapper"
  user_property    = "id"
  claim_name       = "userId"
  claim_value_type = "String"

  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

resource "keycloak_openid_user_property_protocol_mapper" "android_userid_mapper" {
  realm_id         = keycloak_realm.am_realm.id
  client_id        = keycloak_openid_client.am_android_client.id
  name             = "userId-mapper"
  user_property    = "id"
  claim_name       = "userId"
  claim_value_type = "String"

  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

resource "keycloak_openid_user_property_protocol_mapper" "ios_userid_mapper" {
  realm_id         = keycloak_realm.am_realm.id
  client_id        = keycloak_openid_client.am_ios_client.id
  name             = "userId-mapper"
  user_property    = "id"
  claim_name       = "userId"
  claim_value_type = "String"

  add_to_id_token     = true
  add_to_access_token = true
  add_to_userinfo     = true
}

