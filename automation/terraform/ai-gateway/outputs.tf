output "litellm_service" {
  description = "LiteLLM internal service address"
  value       = "http://litellm.am-ai.svc.cluster.local:4000"
}

output "langfuse_service" {
  description = "Langfuse internal service address"
  value       = "http://langfuse.am-ai.svc.cluster.local:3000"
}

output "qdrant_service" {
  description = "Qdrant internal service address"
  value       = "http://qdrant.am-ai.svc.cluster.local:6333"
}

output "mlflow_service" {
  description = "MLflow internal service address"
  value       = "http://mlflow.am-ai.svc.cluster.local:5000"
}
