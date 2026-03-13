output "AZURE_CONTAINER_REGISTRY_ENDPOINT" {
  value = azurerm_container_registry.acr.login_server
}

output "AZURE_OPENAI_ENDPOINT" {
  value = azurerm_cognitive_account.openai.endpoint
}

output "AZURE_OPENAI_RESOURCE_ID" {
  value = azurerm_cognitive_account.openai.id
}

output "AZURE_CONTAINER_APPS_ENVIRONMENT_ID" {
  value = azurerm_container_app_environment.main.id
}

output "SERVICE_BACKEND_NAME" {
  value = azurerm_container_app.backend.name
}

output "SERVICE_BACKEND_RESOURCE_ID" {
  value = azurerm_container_app.backend.id
}

output "SERVICE_FRONTEND_NAME" {
  value = azurerm_container_app.frontend.name
}

output "SERVICE_FRONTEND_RESOURCE_ID" {
  value = azurerm_container_app.frontend.id
}

output "MANAGED_IDENTITY_CLIENT_ID" {
  value = azurerm_user_assigned_identity.apps.client_id
}

output "KEY_VAULT_URI" {
  value = azurerm_key_vault.main.vault_uri
}

output "COSMOS_ENDPOINT" {
  value = azurerm_cosmosdb_account.main.endpoint
}

output "AZURE_SEARCH_ENDPOINT" {
  value = "https://${azurerm_search_service.main.name}.search.windows.net"
}

output "AZURE_STORAGE_ACCOUNT_URL" {
  value = "https://${azurerm_storage_account.main.name}.blob.core.windows.net"
}

output "SERVICE_FRONTEND_ENDPOINTS" {
  value = ["https://${azurerm_container_app.frontend.ingress[0].fqdn}"]
}

output "SERVICE_BACKEND_ENDPOINTS" {
  value = ["https://${azurerm_container_app.backend.ingress[0].fqdn}"]
}
