#!/usr/bin/env bash
# Report whether the custom domain's CNAME resolves and Static Web Apps has validated the hostname.
# Usage: scripts/check_domain.sh [DOMAIN]   (default matchproof.tylermartins.com; needs an azd environment)
set -uo pipefail

DOMAIN="${1:-matchproof.tylermartins.com}"
WEB_HOST="$(azd env get-value WEB_URL | sed 's#^https://##')"
RG="$(azd env get-value AZURE_RESOURCE_GROUP)"
APP="$(az staticwebapp list -g "$RG" --query "[?defaultHostname=='$WEB_HOST'].name | [0]" -o tsv)"

status=0
cname="$(dig +short CNAME "$DOMAIN" | sed 's/\.$//')"
if [ "$cname" = "$WEB_HOST" ]; then
  echo "ok   CNAME $DOMAIN -> $cname"
else
  echo "FAIL CNAME $DOMAIN -> '${cname:-nothing}', expected $WEB_HOST"
  status=1
fi

state="$(az staticwebapp hostname show -n "$APP" -g "$RG" --hostname "$DOMAIN" --query status -o tsv 2>/dev/null)"
if [ "$state" = "Ready" ]; then
  echo "ok   hostname $DOMAIN is validated (Ready)"
else
  echo "FAIL hostname $DOMAIN status: ${state:-not added}"
  status=1
fi
exit $status
