data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

resource "random_password" "portal_jwt_secret" {
  length           = 32
  special          = true
  override_special = "_%@"
}

locals {
  env_suffix      = lower(join("", regexall("[0-9A-Za-z]+", var.environment_name)))
  name_suffix     = "${local.env_suffix}${random_string.suffix.result}"
  service_suffix  = lower(join("", regexall("[0-9A-Za-z-]+", var.environment_name)))
  openai_location = var.openai_location != "" ? var.openai_location : var.location
  resource_group_name = var.resource_group_name != "" ? var.resource_group_name : substr(
    "rg-${local.name_suffix}",
    0,
    90
  )
  tags = {
    "azd-env-name" = var.environment_name
    "project"      = "mednexus"
  }

  acr_name            = substr("acr${local.name_suffix}", 0, 50)
  log_analytics_name  = "law-${local.name_suffix}"
  app_insights_name   = "appi-${local.name_suffix}"
  container_env_name  = "cae-${local.name_suffix}"
  identity_name       = "id-${local.name_suffix}"
  openai_name         = substr("aoai-${local.name_suffix}", 0, 24)
  storage_name        = substr("st${local.name_suffix}", 0, 24)
  cosmos_name         = "cosmos-${local.name_suffix}"
  search_name         = substr("srch-${local.name_suffix}", 0, 60)
  key_vault_name      = substr("kv-${local.name_suffix}", 0, 24)
  backend_name        = substr("${local.service_suffix}backend", 0, 32)
  frontend_name       = substr("${local.service_suffix}frontend", 0, 32)
  jwt_secret_value    = var.portal_jwt_secret != "" ? var.portal_jwt_secret : random_password.portal_jwt_secret.result
  storage_account_url = "https://${azurerm_storage_account.main.name}.blob.core.windows.net"
}

resource "azurerm_resource_group" "rg" {
  name     = local.resource_group_name
  location = var.location
  tags     = local.tags
}

resource "azurerm_container_registry" "acr" {
  name                = local.acr_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.tags
}

resource "azurerm_log_analytics_workspace" "main" {
  name                = local.log_analytics_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_application_insights" "main" {
  name                = local.app_insights_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = local.tags
}

resource "azurerm_user_assigned_identity" "apps" {
  name                = local.identity_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  tags                = local.tags
}

resource "azurerm_role_assignment" "apps_app_insights_metrics_publisher" {
  scope                = azurerm_application_insights.main.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.acr.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
}

resource "azurerm_cognitive_account" "openai" {
  name                          = local.openai_name
  resource_group_name           = azurerm_resource_group.rg.name
  location                      = local.openai_location
  kind                          = "AIServices"
  sku_name                      = var.openai_sku_name
  project_management_enabled    = true
  custom_subdomain_name         = local.openai_name
  public_network_access_enabled = true

  identity {
    type = "SystemAssigned"
  }

  tags = local.tags
}

resource "azapi_resource" "openai_chat_deployment" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-06-01"
  name      = var.openai_chat_deployment
  parent_id = azurerm_cognitive_account.openai.id

  body = {
    sku = {
      name     = var.openai_chat_sku_name
      capacity = var.openai_chat_capacity
    }
    properties = {
      model = {
        format  = "OpenAI"
        name    = var.openai_chat_model_name
        version = var.openai_chat_model_version
      }
      versionUpgradeOption = "OnceNewDefaultVersionAvailable"
    }
  }

  schema_validation_enabled = false

  depends_on = [azurerm_cognitive_account.openai]
}

resource "azapi_resource" "openai_embedding_deployment" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-06-01"
  name      = var.openai_embedding_deployment
  parent_id = azurerm_cognitive_account.openai.id

  body = {
    sku = {
      name     = var.openai_embedding_sku_name
      capacity = var.openai_embedding_capacity
    }
    properties = {
      model = {
        format  = "OpenAI"
        name    = var.openai_embedding_model_name
        version = var.openai_embedding_model_version
      }
      versionUpgradeOption = "OnceNewDefaultVersionAvailable"
    }
  }

  schema_validation_enabled = false

  depends_on = [azapi_resource.openai_chat_deployment]
}

resource "azapi_resource" "openai_whisper_deployment" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-06-01"
  name      = var.openai_whisper_deployment
  parent_id = azurerm_cognitive_account.openai.id

  body = {
    sku = {
      name     = var.openai_whisper_sku_name
      capacity = var.openai_whisper_capacity
    }
    properties = {
      model = {
        format  = "OpenAI"
        name    = var.openai_whisper_model_name
        version = var.openai_whisper_model_version
      }
      versionUpgradeOption = "OnceNewDefaultVersionAvailable"
    }
  }

  schema_validation_enabled = false

  depends_on = [azapi_resource.openai_embedding_deployment]
}

