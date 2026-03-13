variable "environment_name" {
  description = "AZD environment name."
  type        = string
}

variable "location" {
  description = "Azure region for the deployment."
  type        = string
}

variable "resource_group_name" {
  description = "Optional resource group name. If empty, the template generates one."
  type        = string
  default     = ""
}

variable "openai_chat_deployment" {
  description = "Azure AI Foundry chat deployment name."
  type        = string
  default     = "gpt-4o"
}

variable "openai_embedding_deployment" {
  description = "Azure AI Foundry embedding deployment name."
  type        = string
  default     = "text-embedding-3-small"
}

variable "openai_whisper_deployment" {
  description = "Azure AI Foundry Whisper deployment name."
  type        = string
  default     = "whisper"
}

variable "openai_api_version" {
  description = "Azure OpenAI-compatible API version for non-realtime calls."
  type        = string
  default     = "2024-12-01-preview"
}

variable "openai_location" {
  description = "Optional Azure region for the Azure AI Foundry resource and model deployments. If empty, uses the main deployment location."
  type        = string
  default     = ""
}

variable "openai_sku_name" {
  description = "SKU for the Azure AI Foundry account."
  type        = string
  default     = "S0"
}

variable "openai_chat_model_name" {
  description = "Model name for the chat deployment."
  type        = string
  default     = "gpt-4o"
}

variable "openai_chat_model_version" {
  description = "Model version for the chat deployment."
  type        = string
  default     = "2024-11-20"
}

variable "openai_chat_sku_name" {
  description = "Deployment SKU for the chat model."
  type        = string
  default     = "GlobalStandard"
}

variable "openai_chat_capacity" {
  description = "Deployment capacity for the chat model in units of 1,000 TPM, subject to regional quota."
  type        = number
  default     = 50
}

variable "openai_embedding_model_name" {
  description = "Model name for the embedding deployment."
  type        = string
  default     = "text-embedding-3-small"
}

variable "openai_embedding_model_version" {
  description = "Model version for the embedding deployment."
  type        = string
  default     = "1"
}

variable "openai_embedding_sku_name" {
  description = "Deployment SKU for the embedding model."
  type        = string
  default     = "GlobalStandard"
}

variable "openai_embedding_capacity" {
  description = "Deployment capacity for the embedding model in units of 1,000 TPM, subject to regional quota."
  type        = number
  default     = 1
}

variable "openai_whisper_model_name" {
  description = "Model name for the whisper deployment."
  type        = string
  default     = "whisper"
}

variable "openai_whisper_model_version" {
  description = "Model version for the whisper deployment."
  type        = string
  default     = "001"
}

variable "openai_whisper_sku_name" {
  description = "Deployment SKU for the whisper model."
  type        = string
  default     = "Standard"
}

variable "openai_whisper_capacity" {
  description = "Deployment capacity for the whisper model in units of 1,000 TPM, subject to regional quota."
  type        = number
  default     = 1
}

variable "realtime_model_name" {
  description = "Model name for the realtime deployment."
  type        = string
  default     = "gpt-realtime-1.5"
}

variable "realtime_model_version" {
  description = "Model version for the realtime deployment."
  type        = string
  default     = "2026-02-23"
}

variable "realtime_sku_name" {
  description = "Deployment SKU for the realtime model."
  type        = string
  default     = "GlobalStandard"
}

variable "realtime_capacity" {
  description = "Deployment capacity for the realtime model in units of 1,000 TPM, subject to regional quota."
  type        = number
  default     = 1
}

variable "realtime_deployment" {
  description = "Azure AI Foundry Realtime deployment name."
  type        = string
  default     = "gpt-realtime"
}

variable "search_local_auth_enabled" {
  description = "Enable Search local auth so deployment-time tooling can create the index. Runtime still uses managed identity."
  type        = bool
  default     = false
}

variable "search_admin_api_version" {
  description = "API version for Search data-plane index creation."
  type        = string
  default     = "2024-07-01"
}

variable "portal_jwt_secret" {
  description = "Optional JWT signing secret. Leave empty to auto-generate."
  type        = string
  default     = ""
  sensitive   = true
}

variable "backend_cpu" {
  description = "CPU allocation for the backend container app."
  type        = number
  default     = 1
}

variable "backend_memory" {
  description = "Memory allocation for the backend container app."
  type        = string
  default     = "2Gi"
}

variable "frontend_cpu" {
  description = "CPU allocation for the frontend container app."
  type        = number
  default     = 0.5
}

variable "frontend_memory" {
  description = "Memory allocation for the frontend container app."
  type        = string
  default     = "1Gi"
}

variable "search_sku" {
  description = "SKU for Azure AI Search."
  type        = string
  default     = "basic"
}

variable "cosmos_database_name" {
  description = "Cosmos DB database name."
  type        = string
  default     = "mednexus"
}

variable "cosmos_container_name" {
  description = "Cosmos DB container name."
  type        = string
  default     = "clinical_contexts"
}

variable "search_index_name" {
  description = "Azure AI Search index name."
  type        = string
  default     = "mednexus-clinical"
}

variable "storage_container_name" {
  description = "Blob container name used for intake files."
  type        = string
  default     = "mednexus-intake"
}
