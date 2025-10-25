targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment that can be used as part of naming resource convention')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Id of the user or app to assign application roles')
param principalId string = ''

@description('Name of the resource group the search service and deployed embedding model are in')
param resourceGroupName string  = ''// Set in main.parameters.json

@allowed([ 'free', 'basic', 'standard', 'standard2', 'standard3', 'storage_optimized_l1', 'storage_optimized_l2' ])
param searchServiceSkuName string // Set in main.parameters.json

@description('Display name of Computer Vision API account')
param computerVisionAccountName string = '' // Set in main.parameters.json

@description('SKU for Computer Vision API')
param computerVisionSkuName string // Set in main.parameters.json

param computerVisionLocation string = '' // Set in main.parameters.json

param computerVisionResourceGroupName string = '' // Set in main.parameters.json

param searchServiceLocation string = '' // set in main.parameters.json

param searchServiceName string = '' // Set in main.parameters.json

param searchServiceResourceGroupName string = ''// Set in main.parameters.json

param semanticSearchSkuName string = '' // Set in main.parameters.json

param storageLocation string = '' // Set in main.parameters.json

param storageResourceGroupName string = '' // Set in main.parameters.json

param storageAccountName string = '' // Set in main.parameters.json

param apiServiceLocation string = '' // Set in main.parameters.json

param apiServiceResourceGroupName string = '' // Set in main.parameters.json

param logAnalyticsName string = '' // Set in main.parameters.json

param applicationInsightsName string = '' // Set in main.parameters.json

param searchIndexName string = '' // Set in main.parameters.json

param acaExists bool = false // Set in main.parameters.json

@description('Whether the deployment is running on GitHub Actions')
param runningOnGh string = ''

var principalType = empty(runningOnGh) ? 'User' : 'ServicePrincipal'

// Cannot use semantic search on free tier
var actualSemanticSearchSkuName = searchServiceSkuName == 'free' ? 'disabled' : semanticSearchSkuName

// Tags that should be applied to all resources.
// 
// Note that 'azd-service-name' tags should be applied separately to service host resources.
// Example usage:
//   tags: union(tags, { 'azd-service-name': <service name in azure.yaml> })
var tags = {
  'azd-env-name': environmentName
}

var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))

resource resourceGroup 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: empty(resourceGroupName) ? '${abbrs.resourcesResourceGroups}${environmentName}' : resourceGroupName
  location: location
  tags: tags
}

resource searchServiceResourceGroup 'Microsoft.Resources/resourceGroups@2022-09-01' existing = if (!empty(searchServiceResourceGroupName)) {
  name: !empty(searchServiceResourceGroupName) ? searchServiceResourceGroupName : resourceGroup.name
}

resource apiServiceResourceGroup 'Microsoft.Resources/resourceGroups@2022-09-01' existing = if (!empty(apiServiceResourceGroupName)) {
  name: !empty(apiServiceResourceGroupName) ? apiServiceResourceGroupName : resourceGroup.name
}

resource storageResourceGroup 'Microsoft.Resources/resourceGroups@2022-09-01' existing = if (!empty(storageResourceGroupName)) {
  name: !empty(storageResourceGroupName) ? storageResourceGroupName : resourceGroup.name
}

resource computerVisionResourceGroup 'Microsoft.Resources/resourceGroups@2022-09-01' existing = if (!empty(computerVisionResourceGroupName)) {
  name: !empty(computerVisionResourceGroupName) ? computerVisionResourceGroupName : resourceGroup.name
}

module searchService 'core/search/search-services.bicep' = {
  name: 'search-service'
  scope: searchServiceResourceGroup
  params: {
    name: empty(searchServiceName) ? '${abbrs.searchSearchServices}${resourceToken}' : searchServiceName
    location: empty(searchServiceLocation) ? location : searchServiceLocation
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'  
      }
    }
    sku: {
      name: searchServiceSkuName
    }
    semanticSearch: actualSemanticSearchSkuName
    tags: tags
  }
}

// Backing storage for sample data
module storage './core/storage/storage-account.bicep' = {
  name: 'storage'
  scope: storageResourceGroup
  params: {
    name: !empty(storageAccountName) ? storageAccountName : '${abbrs.storageStorageAccounts}${resourceToken}'
    location: empty(storageLocation) ? location : storageLocation
    tags: tags
    allowBlobPublicAccess: true
  }
}

// Storage contributor role to upload sample data
module storageContribRoleUser 'core/security/role.bicep' = {
  scope: storageResourceGroup
  name: 'storage-contribrole-user'
  params: {
    principalId: principalId
    roleDefinitionId: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    principalType: principalType
  }
}

// Monitor application with Azure Monitor
module monitoring './core/monitor/monitoring.bicep' = {
  name: 'monitoring'
  scope: apiServiceResourceGroup
  params: {
    location: empty(apiServiceLocation) ? location : apiServiceLocation
    tags: tags
    logAnalyticsName: !empty(logAnalyticsName) ? logAnalyticsName : '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    applicationInsightsName: !empty(applicationInsightsName) ? applicationInsightsName : '${abbrs.insightsComponents}${resourceToken}'
  }
}

