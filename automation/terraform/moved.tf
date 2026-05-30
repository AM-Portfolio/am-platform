moved {
  from = keycloak_realm.am_realm
  to   = module.keycloak.keycloak_realm.am_realm
}

moved {
  from = keycloak_role.role_user
  to   = module.keycloak.keycloak_role.role_user
}

moved {
  from = keycloak_role.role_admin
  to   = module.keycloak.keycloak_role.role_admin
}

moved {
  from = keycloak_role.role_viewer
  to   = module.keycloak.keycloak_role.role_viewer
}

moved {
  from = keycloak_role.role_service
  to   = module.keycloak.keycloak_role.role_service
}

moved {
  from = keycloak_default_roles.default_roles
  to   = module.keycloak.keycloak_default_roles.default_roles
}

moved {
  from = keycloak_openid_client.am_web_client
  to   = module.keycloak.keycloak_openid_client.am_web_client
}

moved {
  from = keycloak_openid_client.am_diagnostic_client
  to   = module.keycloak.keycloak_openid_client.am_diagnostic_client
}

moved {
  from = keycloak_openid_client.am_identity_service
  to   = module.keycloak.keycloak_openid_client.am_identity_service
}

moved {
  from = keycloak_openid_client.am_gateway_client
  to   = module.keycloak.keycloak_openid_client.am_gateway_client
}

moved {
  from = keycloak_openid_client.am_gateway_streaming_service
  to   = module.keycloak.keycloak_openid_client.am_gateway_streaming_service
}

moved {
  from = keycloak_openid_client.am_mcp_service
  to   = module.keycloak.keycloak_openid_client.am_mcp_service
}

moved {
  from = keycloak_openid_client.am_fin_agent_service
  to   = module.keycloak.keycloak_openid_client.am_fin_agent_service
}

moved {
  from = keycloak_openid_client.am_doc_intelligence_service
  to   = module.keycloak.keycloak_openid_client.am_doc_intelligence_service
}

moved {
  from = keycloak_openid_client.am_analysis_service
  to   = module.keycloak.keycloak_openid_client.am_analysis_service
}

moved {
  from = keycloak_openid_client.am_market_service
  to   = module.keycloak.keycloak_openid_client.am_market_service
}

moved {
  from = keycloak_openid_client.am_market_data_service
  to   = module.keycloak.keycloak_openid_client.am_market_data_service
}

moved {
  from = keycloak_openid_client.am_market_parser_service
  to   = module.keycloak.keycloak_openid_client.am_market_parser_service
}

moved {
  from = keycloak_openid_client.am_portfolio_service
  to   = module.keycloak.keycloak_openid_client.am_portfolio_service
}

moved {
  from = keycloak_openid_client.am_trade_service
  to   = module.keycloak.keycloak_openid_client.am_trade_service
}

moved {
  from = keycloak_openid_client.am_subscription_service
  to   = module.keycloak.keycloak_openid_client.am_subscription_service
}

moved {
  from = keycloak_openid_client.am_notification_service
  to   = module.keycloak.keycloak_openid_client.am_notification_service
}

moved {
  from = keycloak_openid_client.am_android_client
  to   = module.keycloak.keycloak_openid_client.am_android_client
}

moved {
  from = keycloak_openid_client.am_ios_client
  to   = module.keycloak.keycloak_openid_client.am_ios_client
}

moved {
  from = keycloak_openid_client_service_account_realm_role.identity_svc_role
  to   = module.keycloak.keycloak_openid_client_service_account_realm_role.identity_svc_role
}

moved {
  from = keycloak_openid_client_service_account_realm_role.gateway_svc_role
  to   = module.keycloak.keycloak_openid_client_service_account_realm_role.gateway_svc_role
}

moved {
  from = keycloak_openid_client_service_account_realm_role.gateway_streaming_svc_role
  to   = module.keycloak.keycloak_openid_client_service_account_realm_role.gateway_streaming_svc_role
}

moved {
  from = keycloak_openid_client_service_account_realm_role.mcp_svc_role
  to   = module.keycloak.keycloak_openid_client_service_account_realm_role.mcp_svc_role
}