resource "azapi_resource" "openai_realtime_deployment" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-06-01"
  name      = var.realtime_deployment
  parent_id = azurerm_cognitive_account.openai.id

  body = {
    sku = {
      name     = var.realtime_sku_name
      capacity = var.realtime_capacity
    }
    properties = {
      model = {
        format  = "OpenAI"
        name    = var.realtime_model_name
        version = var.realtime_model_version
      }
      versionUpgradeOption = "OnceNewDefaultVersionAvailable"
    }
  }

  schema_validation_enabled = false

  depends_on = [azapi_resource.openai_whisper_deployment]
}

resource "azurerm_storage_account" "main" {
  name                            = local.storage_name
  resource_group_name             = azurerm_resource_group.rg.name
  location                        = azurerm_resource_group.rg.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  allow_nested_items_to_be_public = false
  min_tls_version                 = "TLS1_2"
  tags                            = local.tags
}

resource "azurerm_storage_container" "intake" {
  name                  = var.storage_container_name
  storage_account_id    = azurerm_storage_account.main.id
  container_access_type = "private"
}

resource "azurerm_role_assignment" "storage_blob_data_contributor" {
  scope                = azurerm_storage_account.main.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
}

resource "azurerm_cosmosdb_account" "main" {
  name                = local.cosmos_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  consistency_policy {
    consistency_level = "Session"
  }

  capabilities {
    name = "EnableServerless"
  }

  geo_location {
    location          = azurerm_resource_group.rg.location
    failover_priority = 0
  }

  tags = local.tags
}

resource "azurerm_cosmosdb_sql_database" "main" {
  name                = var.cosmos_database_name
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.main.name
}

resource "azurerm_cosmosdb_sql_container" "clinical_contexts" {
  name                = var.cosmos_container_name
  resource_group_name = azurerm_resource_group.rg.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = ["/patient_id"]
}

resource "azurerm_search_service" "main" {
  name                          = local.search_name
  resource_group_name           = azurerm_resource_group.rg.name
  location                      = azurerm_resource_group.rg.location
  sku                           = var.search_sku
  local_authentication_enabled  = var.search_local_auth_enabled
  public_network_access_enabled = true
  semantic_search_sku           = "free"
  tags                          = local.tags
}

resource "azurerm_role_assignment" "search_service_contributor" {
  scope                = azurerm_search_service.main.id
  role_definition_name = "Search Service Contributor"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
}

resource "azurerm_role_assignment" "search_index_data_contributor" {
  scope                = azurerm_search_service.main.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
}

resource "azurerm_role_assignment" "deployer_search_service_contributor" {
  scope                = azurerm_search_service.main.id
  role_definition_name = "Search Service Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "deployer_search_index_data_contributor" {
  scope                = azurerm_search_service.main.id
  role_definition_name = "Search Index Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "openai_user" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
}

resource "azurerm_role_assignment" "openai_ai_developer" {
  scope                = azurerm_cognitive_account.openai.id
  role_definition_name = "Azure AI Developer"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
}

resource "azurerm_key_vault" "main" {
  name                       = local.key_vault_name
  location                   = azurerm_resource_group.rg.location
  resource_group_name        = azurerm_resource_group.rg.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
  tags                       = local.tags
}

resource "azurerm_role_assignment" "deployer_kv_admin" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "apps_kv_secrets_user" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
}

resource "azurerm_key_vault_secret" "cosmos_key" {
  name         = "cosmos-key"
  value        = azurerm_cosmosdb_account.main.primary_key
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.deployer_kv_admin]
}

resource "azurerm_key_vault_secret" "portal_jwt_secret" {
  name         = "portal-jwt-secret"
  value        = local.jwt_secret_value
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.deployer_kv_admin]
}

resource "azurerm_key_vault_secret" "realtime_api_key" {
  name         = "openai-realtime-api-key"
  value        = azurerm_cognitive_account.openai.primary_access_key
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.deployer_kv_admin]
}

resource "azurerm_container_app_environment" "main" {
  name                       = local.container_env_name
  location                   = azurerm_resource_group.rg.location
  resource_group_name        = azurerm_resource_group.rg.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  tags                       = local.tags
}

