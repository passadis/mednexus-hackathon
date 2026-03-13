#!/usr/bin/env sh
set -eu

SEARCH_ENDPOINT="${AZURE_SEARCH_ENDPOINT:-}"
if [ -z "$SEARCH_ENDPOINT" ]; then
  echo "AZURE_SEARCH_ENDPOINT is not set." >&2
  exit 1
fi

INDEX_NAME="${AZURE_SEARCH_INDEX:-mednexus-clinical}"
API_VERSION="2025-09-01"
TOKEN="$(az account get-access-token --resource https://search.azure.com --query accessToken -o tsv)"

if [ -z "$TOKEN" ]; then
  echo "Failed to acquire Azure AI Search access token." >&2
  exit 1
fi

BODY=$(cat <<EOF
{
  "name": "$INDEX_NAME",
  "fields": [
    { "name": "id", "type": "Edm.String", "key": true, "filterable": true },
    { "name": "patient_id", "type": "Edm.String", "filterable": true, "facetable": true },
    { "name": "content_type", "type": "Edm.String", "filterable": true, "facetable": true },
    { "name": "source_agent", "type": "Edm.String", "filterable": true },
    { "name": "content", "type": "Edm.String", "searchable": true, "analyzer": "en.microsoft" },
    { "name": "analysis_summary", "type": "Edm.String", "searchable": true, "analyzer": "en.microsoft" },
    { "name": "content_vector", "type": "Collection(Edm.Single)", "searchable": true, "dimensions": 1536, "vectorSearchProfile": "mednexus-vector-profile" },
    { "name": "metadata_storage_path", "type": "Edm.String", "filterable": false },
    { "name": "timestamp", "type": "Edm.DateTimeOffset", "filterable": true, "sortable": true }
  ],
  "vectorSearch": {
    "algorithms": [
      {
        "name": "mednexus-hnsw",
        "kind": "hnsw",
        "hnswParameters": {
          "m": 4,
          "efConstruction": 400,
          "efSearch": 500,
          "metric": "cosine"
        }
      }
    ],
    "profiles": [
      {
        "name": "mednexus-vector-profile",
        "algorithm": "mednexus-hnsw"
      }
    ]
  },
  "semantic": {
    "configurations": [
      {
        "name": "mednexus-semantic-config",
        "prioritizedFields": {
          "titleField": { "fieldName": "analysis_summary" },
          "prioritizedContentFields": [{ "fieldName": "content" }],
          "prioritizedKeywordsFields": [{ "fieldName": "content_type" }]
        }
      }
    ]
  }
}
EOF
)

BASE_URL="$(printf '%s' "$SEARCH_ENDPOINT" | tr -d '\r' | sed 's:/*$::')"

curl -fsS -X PUT \
  "${BASE_URL}/indexes/${INDEX_NAME}?api-version=${API_VERSION}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$BODY" >/dev/null

echo "Azure AI Search index '${INDEX_NAME}' created or updated."
