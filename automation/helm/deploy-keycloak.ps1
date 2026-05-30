# deploy-keycloak.ps1
# PowerShell script to deploy Keycloak to the VPS Kubernetes cluster using Helm.

$ErrorActionPreference = "Stop"

# Define Paths
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$platformRoot = (Get-Item (Join-Path $scriptPath "..\..")).FullName
$workspaceRoot = (Get-Item (Join-Path $scriptPath "..\..\..")).FullName
$envPath = Join-Path $platformRoot ".env"
$kubeconfigPath = Join-Path $workspaceRoot "VPS\kubeconfig.vps"
$valuesPath = Join-Path $scriptPath "keycloak-values.yaml"

if (-not (Test-Path $envPath)) {
    Write-Error "Could not find .env file at $envPath"
}

if (-not (Test-Path $kubeconfigPath)) {
    Write-Error "Could not find kubeconfig at $kubeconfigPath"
}

Write-Host "Loading environment configurations..."
$envData = @{}
Get-Content $envPath | Where-Object { $_ -match "^[^#\s]+=.*$" } | ForEach-Object {
    $parts = $_ -split "=", 2
    $key = $parts[0].Trim()
    $val = $parts[1].Trim()
    $envData[$key] = $val
}

$adminUser = $envData["KEYCLOAK_ADMIN_USER"]
$adminPassword = $envData["KEYCLOAK_ADMIN_PASSWORD"]
$dbPassword = $envData["POSTGRES_PASSWORD"]
$dbUser = $envData["POSTGRES_USER"]
$dbDatabase = $envData["POSTGRES_DB"]
$dbHost = $envData["POSTGRES_HOST"]
$hostname = $envData["KEYCLOAK_HOSTNAME"]

if (-not $adminUser -or -not $adminPassword -or -not $dbPassword -or -not $hostname) {
    Write-Error "Missing required parameters in .env file"
}

Write-Host "Deploying Keycloak to namespace 'identity' on VPS..."
helm upgrade --install keycloak oci://registry-1.docker.io/bitnamicharts/keycloak `
  --namespace identity `
  --kubeconfig $kubeconfigPath `
  -f $valuesPath `
  --set auth.adminUser=$adminUser `
  --set auth.adminPassword=$adminPassword `
  --set externalDatabase.user=$dbUser `
  --set externalDatabase.password=$dbPassword `
  --set externalDatabase.database=$dbDatabase `
  --set externalDatabase.host=$dbHost

Write-Host "Deployment command completed successfully!"
