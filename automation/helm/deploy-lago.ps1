# deploy-lago.ps1
# Deploy Lago to the VPS Kubernetes cluster using Helm (external DB/Redis).

$ErrorActionPreference = "Stop"

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$platformRoot = (Get-Item (Join-Path $scriptPath "..\..")).FullName
$workspaceRoot = (Get-Item (Join-Path $scriptPath "..\..\..")).FullName
$envPath = Join-Path $platformRoot ".env"
$secretsPath = Join-Path $platformRoot ".secrets.env"
$kubeconfigPath = Join-Path $workspaceRoot "VPS\kubeconfig.vps"
$valuesPath = Join-Path $scriptPath "lago-values.yaml"

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

$subUser = $envData["AM_SUBSCRIPTION_DB_USER"]
if (-not $subUser) { $subUser = "am_subscription_user" }

$subPassword = $envData["AM_SUBSCRIPTION_DB_PASSWORD"]
$subDb = $envData["AM_SUBSCRIPTION_DB_NAME"]
if (-not $subDb) { $subDb = "subscription" }

$pgHost = $envData["POSTGRES_HOST"]
if (-not $pgHost) { $pgHost = "postgresql.infra.svc.cluster.local" }

$redisHost = $envData["REDIS_HOST"]
if (-not $redisHost) { $redisHost = "redis.infra.svc.cluster.local" }

$redisUrl = $envData["LAGO_REDIS_URL"]
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
    $encodedPassword = [uri]::EscapeDataString($redisPassword)
    $redisUrl = "redis://:${encodedPassword}@${redisHost}:6379/0"
}

if (-not $subPassword) {
    Write-Error "Missing AM_SUBSCRIPTION_DB_PASSWORD in .secrets.env (run: npm run tf:billing:apply -w @am-platform/automation to provision DB and generate password)"
}

$databaseUrl = "postgresql://${subUser}:${subPassword}@${pgHost}:5432/${subDb}"

$lagoFrontHost = $envData["LAGO_HOSTNAME"]
if (-not $lagoFrontHost) { $lagoFrontHost = "lago.munish.org" }

$lagoApiHost = $envData["LAGO_API_HOSTNAME"]
if (-not $lagoApiHost) { $lagoApiHost = "lago-api.munish.org" }

$lagoFrontHostAsrax = $envData["LAGO_ASRAX_HOSTNAME"]
if (-not $lagoFrontHostAsrax) { $lagoFrontHostAsrax = "lago.asrax.in" }

$lagoApiHostAsrax = $envData["LAGO_ASRAX_API_HOSTNAME"]
if (-not $lagoApiHostAsrax) { $lagoApiHostAsrax = "lago-api.asrax.in" }

$lagoAmPathHost = $envData["LAGO_AM_PATH_HOST"]
if (-not $lagoAmPathHost) { $lagoAmPathHost = "am.asrax.in" }

$lagoScheme = $envData["LAGO_PUBLIC_SCHEME"]
if (-not $lagoScheme) { $lagoScheme = "https" }

$frontUrl = $envData["LAGO_FRONT_URL"]
if (-not $frontUrl) { $frontUrl = "${lagoScheme}://${lagoFrontHost}" }

$apiUrl = $envData["LAGO_API_URL"]
if (-not $apiUrl) { $apiUrl = $frontUrl }

$ingressPath = Join-Path $scriptPath "lago-ingress.yaml"
$adminValuesPath = Join-Path $scriptPath "lago-admin.generated.yaml"

$lagoAdminEmail = $envData["LAGO_ADMIN_EMAIL"]
if (-not $lagoAdminEmail) { $lagoAdminEmail = "billing-admin@munish.org" }

$lagoOrgName = $envData["LAGO_ORG_NAME"]
if (-not $lagoOrgName) { $lagoOrgName = "AM Platform" }

$lagoAdminPassword = $envData["LAGO_ADMIN_PASSWORD"]
if (-not $lagoAdminPassword) {
    $lagoAdminPassword = New-RandomHex -Length 24
    Write-Host "Generated new LAGO_ADMIN_PASSWORD and saving to .secrets.env"
}

