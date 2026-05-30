# deploy-novu.ps1
# Deploy Novu to the VPS Kubernetes cluster using Helm (external Mongo/Redis on shared infra).

$ErrorActionPreference = "Stop"

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$platformRoot = (Get-Item (Join-Path $scriptPath "..\..")).FullName
$workspaceRoot = (Get-Item (Join-Path $scriptPath "..\..\..")).FullName
$envPath = Join-Path $platformRoot ".env"
$secretsPath = Join-Path $platformRoot ".secrets.env"
$kubeconfigPath = Join-Path $workspaceRoot "VPS\kubeconfig.vps"
$valuesPath = Join-Path $scriptPath "novu-values.yaml"
$ingressPath = Join-Path $scriptPath "novu-ingress.yaml"

if (-not (Test-Path $envPath)) {
    Write-Error "Could not find .env file at $envPath"
}

if (-not (Test-Path $kubeconfigPath)) {
    Write-Error "Could not find kubeconfig at $kubeconfigPath"
}

function Read-EnvFile {
    param([string]$Path)
    $data = @{}
    if (-not (Test-Path $Path)) { return $data }
    Get-Content $Path | Where-Object { $_ -match "^[^#\s]+=.*$" } | ForEach-Object {
        $parts = $_ -split "=", 2
        $data[$parts[0].Trim()] = $parts[1].Trim()
    }
    return $data
}

function Set-EnvFileValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )
    $lines = @()
    if (Test-Path $Path) {
        $lines = Get-Content $Path
    }
    $pattern = "^\s*$([regex]::Escape($Key))\s*="
    $replaced = $false
    $newLines = foreach ($line in $lines) {
        if ($line -match $pattern) {
            $replaced = $true
            "$Key=$Value"
        } else {
            $line
        }
    }
    if (-not $replaced) {
        if ($newLines.Count -gt 0 -and $newLines[-1] -ne "") {
            $newLines += ""
        }
        $newLines += "$Key=$Value"
    }
    Set-Content -Path $Path -Value $newLines -Encoding utf8
}

function New-RandomHex {
    param([int]$Length = 32)
    $bytes = New-Object byte[] ([math]::Ceiling($Length / 2))
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return ([BitConverter]::ToString($bytes) -replace '-', '').ToLower().Substring(0, $Length)
}

Write-Host "Loading environment configurations..."
$envData = Read-EnvFile $envPath
$secretsData = Read-EnvFile $secretsPath
foreach ($key in $secretsData.Keys) {
    $envData[$key] = $secretsData[$key]
}

$mongoHost = $envData["MONGODB_HOST"]
if (-not $mongoHost) { $mongoHost = "mongodb.infra.svc.cluster.local" }

$novuDbUser = $envData["NOVU_DB_USER"]
if (-not $novuDbUser) { $novuDbUser = "novu_user" }

$novuDbName = $envData["NOVU_DB_NAME"]
if (-not $novuDbName) { $novuDbName = "novu" }

$novuDbPassword = $envData["NOVU_DB_PASSWORD"]
if (-not $novuDbPassword) {
    Write-Error "Missing NOVU_DB_PASSWORD in .secrets.env (run: npm run tf:notification:apply)"
}

$encodedNovuPwd = [uri]::EscapeDataString($novuDbPassword)
$novuMongoUri = "mongodb://${novuDbUser}:${encodedNovuPwd}@${mongoHost}:27017/${novuDbName}?authSource=${novuDbName}"

$redisHost = $envData["REDIS_HOST"]
if (-not $redisHost) { $redisHost = "redis.infra.svc.cluster.local" }

$redisUrl = $envData["NOVU_REDIS_URL"]
if (-not $redisUrl) {
    $redisPassword = $envData["REDIS_PASSWORD"]
    if (-not $redisPassword) {
        Write-Host "REDIS_PASSWORD not in env files - reading from infra/redis-secret..."
        $jsonPath = '{.data.password}'
        $secretB64 = kubectl --kubeconfig $kubeconfigPath get secret redis-secret -n infra -o jsonpath=$jsonPath 2>$null
        if (-not $secretB64) {
            Write-Error "Missing REDIS_PASSWORD in .secrets.env and could not read infra/redis-secret"
        }
        $redisPassword = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($secretB64))
    }
    $encodedRedisPassword = [uri]::EscapeDataString($redisPassword)
    $redisUrl = "redis://:${encodedRedisPassword}@${redisHost}:6379/2"
} else {
    $redisPassword = $envData["REDIS_PASSWORD"]
    if (-not $redisPassword) {
        Write-Host "REDIS_PASSWORD not in env files - reading from infra/redis-secret..."
        $jsonPath = '{.data.password}'
        $secretB64 = kubectl --kubeconfig $kubeconfigPath get secret redis-secret -n infra -o jsonpath=$jsonPath 2>$null
        if (-not $secretB64) {
            Write-Error "Missing REDIS_PASSWORD in .secrets.env and could not read infra/redis-secret"
        }
        $redisPassword = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($secretB64))
    }
}

$chartPath = Join-Path $scriptPath "novu"
if (-not (Test-Path $chartPath)) {
    Write-Error "Local Novu chart not found at $chartPath (run: helm pull oci://ghcr.io/nova-edge/novu-chart/novu --version 0.1.0 -d automation/helm && tar -xf automation/helm/novu-0.1.0.tgz -C automation/helm)"
}

