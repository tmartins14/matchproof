param location string
param tags object
@minLength(8)
param token string
param appInsightsName string
param webUrl string
param apiHealthUrl string
param alertEmail string

// Three regions, every 5 minutes (Learn: availability-standard tests, location population tags).
var locations = [
  { Id: 'us-va-ash-azr' }
  { Id: 'emea-nl-ams-azr' }
  { Id: 'apac-jp-kaw-edge' }
]

var targets = [
  { key: 'web', url: webUrl }
  { key: 'api', url: apiHealthUrl }
]

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-${token}'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'matchproof'
    enabled: true
    emailReceivers: [
      {
        name: 'owner'
        emailAddress: alertEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

resource tests 'Microsoft.Insights/webtests@2022-06-15' = [for target in targets: {
  name: 'avail-${target.key}-${token}'
  location: location
  kind: 'standard'
  tags: union(tags, { 'hidden-link:${appInsights.id}': 'Resource' })
  properties: {
    Name: 'avail-${target.key}-${token}'
    SyntheticMonitorId: 'avail-${target.key}-${token}'
    Description: 'Matchproof ${target.key}: GET ${target.url}'
    Enabled: true
    Frequency: 300
    Timeout: 30
    Kind: 'standard'
    RetryEnabled: true
    Locations: locations
    Request: {
      RequestUrl: target.url
      HttpVerb: 'GET'
      FollowRedirects: true
      ParseDependentRequests: false
    }
    ValidationRules: {
      ExpectedHttpStatusCode: 200
      SSLCheck: true
      SSLCertRemainingLifetimeCheck: 7
    }
  }
}]

// Two of the three locations failing in a 10-minute window, which holds two runs at a 5-minute frequency.
resource alerts 'Microsoft.Insights/metricAlerts@2018-03-01' = [for (target, i) in targets: {
  name: 'alert-${target.key}-${token}'
  location: 'global'
  tags: union(tags, {
    'hidden-link:${appInsights.id}': 'Resource'
    'hidden-link:${tests[i].id}': 'Resource'
  })
  properties: {
    description: 'Matchproof ${target.key} failed from at least two of three locations.'
    severity: 1
    enabled: true
    scopes: [
      tests[i].id
      appInsights.id
    ]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT10M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria'
      webTestId: tests[i].id
      componentId: appInsights.id
      failedLocationCount: 2
    }
    actions: [
      { actionGroupId: actionGroup.id }
    ]
  }
}]
