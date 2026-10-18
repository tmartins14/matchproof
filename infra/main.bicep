targetScope = 'subscription'

@minLength(1)
@maxLength(32)
@description('azd environment name; used in resource names and the resource group.')
param environmentName string

@description('Azure region for all resources.')
param location string

// --- Model (Microsoft Foundry) ------------------------------------------------
@description('Name of the Foundry deployment the API calls.')
param modelDeploymentName string = 'gpt-5-mini'

@description('Model name from the Foundry catalog.')
param modelName string = 'gpt-5-mini'

@description('Model version from the Foundry catalog.')
param modelVersion string = '2025-08-07'

@description('Deployment capacity in thousands of tokens per minute.')
param modelCapacity int = 50

// --- Budget -------------------------------------------------------------------
@description('Monthly budget in the subscription billing currency.')
param budgetAmount int = 50

@description('Email that receives budget alerts.')
param budgetEmail string

var tags = { 'azd-env-name': environmentName }
var token = take(uniqueString(subscription().id, environmentName), 8)

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  scope: rg
  params: {
    location: location
    tags: tags
    token: token
  }
}

module identity 'modules/identity.bicep' = {
  name: 'identity'
  scope: rg
  params: {
    location: location
    tags: tags
    token: token
  }
}

module registry 'modules/registry.bicep' = {
  name: 'registry'
  scope: rg
  params: {
    location: location
    tags: tags
    token: token
    principalId: identity.outputs.principalId
  }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  scope: rg
  params: {
    location: location
    tags: tags
    token: token
    principalId: identity.outputs.principalId
  }
}

module foundry 'modules/foundry.bicep' = {
  name: 'foundry'
  scope: rg
  params: {
    location: location
    tags: tags
    token: token
    principalId: identity.outputs.principalId
    modelDeploymentName: modelDeploymentName
    modelName: modelName
    modelVersion: modelVersion
    modelCapacity: modelCapacity
  }
}

module app 'modules/containerapp.bicep' = {
  name: 'containerapp'
  scope: rg
  params: {
    location: location
    tags: tags
    token: token
    identityId: identity.outputs.id
    identityClientId: identity.outputs.clientId
    logAnalyticsName: monitoring.outputs.logAnalyticsName
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    registryLoginServer: registry.outputs.loginServer
    storageAccountName: storage.outputs.accountName
    modelBaseUrl: foundry.outputs.modelBaseUrl
    modelDeploymentName: foundry.outputs.deploymentName
  }
}

module budget 'modules/budget.bicep' = {
  name: 'budget'
  scope: rg
  params: {
    environmentName: environmentName
    budgetAmount: budgetAmount
    budgetEmail: budgetEmail
  }
}

// azd reads these outputs into the environment.
output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.outputs.loginServer
output API_URL string = app.outputs.url
output MODEL_BASE_URL string = foundry.outputs.modelBaseUrl
output MODEL_DEPLOYMENT_NAME string = foundry.outputs.deploymentName
output APPLICATIONINSIGHTS_NAME string = monitoring.outputs.appInsightsName
