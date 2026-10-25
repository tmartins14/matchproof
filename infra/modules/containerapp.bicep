param location string
param tags object
@minLength(8)
param token string
param identityId string
param identityClientId string
param logAnalyticsName string
param appInsightsConnectionString string
param registryLoginServer string
param storageAccountName string
param modelBaseUrl string
param modelDeploymentName string
@description('Browser origins allowed by CORS, comma-separated. No localhost in production.')
param webOrigins string
@description('Replicas kept warm; 1 avoids the cold-start stall while judging.')
@minValue(0)
param minReplicas int

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2025-02-01' existing = {
  name: logAnalyticsName
}

resource environment 'Microsoft.App/managedEnvironments@2025-07-01' = {
  name: 'cae-${token}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// The app's public host name, which the MCP endpoint must accept (DNS-rebinding protection).
var apiName = 'ca-api-${token}'
var apiHost = '${apiName}.${environment.properties.defaultDomain}'

// azd replaces the placeholder image on `azd deploy`; the azd-service-name tag is how it finds this app.
resource api 'Microsoft.App/containerApps@2025-07-01' = {
  name: apiName
  location: location
  tags: union(tags, { 'azd-service-name': 'api' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityId}': {} }
  }
  properties: {
    environmentId: environment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          server: registryLoginServer
          identity: identityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          resources: {
            cpu: json('1')
            memory: '2Gi'
          }
          env: [
            { name: 'AZURE_CLIENT_ID', value: identityClientId }
            { name: 'MODEL_BASE_URL', value: modelBaseUrl }
            { name: 'MODEL_DEPLOYMENT_NAME', value: modelDeploymentName }
            { name: 'AZURE_STORAGE_ACCOUNT', value: storageAccountName }
            { name: 'MATCH_ARCHIVE', value: 'blob' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'OTEL_SERVICE_NAME', value: 'matchproof-api' }
            { name: 'MCP_ALLOWED_HOSTS', value: apiHost }
            { name: 'WEB_ORIGINS', value: webOrigins }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: 2
      }
    }
  }
}

output url string = 'https://${api.properties.configuration.ingress.fqdn}'
