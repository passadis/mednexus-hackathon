$ErrorActionPreference = "Stop"

$searchEndpoint = $env:AZURE_SEARCH_ENDPOINT
if ([string]::IsNullOrWhiteSpace($searchEndpoint)) {
    throw "AZURE_SEARCH_ENDPOINT is not set."
}

$indexName = if ([string]::IsNullOrWhiteSpace($env:AZURE_SEARCH_INDEX)) { "mednexus-clinical" } else { $env:AZURE_SEARCH_INDEX }
$apiVersion = "2025-09-01"
$token = az account get-access-token --resource https://search.azure.com --query accessToken -o tsv

if ([string]::IsNullOrWhiteSpace($token)) {
    throw "Failed to acquire Azure AI Search access token."
}

$body = @{
    name = $indexName
    fields = @(
        @{
            name = "id"
            type = "Edm.String"
            key = $true
            filterable = $true
        },
        @{
            name = "patient_id"
            type = "Edm.String"
            filterable = $true
            facetable = $true
        },
        @{
            name = "content_type"
            type = "Edm.String"
            filterable = $true
            facetable = $true
        },
        @{
            name = "source_agent"
            type = "Edm.String"
            filterable = $true
        },
        @{
            name = "content"
            type = "Edm.String"
            searchable = $true
            analyzer = "en.microsoft"
        },
        @{
            name = "analysis_summary"
            type = "Edm.String"
            searchable = $true
            analyzer = "en.microsoft"
        },
        @{
            name = "content_vector"
            type = "Collection(Edm.Single)"
            searchable = $true
            dimensions = 1536
            vectorSearchProfile = "mednexus-vector-profile"
        },
        @{
            name = "metadata_storage_path"
            type = "Edm.String"
            filterable = $false
        },
        @{
            name = "timestamp"
            type = "Edm.DateTimeOffset"
            filterable = $true
            sortable = $true
        }
    )
    vectorSearch = @{
        algorithms = @(
            @{
                name = "mednexus-hnsw"
                kind = "hnsw"
                hnswParameters = @{
                    m = 4
                    efConstruction = 400
                    efSearch = 500
                    metric = "cosine"
                }
            }
        )
        profiles = @(
            @{
                name = "mednexus-vector-profile"
                algorithm = "mednexus-hnsw"
            }
        )
    }
    semantic = @{
        configurations = @(
            @{
                name = "mednexus-semantic-config"
                prioritizedFields = @{
                    titleField = @{
                        fieldName = "analysis_summary"
                    }
                    prioritizedContentFields = @(
                        @{
                            fieldName = "content"
                        }
                    )
                    prioritizedKeywordsFields = @(
                        @{
                            fieldName = "content_type"
                        }
                    )
                }
            }
        )
    }
} | ConvertTo-Json -Depth 20

$baseUrl = $searchEndpoint.Trim().TrimEnd("/")
$url = "{0}/indexes/{1}?api-version={2}" -f $baseUrl, $indexName, $apiVersion

Invoke-RestMethod `
    -Method Put `
    -Uri $url `
    -Headers @{
        "Authorization" = "Bearer $token"
        "Content-Type" = "application/json"
    } `
    -Body $body | Out-Null

Write-Host "Azure AI Search index '$indexName' created or updated."
