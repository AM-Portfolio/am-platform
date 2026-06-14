# deploy-mcp-gateway.ps1
# Deploy am-mcp-gateway to the VPS Kubernetes cluster using Helm.

$ErrorActionPreference = "Stop"

# Define Paths
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$platformRoot = (Get-Item (Join-Path $scriptPath "..\..")).FullName
$workspaceRoot = (Get-Item (Join-Path $scriptPath "..\..\..")).FullName
$kubeconfigPath = Join-Path $workspaceRoot "VPS\kubeconfig.vps"
$chartPath = Join-Path $workspaceRoot "am-pipelines\helm\universal-chart"
$valuesPath = Join-Path $platformRoot "am-mcp-gateway\helm\values.yaml"
$preprodValuesPath = Join-Path $platformRoot "am-mcp-gateway\helm\values.preprod.yaml"

if (-not (Test-Path $kubeconfigPath)) {
    Write-Error "Could not find kubeconfig at $kubeconfigPath"
}

if (-not (Test-Path $chartPath)) {
    Write-Error "Universal chart not found at $chartPath"
}

Write-Host "Deploying am-mcp-gateway to namespace 'am-apps-preprod' on VPS..."
helm upgrade --install am-mcp-gateway $chartPath `
  --namespace am-apps-preprod `
  --create-namespace `
  --kubeconfig $kubeconfigPath `
  -f $valuesPath `
  -f $preprodValuesPath

if ($LASTEXITCODE -ne 0) {
    Write-Error "helm upgrade --install am-mcp-gateway failed"
}

Write-Host "am-mcp-gateway deployment completed successfully!"