moved {
  from = keycloak_openid_client_service_account_realm_role.fin_agent_svc_role
  to   = module.keycloak.keycloak_openid_client_service_account_realm_role.fin_agent_svc_role
}

moved {
  from = keycloak_openid_client_service_account_realm_role.doc_intelligence_svc_role
  to   = module.keycloak.keycloak_openid_client_service_account_realm_role.doc_intelligence_svc_role
}

moved {
  from = keycloak_openid_client_service_account_realm_role.analysis_svc_role
  to   = module.keycloak.keycloak_openid_client_service_account_realm_role.analysis_svc_role
}

moved {
  from = keycloak_openid_client_service_account_realm_role.market_svc_role
  to   = module.keycloak.keycloak_openid_client_service_account_realm_role.market_svc_role
}

moved {
  from = keycloak_openid_client_service_account_realm_role.market_data_svc_role
  to   = module.keycloak.keycloak_openid_client_service_account_realm_role.market_data_svc_role
}

moved {
  from = keycloak_openid_client_service_account_realm_role.market_parser_svc_role
  to   = module.keycloak.keycloak_openid_client_service_account_realm_role.market_parser_svc_role
}

moved {
  from = keycloak_openid_client_service_account_realm_role.portfolio_svc_role
  to   = module.keycloak.keycloak_openid_client_service_account_realm_role.portfolio_svc_role
}

moved {
  from = keycloak_openid_client_service_account_realm_role.trade_svc_role
  to   = module.keycloak.keycloak_openid_client_service_account_realm_role.trade_svc_role
}

moved {
  from = keycloak_openid_client_service_account_realm_role.subscription_svc_role
  to   = module.keycloak.keycloak_openid_client_service_account_realm_role.subscription_svc_role
}

moved {
  from = keycloak_openid_client_service_account_realm_role.notification_svc_role
  to   = module.keycloak.keycloak_openid_client_service_account_realm_role.notification_svc_role
}

moved {
  from = keycloak_oidc_google_identity_provider.google_idp
  to   = module.keycloak.keycloak_oidc_google_identity_provider.google_idp
}

moved {
  from = keycloak_openid_user_realm_role_protocol_mapper.web_realm_roles_mapper
  to   = module.keycloak.keycloak_openid_user_realm_role_protocol_mapper.web_realm_roles_mapper
}

moved {
  from = keycloak_openid_hardcoded_claim_protocol_mapper.web_platform_mapper
  to   = module.keycloak.keycloak_openid_hardcoded_claim_protocol_mapper.web_platform_mapper
}

moved {
  from = keycloak_openid_user_realm_role_protocol_mapper.diagnostic_realm_roles_mapper
  to   = module.keycloak.keycloak_openid_user_realm_role_protocol_mapper.diagnostic_realm_roles_mapper
}

moved {
  from = keycloak_openid_hardcoded_claim_protocol_mapper.diagnostic_platform_mapper
  to   = module.keycloak.keycloak_openid_hardcoded_claim_protocol_mapper.diagnostic_platform_mapper
}

moved {
  from = keycloak_openid_user_realm_role_protocol_mapper.android_realm_roles_mapper
  to   = module.keycloak.keycloak_openid_user_realm_role_protocol_mapper.android_realm_roles_mapper
}

moved {
  from = keycloak_openid_hardcoded_claim_protocol_mapper.android_platform_mapper
  to   = module.keycloak.keycloak_openid_hardcoded_claim_protocol_mapper.android_platform_mapper
}

moved {
  from = keycloak_openid_user_realm_role_protocol_mapper.ios_realm_roles_mapper
  to   = module.keycloak.keycloak_openid_user_realm_role_protocol_mapper.ios_realm_roles_mapper
}

moved {
  from = keycloak_openid_hardcoded_claim_protocol_mapper.ios_platform_mapper
  to   = module.keycloak.keycloak_openid_hardcoded_claim_protocol_mapper.ios_platform_mapper
}

moved {
  from = keycloak_openid_client_scope.am_user_scope
  to   = module.keycloak.keycloak_openid_client_scope.am_user_scope
}
