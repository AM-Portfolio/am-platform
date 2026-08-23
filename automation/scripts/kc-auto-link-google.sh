#!/bin/sh
set -eu
export HOME=/tmp
K=/opt/bitnami/keycloak/bin/kcadm.sh
R=am-dev-realm
FLOW=first%20broker%20login%20auto-link

$K update "authentication/flows/${FLOW}/executions" -r "$R" -b '{"id":"e0735a02-ea4c-4346-9c31-fac28d22cc18","requirement":"DISABLED"}'
$K update "authentication/flows/${FLOW}/executions" -r "$R" -b '{"id":"f7770fd2-9008-4f73-985c-ec17e1efaf9d","requirement":"DISABLED"}'
$K update "authentication/flows/${FLOW}/executions" -r "$R" -b '{"id":"14d36441-68b3-4e43-81f6-a1512c257541","requirement":"DISABLED"}'

$K create "authentication/flows/${FLOW}%20Handle%20Existing%20Account/executions/execution" -r "$R" -b '{"provider":"idp-auto-link"}' || true

$K update identity-provider/instances/google -r "$R" -s 'firstBrokerLoginFlowAlias=first broker login auto-link' -s 'trustEmail=true'
echo DONE
