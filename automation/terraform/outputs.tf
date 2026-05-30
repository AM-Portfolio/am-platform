# Realm & OIDC Server Info
output "realm_id" {
  value = module.keycloak.realm_id
}

output "realm_name" {
  value = module.keycloak.realm_name
}

output "auth_server_url" {
  value       = var.keycloak_url
  description = "The base Keycloak auth URL"
}

output "oidc_discovery_url" {
  value       = "${var.keycloak_url}/realms/${var.realm_name}/.well-known/openid-configuration"
  description = "OIDC discovery URL"
}

# Public OIDC Clients
output "web_client_id" {
  value = module.keycloak.web_client_id
}

output "diagnostic_client_id" {
  value = module.keycloak.diagnostic_client_id
}

output "android_client_id" {
  value = module.keycloak.android_client_id
}

output "ios_client_id" {
  value = module.keycloak.ios_client_id
}

# Confidential OIDC Clients
output "identity_service_client_id" {
  value = module.keycloak.identity_service_client_id
}

output "identity_service_client_secret" {
  value     = module.keycloak.identity_service_client_secret
  sensitive = true
}

output "gateway_client_id" {
  value = module.keycloak.gateway_client_id
}

output "gateway_client_secret" {
  value     = module.keycloak.gateway_client_secret
  sensitive = true
}

output "gateway_streaming_client_id" {
  value = module.keycloak.gateway_streaming_client_id
}

output "gateway_streaming_client_secret" {
  value     = module.keycloak.gateway_streaming_client_secret
  sensitive = true
}

output "mcp_client_id" {
  value = module.keycloak.mcp_client_id
}

output "mcp_client_secret" {
  value     = module.keycloak.mcp_client_secret
  sensitive = true
}

output "fin_agent_client_id" {
  value = module.keycloak.fin_agent_client_id
}

output "fin_agent_client_secret" {
  value     = module.keycloak.fin_agent_client_secret
  sensitive = true
}

output "doc_intelligence_client_id" {
  value = module.keycloak.doc_intelligence_client_id
}

output "doc_intelligence_client_secret" {
  value     = module.keycloak.doc_intelligence_client_secret
  sensitive = true
}

output "analysis_service_client_id" {
  value = module.keycloak.analysis_service_client_id
}

output "analysis_service_client_secret" {
  value     = module.keycloak.analysis_service_client_secret
  sensitive = true
}

output "market_service_client_id" {
  value = module.keycloak.market_service_client_id
}

output "market_service_client_secret" {
  value     = module.keycloak.market_service_client_secret
  sensitive = true
}

output "market_data_service_client_id" {
  value = module.keycloak.market_data_service_client_id
}

output "market_data_service_client_secret" {
  value     = module.keycloak.market_data_service_client_secret
  sensitive = true
}

output "market_parser_service_client_id" {
  value = module.keycloak.market_parser_service_client_id
}

output "market_parser_service_client_secret" {
  value     = module.keycloak.market_parser_service_client_secret
  sensitive = true
}

output "portfolio_service_client_id" {
  value = module.keycloak.portfolio_service_client_id
}

output "portfolio_service_client_secret" {
  value     = module.keycloak.portfolio_service_client_secret
  sensitive = true
}

output "trade_service_client_id" {
  value = module.keycloak.trade_service_client_id
}

output "trade_service_client_secret" {
  value     = module.keycloak.trade_service_client_secret
  sensitive = true
}

output "subscription_service_client_id" {
  value = module.keycloak.subscription_service_client_id
}

output "subscription_service_client_secret" {
  value     = module.keycloak.subscription_service_client_secret
  sensitive = true
}

output "notification_service_client_id" {
  value = module.keycloak.notification_service_client_id
}

output "notification_service_client_secret" {
  value     = module.keycloak.notification_service_client_secret
  sensitive = true
}

# New OIDC clients
output "lago_client_id" {
  value = module.keycloak.lago_client_id
}

output "lago_client_secret" {
  value     = module.keycloak.lago_client_secret
  sensitive = true
}

output "analysis_client_id" {
  value = module.keycloak.analysis_client_id
}

output "analysis_client_secret" {
  value     = module.keycloak.analysis_client_secret
  sensitive = true
}

output "market_client_id" {
  value = module.keycloak.market_client_id
}

output "market_client_secret" {
  value     = module.keycloak.market_client_secret
  sensitive = true
}

output "market_data_client_id" {
  value = module.keycloak.market_data_client_id
}

output "market_data_client_secret" {
  value     = module.keycloak.market_data_client_secret
  sensitive = true
}

output "parser_client_id" {
  value = module.keycloak.parser_client_id
}

output "parser_client_secret" {
  value     = module.keycloak.parser_client_secret
  sensitive = true
}

output "doc_a_client_id" {
  value = module.keycloak.doc_a_client_id
}

output "doc_a_client_secret" {
  value     = module.keycloak.doc_a_client_secret
  sensitive = true
}

output "doc_b_client_id" {
  value = module.keycloak.doc_b_client_id
}

output "doc_b_client_secret" {
  value     = module.keycloak.doc_b_client_secret
  sensitive = true
}

output "doc_c_client_id" {
  value = module.keycloak.doc_c_client_id
}

output "doc_c_client_secret" {
  value     = module.keycloak.doc_c_client_secret
  sensitive = true
}

# Database Outputs
output "subscription_db_name" {
  value = module.billing.subscription_db_name
}

output "subscription_db_user" {
  value = module.billing.subscription_db_user
}

output "subscription_db_password" {
  value     = module.billing.subscription_db_password
  sensitive = true
}

# Billing Services
output "lago_api_service" {
  value = module.billing.lago_api_service
}

output "lago_front_service" {
  value = module.billing.lago_front_service
}

output "billing_namespace" {
  value = module.billing.billing_namespace
}
