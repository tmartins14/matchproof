targetScope = 'resourceGroup'

param environmentName string
param budgetAmount int
param budgetEmail string

// Budgets must start on the first of a month.
param startDate string = utcNow('yyyy-MM-01T00:00:00Z')

resource budget 'Microsoft.Consumption/budgets@2024-08-01' = {
  name: 'budget-${environmentName}'
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: startDate
    }
    notifications: {
      actual80: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: [ budgetEmail ]
      }
      actual100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Actual'
        contactEmails: [ budgetEmail ]
      }
      forecast100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: [ budgetEmail ]
      }
    }
  }
}