$lagoOrgApiKey = $envData["LAGO_ORG_API_KEY"]
if (-not $lagoOrgApiKey) {
    $lagoOrgApiKey = "lago_$(New-RandomHex -Length 32)"
    Write-Host "Generated new LAGO_ORG_API_KEY and saving to .secrets.env"
}

Set-EnvFileValue -Path $envPath -Key "LAGO_ADMIN_EMAIL" -Value $lagoAdminEmail
Set-EnvFileValue -Path $envPath -Key "LAGO_ORG_NAME" -Value $lagoOrgName
Set-EnvFileValue -Path $envPath -Key "LAGO_ADMIN_UI_URL" -Value $frontUrl
Set-EnvFileValue -Path $secretsPath -Key "LAGO_ADMIN_PASSWORD" -Value $lagoAdminPassword
Set-EnvFileValue -Path $secretsPath -Key "LAGO_ORG_API_KEY" -Value $lagoOrgApiKey

$escapedPassword = $lagoAdminPassword -replace '"', '\"'
$escapedApiKey = $lagoOrgApiKey -replace '"', '\"'
$escapedEmail = $lagoAdminEmail -replace '"', '\"'
$escapedOrg = $lagoOrgName -replace '"', '\"'

@"
job:
  migrate:
    extraEnv:
      LAGO_CREATE_ORG: "false"
      LAGO_ORG_USER_EMAIL: "$escapedEmail"
      LAGO_ORG_USER_PASSWORD: "$escapedPassword"
      LAGO_ORG_NAME: "$escapedOrg"
      LAGO_ORG_API_KEY: "$escapedApiKey"
"@ | Set-Content -Path $adminValuesPath -Encoding utf8

Write-Host "Deploying Lago to namespace 'billing' on VPS..."
helm repo add lago https://charts.getlago.com 2>$null
helm repo update lago
if ($LASTEXITCODE -ne 0) {
    Write-Error "helm repo update failed"
}

helm upgrade --install lago lago/lago `
  --namespace billing `
  --create-namespace `
  --kubeconfig $kubeconfigPath `
  --no-hooks `
  -f $valuesPath `
  -f $adminValuesPath `
  --set global.databaseUrl=$databaseUrl `
  --set global.redisUrl=$redisUrl `
  --set global.redisCacheUrl=$redisUrl `
  --set apiUrl=$apiUrl `
  --set frontUrl=$frontUrl

if ($LASTEXITCODE -ne 0) {
    Write-Error "helm upgrade --install lago failed"
}

Write-Host "Applying Traefik ingress (UI: $frontUrl, API: $apiUrl)..."
$ingressManifest = Get-Content $ingressPath -Raw
$ingressManifest = $ingressManifest -replace 'lago\.munish\.org', $lagoFrontHost
$ingressManifest = $ingressManifest -replace 'lago-api\.munish\.org', $lagoApiHost
$ingressManifest = $ingressManifest -replace 'lago\.asrax\.in', $lagoFrontHostAsrax
$ingressManifest = $ingressManifest -replace 'lago-api\.asrax\.in', $lagoApiHostAsrax
$ingressManifest = $ingressManifest -replace 'am\.asrax\.in', $lagoAmPathHost
$ingressManifest | kubectl --kubeconfig $kubeconfigPath apply -f -

if ($LASTEXITCODE -ne 0) {
    Write-Error "kubectl apply lago-ingress failed"
}

Write-Host "Lago deployment completed successfully!"
Write-Host "Admin UI (munish):  $frontUrl"
Write-Host "Admin UI (asrax):   ${lagoScheme}://${lagoFrontHostAsrax}"
Write-Host "Admin UI (am path): ${lagoScheme}://${lagoAmPathHost}/lago"
Write-Host "API (munish):       $apiUrl"
Write-Host "API (asrax):        ${lagoScheme}://${lagoApiHostAsrax}"
Write-Host "Cloudflare DNS: lago.munish.org, lago-api.munish.org, lago.asrax.in, lago-api.asrax.in -> VPS IP."
Write-Host ""
Write-Host "Lago admin login (also in am-platform/.env and .secrets.env):"
Write-Host "  Email:    $lagoAdminEmail"
Write-Host "  Password: (see LAGO_ADMIN_PASSWORD in .secrets.env)"
Write-Host "  Org:      $lagoOrgName"
Write-Host "  API key:  (see LAGO_ORG_API_KEY in .secrets.env)"