// Computer vision account for vision embeddings
module computerVision 'core/ai/cognitiveservices.bicep' = {
  name: 'computervision'
  scope: computerVisionResourceGroup
  params: {
    name: !empty(computerVisionAccountName) ? computerVisionAccountName : '${abbrs.cognitiveServicesAccounts}viz${resourceToken}'
    location: empty(computerVisionLocation) ? location : computerVisionLocation
    kind: 'CognitiveServices'
    sku: {
      name: computerVisionSkuName
    }
  }
}

// Container apps host (including container registry)
module containerApps 'core/host/container-apps.bicep' = {
  name: 'container-apps'
  scope: resourceGroup
  params: {
    name: 'app'
    location: location
    tags: tags
    containerAppsEnvironmentName: '${resourceToken}-containerapps-env'
    containerRegistryName: '${replace(resourceToken, '-', '')}registry'
    logAnalyticsWorkspaceName: monitoring.outputs.logAnalyticsWorkspaceName
  }
}

// Container app frontend
module aca 'aca.bicep' = {
  name: 'aca'
  scope: resourceGroup
  params: {
    name: replace('ca-${take(resourceToken, 19)}', '--', '-')
    location: location
    tags: tags
    identityName: '${resourceToken}-id-aca'
    containerAppsEnvironmentName: containerApps.outputs.environmentName
    containerRegistryName: containerApps.outputs.registryName
    env: [
      {name: 'AZURE_SEARCH_INDEX'
        value: searchIndexName
      }
      {name: 'AZURE_SEARCH_SERVICE'
        value: searchService.outputs.name
      }
      {
        name: 'RUNNING_IN_PRODUCTION'
        value: 'true'
      }
    ]
    exists: acaExists
  }
}


// Frontend reader role to query index data:
module frontendSearchReaderRole 'core/security/role.bicep' = {
  scope: searchServiceResourceGroup
  name: 'frontend-search-reader-role'
  params: {
    principalId: aca.outputs.identityPrincipalId
    roleDefinitionId: '1407120a-92aa-4202-b7e9-c0e197c71c8f'
    principalType: 'ServicePrincipal'
  }
}

// Required for local development:
module userSearchReaderRole 'core/security/role.bicep' = {
  scope: searchServiceResourceGroup
  name: 'user-search-reader-role'
  params: {
    principalId: principalId
    roleDefinitionId: '1407120a-92aa-4202-b7e9-c0e197c71c8f'
    principalType: principalType
  }
}

module visionRoleSearchService 'core/security/role.bicep' = {
  scope: resourceGroup
  name: 'vision-role-searchservice'
  params: {
    principalId: searchService.outputs.principalId
    roleDefinitionId: 'a97b65f3-24c7-4388-baec-2e87135dc908'
    principalType: 'ServicePrincipal'
  }
}

output AZURE_RESOURCE_GROUP string = resourceGroup.name
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_SEARCH_SERVICE string = searchService.outputs.name
output AZURE_SEARCH_SERVICE_RESOURCE_GROUP string = searchServiceResourceGroup.name
output AZURE_SEARCH_SERVICE_LOCATION string = searchService.outputs.location
output AZURE_SEARCH_SERVICE_SKU string = searchService.outputs.sku
output AZURE_SEARCH_INDEX string = searchIndexName

output AZURE_STORAGE_ACCOUNT_ID string = storage.outputs.id
output AZURE_STORAGE_ACCOUNT_LOCATION string = storage.outputs.location
output AZURE_STORAGE_ACCOUNT_RESOURCE_GROUP string = storageResourceGroup.name
output AZURE_STORAGE_ACCOUNT string = storage.outputs.name
output AZURE_STORAGE_ACCOUNT_BLOB_URL string = storage.outputs.primaryBlobEndpoint
output AZURE_API_SERVICE_RESOURCE_GROUP string = apiServiceResourceGroup.name
output AZURE_LOG_ANALYTICS string = monitoring.outputs.logAnalyticsWorkspaceName
output AZURE_APPINSIGHTS string = monitoring.outputs.applicationInsightsName

output AZURE_COMPUTERVISION_ACCOUNT_URL string = computerVision.outputs.endpoint

output SERVICE_ACA_IDENTITY_PRINCIPAL_ID string = aca.outputs.identityPrincipalId
output SERVICE_ACA_NAME string = aca.outputs.name
output SERVICE_ACA_URI string = aca.outputs.uri
output SERVICE_ACA_IMAGE_NAME string = aca.outputs.imageName

output AZURE_CONTAINER_ENVIRONMENT_NAME string = containerApps.outputs.environmentName
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerApps.outputs.registryLoginServer
output AZURE_CONTAINER_REGISTRY_NAME string = containerApps.outputs.registryName