$novuHost = $envData["NOVU_HOSTNAME"]
if (-not $novuHost) { $novuHost = "novu.munish.org" }

$novuApiHost = $envData["NOVU_API_HOSTNAME"]
if (-not $novuApiHost) { $novuApiHost = "novu-api.munish.org" }

$novuAsraxHost = $envData["NOVU_ASRAX_HOSTNAME"]
if (-not $novuAsraxHost) { $novuAsraxHost = "novu.asrax.in" }

$novuScheme = $envData["NOVU_PUBLIC_SCHEME"]
if (-not $novuScheme) { $novuScheme = "https" }

$novuApiUrl = $envData["NOVU_API_URL"]
if (-not $novuApiUrl) { $novuApiUrl = "${novuScheme}://${novuApiHost}" }

$novuFrontUrl = $envData["NOVU_FRONT_URL"]
if (-not $novuFrontUrl) { $novuFrontUrl = "${novuScheme}://${novuHost}" }

$jwtSecret = $envData["NOVU_JWT_SECRET"]
if (-not $jwtSecret) {
    $jwtSecret = New-RandomHex -Length 32
    Write-Host "Generated new NOVU_JWT_SECRET"
}

$storageKey = $envData["NOVU_STORAGE_KEY"]
if (-not $storageKey) {
    $storageKey = (New-RandomHex -Length 16) + (New-RandomHex -Length 16)
    Write-Host "Generated new NOVU_STORAGE_KEY"
}

$novuApiKey = $envData["NOVU_API_KEY"]
if (-not $novuApiKey) {
    Write-Host "NOVU_API_KEY not set — copy Production API key from Novu dashboard (Settings -> API Keys) into .secrets.env"
} else {
    Set-EnvFileValue -Path $secretsPath -Key "NOVU_API_KEY" -Value $novuApiKey
}

Set-EnvFileValue -Path $envPath -Key "NOVU_HOSTNAME" -Value $novuHost
Set-EnvFileValue -Path $envPath -Key "NOVU_API_HOSTNAME" -Value $novuApiHost
Set-EnvFileValue -Path $envPath -Key "NOVU_ASRAX_HOSTNAME" -Value $novuAsraxHost
Set-EnvFileValue -Path $envPath -Key "NOVU_API_URL" -Value $novuApiUrl
Set-EnvFileValue -Path $envPath -Key "NOVU_FRONT_URL" -Value $novuFrontUrl
Set-EnvFileValue -Path $secretsPath -Key "NOVU_JWT_SECRET" -Value $jwtSecret
Set-EnvFileValue -Path $secretsPath -Key "NOVU_STORAGE_KEY" -Value $storageKey
Set-EnvFileValue -Path $secretsPath -Key "NOVU_MONGO_URI" -Value $novuMongoUri
Set-EnvFileValue -Path $secretsPath -Key "NOVU_REDIS_URL" -Value $redisUrl

Write-Host "Deploying Novu to namespace 'notification' (external Mongo/Redis on shared infra)..."
if ($LASTEXITCODE -ne 0) { $LASTEXITCODE = 0 }

helm upgrade --install novu $chartPath `
  --namespace notification `
  --create-namespace `
  --kubeconfig $kubeconfigPath `
  -f $valuesPath `
  --set global.env.secret.jwtSecret=$jwtSecret `
  --set global.env.secret.storageKey=$storageKey `
  --set global.env.apiRootUrl=$novuApiUrl `
  --set global.env.frontBaseUrl=$novuFrontUrl `
  --set global.env.wsRootUrl=$novuFrontUrl `
  --set global.env.disableUserRegistration=true `
  --set externalDataStores.enabled=true `
  --set externalDataStores.mongoUrl=$novuMongoUri `
  --set externalDataStores.redisHost=$redisHost `
  --set externalDataStores.redisPort=6379 `
  --set externalDataStores.redisPassword=$redisPassword

if ($LASTEXITCODE -ne 0) {
    Write-Error "helm upgrade --install novu failed"
}

Write-Host "Applying Traefik ingress (UI: $novuFrontUrl, API: $novuApiUrl)..."
$ingressManifest = Get-Content $ingressPath -Raw
$ingressManifest = $ingressManifest -replace 'novu\.munish\.org', $novuHost
$ingressManifest = $ingressManifest -replace 'novu-api\.munish\.org', $novuApiHost
$ingressManifest = $ingressManifest -replace 'novu\.asrax\.in', $novuAsraxHost
$ingressManifest | kubectl --kubeconfig $kubeconfigPath apply -f -

if ($LASTEXITCODE -ne 0) {
    Write-Error "kubectl apply novu-ingress failed"
}

Write-Host "Novu deployment completed successfully!"
Write-Host "Dashboard (munish):  $novuFrontUrl"
Write-Host "Dashboard (asrax):   ${novuScheme}://${novuAsraxHost}"
Write-Host "API:                 $novuApiUrl"
Write-Host "NOVU_API_KEY:        (see .secrets.env)"
Write-Host ""
Write-Host "Next: npm run tf:notification:apply - sync workflows from novu-workflows.json"
