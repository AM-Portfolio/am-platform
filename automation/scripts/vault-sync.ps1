<#
.SYNOPSIS
    Synchronises environment-specific secrets from a .secrets.{env}.env file
    into HashiCorp Vault under the canonical 'apps/{env}/...' path schema.

.DESCRIPTION
    Reads the target .secrets.{env}.env, groups variables by their logical
    service/infra domain, and writes each group as a separate Vault KV secret.
    Performs a read-back verification after each write.

    Also migrates the legacy 'secret/...' paths by writing the same values
    to the canonical path (additive — does NOT delete old paths automatically).

.PARAMETER Env
    Target environment: dev | preprod | prod

.PARAMETER VaultAddr
    Vault address (default: http://localhost:8201)

.PARAMETER SecretsDir
    Directory containing the .secrets.{env}.env files.
    Defaults to the am-platform root two levels above this script.

.PARAMETER DryRun
    Show what would be written without actually writing to Vault.

.EXAMPLE
    .\vault-sync.ps1 -Env preprod
    .\vault-sync.ps1 -Env prod -DryRun
    .\vault-sync.ps1 -Env dev -VaultAddr http://vault.internal:8200
#>

param(
    [Parameter(Mandatory)]
    [ValidateSet("dev", "preprod", "prod")]
    [string]$Env,

    [string]$VaultAddr = "http://localhost:8201",

    [string]$SecretsDir = "",

    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Resolve paths ─────────────────────────────────────────────────────────────
if (-not $SecretsDir) {
    # Script lives at: automation/scripts/vault-sync.ps1
    # Secrets live at: am-platform/.secrets.{env}.env
    $SecretsDir = Join-Path $PSScriptRoot "..\.."
}

$EnvFile = Join-Path $SecretsDir ".secrets.$Env.env"
if (-not (Test-Path $EnvFile)) {
    Write-Error "Secrets file not found: $EnvFile"
    exit 1
}

$env:VAULT_ADDR = $VaultAddr

Write-Host "`n[vault-sync] Environment : $Env" -ForegroundColor Cyan
Write-Host "[vault-sync] Vault addr  : $VaultAddr" -ForegroundColor Cyan
Write-Host "[vault-sync] Secrets file: $EnvFile" -ForegroundColor Cyan
if ($DryRun) { Write-Host "[vault-sync] DRY RUN — no writes will occur" -ForegroundColor Yellow }

# ── Parse .env file into a hashtable ─────────────────────────────────────────
function Read-EnvFile([string]$Path) {
    $map = @{}
    foreach ($line in Get-Content $Path) {
        $line = $line.Trim()
        if ($line -match '^\s*#' -or $line -eq '') { continue }
        if ($line -match '^([^=]+)=(.*)$') {
            $map[$Matches[1].Trim()] = $Matches[2].Trim()
        }
    }
    return $map
}

# ── Write a single KV secret to Vault ────────────────────────────────────────
function Write-VaultSecret([string]$Path, [hashtable]$Data) {
    $kvPairs = ($Data.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join " "
    Write-Host "`n  >> vault kv put $Path [$(($Data.Keys) -join ', ')]" -ForegroundColor Yellow
    if (-not $DryRun) {
        $cmd = "vault kv put $Path $kvPairs"
        Invoke-Expression $cmd
    }
}

# ── Verify a path was written ─────────────────────────────────────────────────
function Test-VaultSecret([string]$Path) {
    if ($DryRun) { return }
    $result = vault kv get -format=json $Path 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "  [WARN] Verification failed for: $Path"
    } else {
        Write-Host "  [OK] Verified: $Path" -ForegroundColor Green
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
$secrets = Read-EnvFile $EnvFile
$base     = "apps/$Env"

Write-Host "`n[vault-sync] Starting sync for env=$Env ..." -ForegroundColor Cyan

# ── 1. Keycloak / OIDC ───────────────────────────────────────────────────────
$path = "$base/services/am-keycloak"
Write-VaultSecret $path @{
    KEYCLOAK_URL              = $secrets["KEYCLOAK_URL"]
    KEYCLOAK_ADMIN_USER       = $secrets["KEYCLOAK_ADMIN_USER"]
    KEYCLOAK_ADMIN_PASSWORD   = $secrets["KEYCLOAK_ADMIN_PASSWORD"]
    KEYCLOAK_REALM            = $secrets["KEYCLOAK_REALM"]
    OIDC_DISCOVERY_URL        = $secrets["OIDC_DISCOVERY_URL"]
    OIDC_ISSUER               = $secrets["OIDC_ISSUER"]
    OIDC_JWKS_URL             = $secrets["OIDC_JWKS_URL"]
    OIDC_TOKEN_URL            = $secrets["OIDC_TOKEN_URL"]
    GOOGLE_CLIENT_ID          = $secrets["GOOGLE_CLIENT_ID"]
    GOOGLE_CLIENT_SECRET      = $secrets["GOOGLE_CLIENT_SECRET"]
    ALLOWED_GOOGLE_REDIRECT_URIS = $secrets["ALLOWED_GOOGLE_REDIRECT_URIS"]
}
Test-VaultSecret $path

# ── 2. am-identity-service ───────────────────────────────────────────────────
$path = "$base/services/am-identity"
Write-VaultSecret $path @{
    AM_IDENTITY_CLIENT_ID     = $secrets["AM_IDENTITY_CLIENT_ID"]
    AM_IDENTITY_CLIENT_SECRET = $secrets["AM_IDENTITY_CLIENT_SECRET"]
    KEYCLOAK_URL              = $secrets["KEYCLOAK_URL"]
    KEYCLOAK_REALM            = $secrets["KEYCLOAK_REALM"]
    OIDC_DISCOVERY_URL        = $secrets["OIDC_DISCOVERY_URL"]
    OIDC_ISSUER               = $secrets["OIDC_ISSUER"]
    OIDC_JWKS_URL             = $secrets["OIDC_JWKS_URL"]
    OIDC_TOKEN_URL            = $secrets["OIDC_TOKEN_URL"]
    GOOGLE_CLIENT_ID          = $secrets["GOOGLE_CLIENT_ID"]
    GOOGLE_CLIENT_SECRET      = $secrets["GOOGLE_CLIENT_SECRET"]
    ALLOWED_GOOGLE_REDIRECT_URIS = $secrets["ALLOWED_GOOGLE_REDIRECT_URIS"]
    AM_MCP_CLIENT_ID          = $secrets["AM_MCP_CLIENT_ID"]
    AM_MCP_CLIENT_SECRET      = $secrets["AM_MCP_CLIENT_SECRET"]
}
Test-VaultSecret $path

# ── 3. am-gateway-client ─────────────────────────────────────────────────────
$path = "$base/services/am-gateway"
Write-VaultSecret $path @{
    AM_GATEWAY_CLIENT_ID             = $secrets["AM_GATEWAY_CLIENT_ID"]
    AM_GATEWAY_CLIENT_SECRET         = $secrets["AM_GATEWAY_CLIENT_SECRET"]
    AM_GATEWAY_STREAMING_CLIENT_ID   = $secrets["AM_GATEWAY_STREAMING_CLIENT_ID"]
    AM_GATEWAY_STREAMING_CLIENT_SECRET = $secrets["AM_GATEWAY_STREAMING_CLIENT_SECRET"]
    OIDC_ISSUER                      = $secrets["OIDC_ISSUER"]
    OIDC_JWKS_URL                    = $secrets["OIDC_JWKS_URL"]
}
Test-VaultSecret $path

# ── 4. am-subscription-service ───────────────────────────────────────────────
$path = "$base/services/am-subscription"
Write-VaultSecret $path @{
    AM_SUBSCRIPTION_CLIENT_ID     = $secrets["AM_SUBSCRIPTION_CLIENT_ID"]
    AM_SUBSCRIPTION_CLIENT_SECRET = $secrets["AM_SUBSCRIPTION_CLIENT_SECRET"]
    AM_SUBSCRIPTION_DB_PASSWORD   = $secrets["AM_SUBSCRIPTION_DB_PASSWORD"]
    OIDC_ISSUER                   = $secrets["OIDC_ISSUER"]
    OIDC_JWKS_URL                 = $secrets["OIDC_JWKS_URL"]
}
Test-VaultSecret $path

# ── 5. am-notification-service ───────────────────────────────────────────────
$path = "$base/services/am-notification"
Write-VaultSecret $path @{
    AM_NOTIFICATION_CLIENT_ID     = $secrets["AM_NOTIFICATION_CLIENT_ID"]
    AM_NOTIFICATION_CLIENT_SECRET = $secrets["AM_NOTIFICATION_CLIENT_SECRET"]
    AM_NOTIFICATION_DB_PASSWORD   = $secrets["AM_NOTIFICATION_DB_PASSWORD"]
    NOVU_JWT_SECRET               = $secrets["NOVU_JWT_SECRET"]
    NOVU_STORAGE_KEY              = $secrets["NOVU_STORAGE_KEY"]
    NOVU_API_KEY                  = $secrets["NOVU_API_KEY"]
    NOVU_DEV_API_KEY              = $secrets["NOVU_DEV_API_KEY"]
    NOVU_DEV_ENVIRONMENT_ID       = $secrets["NOVU_DEV_ENVIRONMENT_ID"]
    NOVU_ADMIN_EMAIL              = $secrets["NOVU_ADMIN_EMAIL"]
    NOVU_ADMIN_PASSWORD           = $secrets["NOVU_ADMIN_PASSWORD"]
    NOVU_MONGO_URI                = $secrets["NOVU_MONGO_URI"]
    NOVU_REDIS_URL                = $secrets["NOVU_REDIS_URL"]
    OIDC_ISSUER                   = $secrets["OIDC_ISSUER"]
    OIDC_JWKS_URL                 = $secrets["OIDC_JWKS_URL"]
}
Test-VaultSecret $path

# ── 6. am-lago (billing) ─────────────────────────────────────────────────────
$path = "$base/services/am-lago"
Write-VaultSecret $path @{
    LAGO_CLIENT_ID        = $secrets["LAGO_CLIENT_ID"]
    LAGO_CLIENT_SECRET    = $secrets["LAGO_CLIENT_SECRET"]
    LAGO_ADMIN_PASSWORD   = $secrets["LAGO_ADMIN_PASSWORD"]
    LAGO_ORG_API_KEY      = $secrets["LAGO_ORG_API_KEY"]
}
Test-VaultSecret $path

# ── 7. Phase 5 billing clients ───────────────────────────────────────────────
$path = "$base/services/am-billing-clients"
Write-VaultSecret $path @{
    ANALYSIS_CLIENT_ID      = $secrets["ANALYSIS_CLIENT_ID"]
    ANALYSIS_CLIENT_SECRET  = $secrets["ANALYSIS_CLIENT_SECRET"]
    MARKET_CLIENT_ID        = $secrets["MARKET_CLIENT_ID"]
    MARKET_CLIENT_SECRET    = $secrets["MARKET_CLIENT_SECRET"]
    MARKET_DATA_CLIENT_ID   = $secrets["MARKET_DATA_CLIENT_ID"]
    MARKET_DATA_CLIENT_SECRET = $secrets["MARKET_DATA_CLIENT_SECRET"]
    PARSER_CLIENT_ID        = $secrets["PARSER_CLIENT_ID"]
    PARSER_CLIENT_SECRET    = $secrets["PARSER_CLIENT_SECRET"]
    DOC_A_CLIENT_ID         = $secrets["DOC_A_CLIENT_ID"]
    DOC_A_CLIENT_SECRET     = $secrets["DOC_A_CLIENT_SECRET"]
    DOC_B_CLIENT_ID         = $secrets["DOC_B_CLIENT_ID"]
    DOC_B_CLIENT_SECRET     = $secrets["DOC_B_CLIENT_SECRET"]
    DOC_C_CLIENT_ID         = $secrets["DOC_C_CLIENT_ID"]
    DOC_C_CLIENT_SECRET     = $secrets["DOC_C_CLIENT_SECRET"]
    AM_MCP_CLIENT_ID        = $secrets["AM_MCP_CLIENT_ID"]
    AM_MCP_CLIENT_SECRET    = $secrets["AM_MCP_CLIENT_SECRET"]
    AM_FIN_AGENT_CLIENT_ID  = $secrets["AM_FIN_AGENT_CLIENT_ID"]
    AM_FIN_AGENT_CLIENT_SECRET = $secrets["AM_FIN_AGENT_CLIENT_SECRET"]
}
Test-VaultSecret $path

# ── 8. Infra: Postgres ───────────────────────────────────────────────────────
$path = "$base/infra/postgres"
Write-VaultSecret $path @{
    host         = $secrets["POSTGRES_HOST"]
    username     = $secrets["POSTGRES_USER"]
    password     = $secrets["POSTGRES_PASSWORD"]
    database     = $secrets["POSTGRES_DB"]
    DATABASE_URL = "postgresql://$($secrets['POSTGRES_USER']):$($secrets['POSTGRES_PASSWORD'])@$($secrets['POSTGRES_HOST']):5432/$($secrets['POSTGRES_DB'])"
    url          = "postgresql://$($secrets['POSTGRES_USER']):$($secrets['POSTGRES_PASSWORD'])@$($secrets['POSTGRES_HOST']):5432/$($secrets['POSTGRES_DB'])"
    port         = "5432"
}
Test-VaultSecret $path

# ── 9. Infra: MongoDB ────────────────────────────────────────────────────────
$path = "$base/infra/mongodb"
Write-VaultSecret $path @{
    host     = $secrets["MONGODB_HOST"]
    username = $secrets["MONGODB_ADMIN_USER"]
    password = $secrets["MONGODB_ADMIN_PASSWORD"]
    port     = "27017"
    url      = "mongodb://$($secrets['MONGODB_ADMIN_USER']):$($secrets['MONGODB_ADMIN_PASSWORD'])@$($secrets['MONGODB_HOST']):27017/?authSource=admin&directConnection=true"
}
Test-VaultSecret $path

# ── 10. Infra: Kafka ─────────────────────────────────────────────────────────
$path = "$base/infra/kafka"
Write-VaultSecret $path @{
    username          = $secrets["KAFKA_USERNAME"]
    password          = $secrets["KAFKA_PASSWORD"]
    bootstrap_servers = "kafka.infra.svc.cluster.local:9092"
}
Test-VaultSecret $path

# ─────────────────────────────────────────────────────────────────────────────
Write-Host "`n[vault-sync] All secrets synced to Vault for env=$Env" -ForegroundColor Green
Write-Host "[vault-sync] Canonical base path: $base" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Verify: vault kv list $base/services/" -ForegroundColor Gray
Write-Host "  2. Verify: vault kv list $base/infra/" -ForegroundColor Gray
Write-Host "  3. After confirming all services work, legacy 'secret/$Env/...' paths can be removed." -ForegroundColor Gray
