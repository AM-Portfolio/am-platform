variable "litellm_master_key" {
  description = "Master API key for LiteLLM proxy"
  type        = string
  sensitive   = true
}

variable "deepseek_api_key" {
  description = "DeepSeek API key for LLM access"
  type        = string
  sensitive   = true
  default     = ""
}

variable "google_api_key" {
  description = "Google API key for Gemini"
  type        = string
  sensitive   = true
  default     = ""
}

variable "langfuse_public_key" {
  description = "Langfuse public key"
  type        = string
  sensitive   = true
}

variable "langfuse_secret_key" {
  description = "Langfuse secret key"
  type        = string
  sensitive   = true
}

variable "langfuse_nextauth_secret" {
  description = "NextAuth secret for Langfuse UI"
  type        = string
  sensitive   = true
}

variable "langfuse_host" {
  description = "Public URL for Langfuse (used in LiteLLM callback config)"
  type        = string
  default     = "https://langfuse.munish.org"
}

variable "langfuse_db_password" {
  description = "PostgreSQL password for Langfuse database"
  type        = string
  sensitive   = true
}

variable "kubeconfig_path" {
  description = "Path to kubeconfig file"
  type        = string
  default     = "kubeconfig.yaml"
}

variable "litellm_db_password" {
  description = "PostgreSQL password for LiteLLM database"
  type        = string
  sensitive   = true
}

variable "together_api_key" {
  description = "Together AI API key"
  type        = string
  sensitive   = true
  default     = ""
}
