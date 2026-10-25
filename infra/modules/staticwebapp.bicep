param location string
param tags object
@minLength(8)
param token string

// azd finds this app by the azd-service-name tag and uploads apps/web/out to it. No repository is linked, so no token is stored.
resource web 'Microsoft.Web/staticSites@2025-03-01' = {
  name: 'swa-${token}'
  location: location
  tags: union(tags, { 'azd-service-name': 'web' })
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {}
}

output hostname string = web.properties.defaultHostname
