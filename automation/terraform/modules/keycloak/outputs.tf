output "realm_id" {
  value = keycloak_realm.am_realm.id
}

output "realm_name" {
  value = keycloak_realm.am_realm.realm
}

# Public Clients
output "web_client_id" {
  value = keycloak_openid_client.am_web_client.client_id
}

output "diagnostic_client_id" {
  value = keycloak_openid_client.am_diagnostic_client.client_id
}

output "android_client_id" {
  value = keycloak_openid_client.am_android_client.client_id
}

output "ios_client_id" {
  value = keycloak_openid_client.am_ios_client.client_id
}

# Confidential Clients
output "identity_service_client_id" {
  value = keycloak_openid_client.am_identity_service.client_id
}

output "identity_service_client_secret" {
  value     = keycloak_openid_client.am_identity_service.client_secret
  sensitive = true
}

output "gateway_client_id" {
  value = keycloak_openid_client.am_gateway_client.client_id
}

output "gateway_client_secret" {
  value     = keycloak_openid_client.am_gateway_client.client_secret
  sensitive = true
}

output "gateway_streaming_client_id" {
  value = keycloak_openid_client.am_gateway_streaming_service.client_id
}

output "gateway_streaming_client_secret" {
  value     = keycloak_openid_client.am_gateway_streaming_service.client_secret
  sensitive = true
}

output "mcp_client_id" {
  value = keycloak_openid_client.am_mcp_service.client_id
}

output "mcp_client_secret" {
  value     = keycloak_openid_client.am_mcp_service.client_secret
  sensitive = true
}

output "fin_agent_client_id" {
  value = keycloak_openid_client.am_fin_agent_service.client_id
}

output "fin_agent_client_secret" {
  value     = keycloak_openid_client.am_fin_agent_service.client_secret
  sensitive = true
}

output "doc_intelligence_client_id" {
  value = keycloak_openid_client.am_doc_intelligence_service.client_id
}

output "doc_intelligence_client_secret" {
  value     = keycloak_openid_client.am_doc_intelligence_service.client_secret
  sensitive = true
}

output "analysis_service_client_id" {
  value = keycloak_openid_client.am_analysis_service.client_id
}

output "analysis_service_client_secret" {
  value     = keycloak_openid_client.am_analysis_service.client_secret
  sensitive = true
}

output "market_service_client_id" {
  value = keycloak_openid_client.am_market_service.client_id
}

output "market_service_client_secret" {
  value     = keycloak_openid_client.am_market_service.client_secret
  sensitive = true
}

output "market_data_service_client_id" {
  value = keycloak_openid_client.am_market_data_service.client_id
}

output "market_data_service_client_secret" {
  value     = keycloak_openid_client.am_market_data_service.client_secret
  sensitive = true
}

output "market_parser_service_client_id" {
  value = keycloak_openid_client.am_market_parser_service.client_id
}

output "market_parser_service_client_secret" {
  value     = keycloak_openid_client.am_market_parser_service.client_secret
  sensitive = true
}

output "portfolio_service_client_id" {
  value = keycloak_openid_client.am_portfolio_service.client_id
}

output "portfolio_service_client_secret" {
  value     = keycloak_openid_client.am_portfolio_service.client_secret
  sensitive = true
}

output "trade_service_client_id" {
  value = keycloak_openid_client.am_trade_service.client_id
}

output "trade_service_client_secret" {
  value     = keycloak_openid_client.am_trade_service.client_secret
  sensitive = true
}

output "subscription_service_client_id" {
  value = keycloak_openid_client.am_subscription_service.client_id
}

output "subscription_service_client_secret" {
  value     = keycloak_openid_client.am_subscription_service.client_secret
  sensitive = true
}

output "notification_service_client_id" {
  value = keycloak_openid_client.am_notification_service.client_id
}

output "notification_service_client_secret" {
  value     = keycloak_openid_client.am_notification_service.client_secret
  sensitive = true
}

# New clients
output "lago_client_id" {
  value = keycloak_openid_client.am_lago_client.client_id
}

output "lago_client_secret" {
  value     = keycloak_openid_client.am_lago_client.client_secret
  sensitive = true
}

output "analysis_client_id" {
  value = keycloak_openid_client.am_analysis_client.client_id
}

output "analysis_client_secret" {
  value     = keycloak_openid_client.am_analysis_client.client_secret
  sensitive = true
}

output "market_client_id" {
  value = keycloak_openid_client.am_market_client.client_id
}

output "market_client_secret" {
  value     = keycloak_openid_client.am_market_client.client_secret
  sensitive = true
}

output "market_data_client_id" {
  value = keycloak_openid_client.am_market_data_client.client_id
}

output "market_data_client_secret" {
  value     = keycloak_openid_client.am_market_data_client.client_secret
  sensitive = true
}

output "parser_client_id" {
  value = keycloak_openid_client.am_parser_client.client_id
}

output "parser_client_secret" {
  value     = keycloak_openid_client.am_parser_client.client_secret
  sensitive = true
}

output "doc_a_client_id" {
  value = keycloak_openid_client.am_doc_a_client.client_id
}

output "doc_a_client_secret" {
  value     = keycloak_openid_client.am_doc_a_client.client_secret
  sensitive = true
}

output "doc_b_client_id" {
  value = keycloak_openid_client.am_doc_b_client.client_id
}

output "doc_b_client_secret" {
  value     = keycloak_openid_client.am_doc_b_client.client_secret
  sensitive = true
}

output "doc_c_client_id" {
  value = keycloak_openid_client.am_doc_c_client.client_id
}

output "doc_c_client_secret" {
  value     = keycloak_openid_client.am_doc_c_client.client_secret
  sensitive = true
}