resource "azurerm_container_app" "backend" {
  name                         = local.backend_name
  resource_group_name          = azurerm_resource_group.rg.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"
  tags = merge(local.tags, {
    "azd-service-name" = "backend"
  })

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.apps.id]
  }

  registry {
    server   = azurerm_container_registry.acr.login_server
    identity = azurerm_user_assigned_identity.apps.id
  }

  secret {
    name                = "cosmos-key"
    key_vault_secret_id = azurerm_key_vault_secret.cosmos_key.id
    identity            = azurerm_user_assigned_identity.apps.id
  }

  secret {
    name                = "portal-jwt-secret"
    key_vault_secret_id = azurerm_key_vault_secret.portal_jwt_secret.id
    identity            = azurerm_user_assigned_identity.apps.id
  }

  secret {
    name                = "realtime-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.realtime_api_key.id
    identity            = azurerm_user_assigned_identity.apps.id
  }

  ingress {
    allow_insecure_connections = false
    external_enabled           = false
    target_port                = 8000
    transport                  = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  dapr {
    app_id   = local.backend_name
    app_port = 8000
  }

  template {
    min_replicas = 1
    max_replicas = 2

    container {
      name   = "backend"
      image  = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
      cpu    = var.backend_cpu
      memory = var.backend_memory

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.main.connection_string
      }

      env {
        name  = "APPLICATIONINSIGHTS_AUTHENTICATION_STRING"
        value = "Authorization=AAD;ClientId=${azurerm_user_assigned_identity.apps.client_id}"
      }

      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = azurerm_cognitive_account.openai.endpoint
      }

      env {
        name  = "AZURE_OPENAI_DEPLOYMENT"
        value = var.openai_chat_deployment
      }

      env {
        name  = "AZURE_OPENAI_API_VERSION"
        value = var.openai_api_version
      }

      env {
        name  = "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
        value = var.openai_embedding_deployment
      }

      env {
        name  = "AZURE_OPENAI_WHISPER_DEPLOYMENT"
        value = var.openai_whisper_deployment
      }

      env {
        name  = "AZURE_OPENAI_REALTIME_ENDPOINT"
        value = azurerm_cognitive_account.openai.endpoint
      }

      env {
        name        = "AZURE_OPENAI_REALTIME_KEY"
        secret_name = "realtime-api-key"
      }

      env {
        name  = "AZURE_OPENAI_REALTIME_DEPLOYMENT"
        value = var.realtime_deployment
      }

      env {
        name  = "AZURE_SEARCH_ENDPOINT"
        value = "https://${azurerm_search_service.main.name}.search.windows.net"
      }

      env {
        name  = "AZURE_SEARCH_INDEX"
        value = var.search_index_name
      }

      env {
        name  = "AZURE_KEY_VAULT_URL"
        value = azurerm_key_vault.main.vault_uri
      }

      env {
        name  = "AZURE_STORAGE_ACCOUNT_URL"
        value = local.storage_account_url
      }

      env {
        name  = "AZURE_STORAGE_CONTAINER"
        value = azurerm_storage_container.intake.name
      }

      env {
        name  = "COSMOS_ENDPOINT"
        value = azurerm_cosmosdb_account.main.endpoint
      }

      env {
        name        = "COSMOS_KEY"
        secret_name = "cosmos-key"
      }

      env {
        name  = "COSMOS_DATABASE"
        value = azurerm_cosmosdb_sql_database.main.name
      }

      env {
        name  = "COSMOS_CONTAINER"
        value = azurerm_cosmosdb_sql_container.clinical_contexts.name
      }

      env {
        name        = "PORTAL_JWT_SECRET"
        secret_name = "portal-jwt-secret"
      }

      env {
        name  = "PORTAL_JWT_EXPIRY_HOURS"
        value = "48"
      }

      env {
        name  = "USE_MANAGED_IDENTITY"
        value = "true"
      }

      env {
        name  = "MANAGED_IDENTITY_CLIENT_ID"
        value = azurerm_user_assigned_identity.apps.client_id
      }

      env {
        name  = "MEDNEXUS_CORS_ORIGINS"
        value = "*"
      }

      env {
        name  = "MEDNEXUS_BOOTSTRAP_SEARCH_INDEX"
        value = "false"
      }
    }
  }

  depends_on = [
    azapi_resource.openai_chat_deployment,
    azapi_resource.openai_embedding_deployment,
    azapi_resource.openai_whisper_deployment,
    azapi_resource.openai_realtime_deployment
  ]
}

resource "azurerm_container_app" "frontend" {
  name                         = local.frontend_name
  resource_group_name          = azurerm_resource_group.rg.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"
  tags = merge(local.tags, {
    "azd-service-name" = "frontend"
  })

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.apps.id]
  }

  registry {
    server   = azurerm_container_registry.acr.login_server
    identity = azurerm_user_assigned_identity.apps.id
  }

  ingress {
    allow_insecure_connections = false
    external_enabled           = true
    target_port                = 80
    transport                  = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  dapr {
    app_id   = local.frontend_name
    app_port = 80
  }

  template {
    min_replicas = 1
    max_replicas = 2

    container {
      name   = "frontend"
      image  = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
      cpu    = var.frontend_cpu
      memory = var.frontend_memory

      env {
        name  = "DAPR_BACKEND_APP_ID"
        value = local.backend_name
      }

      env {
        name  = "BACKEND_INTERNAL_HOST"
        value = azurerm_container_app.backend.ingress[0].fqdn
      }
    }
  }
}
