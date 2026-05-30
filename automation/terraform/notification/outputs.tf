output "notification_db_name" {
  value = var.notification_db_name
}

output "notification_db_user" {
  value = var.notification_db_user
}

output "notification_db_password" {
  value     = var.notification_db_password
  sensitive = true
}

output "novu_db_name" {
  value = var.novu_db_name
}

output "novu_db_user" {
  value = var.novu_db_user
}

output "novu_db_password" {
  value     = var.novu_db_password
  sensitive = true
}

output "notification_namespace" {
  value = "notification"
}
