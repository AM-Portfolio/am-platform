output "subscription_db_name" {
  value = var.subscription_db_name
}

output "subscription_db_user" {
  value = var.subscription_db_user
}

output "subscription_db_password" {
  value     = var.subscription_db_password
  sensitive = true
}

output "lago_api_service" {
  value = "lago-api"
}

output "lago_front_service" {
  value = "lago-front"
}

output "billing_namespace" {
  value = "billing"
}
