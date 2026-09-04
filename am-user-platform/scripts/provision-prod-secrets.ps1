<#
.SYNOPSIS
  Register am-user-platform in Keycloak (verify) + Vault + Postgres for prod.
  Prints only status lines — never secret values.
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ClientId = "am-user-platform-service"
$ClientUuid = "8e0fa780-ec7c-48e6-96a0-e07e3a980bac"
$Realm = "am-realm"
$DbName = "am_user_platform_prod"
$DbUser = "am_user_platform_user_prod"
$Kubeconfig = Join-Path $env:USERPROFILE ".asrax\kubeconfig.vps"
$CredsFile = Join-Path $env:USERPROFILE ".asrax\credentials.env"
$VaultServicePath = "secret/prod/services/am-user-platform"
$VaultPostgresPath = "apps/prod/infra/postgres"

function Read-CredMap([string]$Path) {
  $map = @{}
  foreach ($line in Get-Content $Path) {
    $t = $line.Trim()
    if ($t -match '^\s*#' -or $t -eq '' -or $t -notmatch '=') { continue }
    $k, $v = $t.Split('=', 2)
    $map[$k.Trim()] = $v.Trim().Trim('"')
  }
  return $map
}

function Write-JsonNoBom([string]$Path, [hashtable]$Data) {
  $json = $Data | ConvertTo-Json -Compress
  $utf8 = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($Path, $json, $utf8)
}

function Status([string]$msg) { Write-Host "[ok] $msg" -ForegroundColor Green }
function Fail([string]$msg) { Write-Host "[fail] $msg" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $CredsFile)) { Fail "Missing $CredsFile" }
if (-not (Test-Path $Kubeconfig)) { Fail "Missing $Kubeconfig" }

$creds = Read-CredMap $CredsFile
foreach ($req in @('VAULT_ADDR', 'VAULT_TOKEN', 'KEYCLOAK_URL', 'KEYCLOAK_ADMIN', 'KEYCLOAK_ADMIN_PASSWORD')) {
  if (-not $creds.ContainsKey($req) -or [string]::IsNullOrWhiteSpace($creds[$req])) {
    Fail "credentials.env missing $req"
  }
}
$env:VAULT_ADDR = $creds['VAULT_ADDR']
$env:VAULT_TOKEN = $creds['VAULT_TOKEN']

# ── Keycloak: admin token + client secret ────────────────────────────────────
$kcBase = $creds['KEYCLOAK_URL'].TrimEnd('/')
$tokenBody = @{
  grant_type = 'password'
  client_id  = 'admin-cli'
  username   = $creds['KEYCLOAK_ADMIN']
  password   = $creds['KEYCLOAK_ADMIN_PASSWORD']
}
$tokenResp = Invoke-RestMethod -Method Post -Uri "$kcBase/realms/master/protocol/openid-connect/token" -Body $tokenBody -ContentType 'application/x-www-form-urlencoded'
$headers = @{ Authorization = "Bearer $($tokenResp.access_token)" }

# Align client flags with am-subscription-service
$client = Invoke-RestMethod -Method Get -Uri "$kcBase/admin/realms/$Realm/clients/$ClientUuid" -Headers $headers
$client.directAccessGrantsEnabled = $false
$client.standardFlowEnabled = $false
$client.serviceAccountsEnabled = $true
$client.publicClient = $false
if ($null -ne ($client.PSObject.Properties['description'])) {
  $client.description = 'Internal service client for user platform (AI sessions/feedback)'
} else {
  $client | Add-Member -NotePropertyName description -NotePropertyValue 'Internal service client for user platform (AI sessions/feedback)' -Force
}
Invoke-RestMethod -Method Put -Uri "$kcBase/admin/realms/$Realm/clients/$ClientUuid" -Headers $headers -ContentType 'application/json' -Body ($client | ConvertTo-Json -Depth 20) | Out-Null
Status "Keycloak client $ClientId updated (service-account, no direct grant)"

$secretResp = Invoke-RestMethod -Method Get -Uri "$kcBase/admin/realms/$Realm/clients/$ClientUuid/client-secret" -Headers $headers
$clientSecret = $secretResp.value
if ([string]::IsNullOrWhiteSpace($clientSecret)) { Fail 'Empty Keycloak client secret' }
Status 'Keycloak client secret retrieved'

# ── Generate DB password + optional SERVICE_TOKEN ────────────────────────────
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
function New-Hex([int]$bytes) {
  $buf = New-Object byte[] $bytes
  $rng.GetBytes($buf)
  return ([BitConverter]::ToString($buf) -replace '-', '').ToLowerInvariant()
}
$dbPassword = New-Hex 24
$serviceToken = New-Hex 32

# ── Vault: service secret ────────────────────────────────────────────────────
$tmp = Join-Path $env:TEMP "am-user-platform-vault.json"
Write-JsonNoBom $tmp @{
  AM_USER_PLATFORM_CLIENT_ID     = $ClientId
  AM_USER_PLATFORM_CLIENT_SECRET = $clientSecret
  SERVICE_TOKEN                  = $serviceToken
}
try {
  & vault kv put $VaultServicePath ("@" + $tmp)
  if ($LASTEXITCODE -ne 0) { Fail "vault kv put $VaultServicePath failed" }
  Status "Vault wrote $VaultServicePath (keys only: CLIENT_ID, CLIENT_SECRET, SERVICE_TOKEN)"
}
finally {
  Remove-Item -Force -ErrorAction SilentlyContinue $tmp
}

# ── Vault: patch postgres keys (merge) ───────────────────────────────────────
$tmpPg = Join-Path $env:TEMP "am-user-platform-pg-patch.json"
Write-JsonNoBom $tmpPg @{
  AM_USER_PLATFORM_DB_NAME     = $DbName
  AM_USER_PLATFORM_DB_USER     = $DbUser
  AM_USER_PLATFORM_DB_PASSWORD = $dbPassword
}
try {
  & vault kv patch $VaultPostgresPath ("@" + $tmpPg)
  if ($LASTEXITCODE -ne 0) {
    # Older vault may lack patch — merge manually
    $existing = vault kv get -format=json $VaultPostgresPath | ConvertFrom-Json
    $merged = @{}
    foreach ($p in $existing.data.data.PSObject.Properties) { $merged[$p.Name] = [string]$p.Value }
    $merged['AM_USER_PLATFORM_DB_NAME'] = $DbName
    $merged['AM_USER_PLATFORM_DB_USER'] = $DbUser
    $merged['AM_USER_PLATFORM_DB_PASSWORD'] = $dbPassword
    Write-JsonNoBom $tmpPg $merged
    & vault kv put $VaultPostgresPath ("@" + $tmpPg)
    if ($LASTEXITCODE -ne 0) { Fail "vault put/patch postgres failed" }
  }
  Status "Vault patched $VaultPostgresPath with AM_USER_PLATFORM_DB keys"
}
finally {
  Remove-Item -Force -ErrorAction SilentlyContinue $tmpPg
}

# Verify key presence only
$svcKeys = (vault kv get -format=json $VaultServicePath | ConvertFrom-Json).data.data.PSObject.Properties.Name
$pgKeys = (vault kv get -format=json $VaultPostgresPath | ConvertFrom-Json).data.data.PSObject.Properties.Name
foreach ($k in @('AM_USER_PLATFORM_CLIENT_ID', 'AM_USER_PLATFORM_CLIENT_SECRET', 'SERVICE_TOKEN')) {
  if ($svcKeys -notcontains $k) { Fail "Missing service key $k" }
}
foreach ($k in @('AM_USER_PLATFORM_DB_NAME', 'AM_USER_PLATFORM_DB_USER', 'AM_USER_PLATFORM_DB_PASSWORD', 'host', 'port')) {
  if ($pgKeys -notcontains $k) { Fail "Missing postgres key $k" }
}
Status 'Vault verification: required keys present'

# ── Postgres: create role + database via kubectl (stdin; no kubectl cp) ───────
$pgAdminPass = (vault kv get -format=json $VaultPostgresPath | ConvertFrom-Json).data.data.password
$pgAdminUser = (vault kv get -format=json $VaultPostgresPath | ConvertFrom-Json).data.data.username
if ([string]::IsNullOrWhiteSpace($pgAdminPass)) { Fail 'Vault postgres admin password missing' }

function Invoke-Psql([string]$Database, [string]$Sql) {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = "kubectl"
  $psi.Arguments = "--kubeconfig `"$Kubeconfig`" -n infra exec -i postgresql-0 -c postgresql -- env PGPASSWORD=$pgAdminPass psql -U $pgAdminUser -d $Database -v ON_ERROR_STOP=1 -t -A"
  $psi.RedirectStandardInput = $true
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.UseShellExecute = $false
  $p = [System.Diagnostics.Process]::Start($psi)
  $p.StandardInput.Write($Sql)
  $p.StandardInput.Close()
  $stdout = $p.StandardOutput.ReadToEnd()
  $stderr = $p.StandardError.ReadToEnd()
  $p.WaitForExit()
  if ($p.ExitCode -ne 0) {
    Fail "psql failed on $Database : $stderr $stdout"
  }
  return $stdout.Trim()
}

$roleSql = @"
DO `$`$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$DbUser') THEN
    CREATE ROLE $DbUser WITH LOGIN PASSWORD '$dbPassword';
  ELSE
    ALTER ROLE $DbUser WITH PASSWORD '$dbPassword';
  END IF;
END
`$`$;
"@
Invoke-Psql "postgres" $roleSql | Out-Null
Status "Postgres role $DbUser ensured"

$dbExists = Invoke-Psql "postgres" "SELECT count(*) FROM pg_database WHERE datname = '$DbName';"
if ($dbExists -eq '0') {
  Invoke-Psql "postgres" "CREATE DATABASE $DbName OWNER $DbUser;" | Out-Null
  Status "Postgres database $DbName created"
} else {
  Status "Postgres database $DbName already exists"
}

Invoke-Psql $DbName "GRANT ALL ON SCHEMA public TO $DbUser; ALTER DATABASE $DbName OWNER TO $DbUser;" | Out-Null
Status "Postgres grants applied"

Write-Host ""
Write-Host "DONE - am-user-platform registered for prod" -ForegroundColor Cyan
Write-Host "  Keycloak : $Realm / $ClientId"
Write-Host "  Vault    : $VaultServicePath"
Write-Host "  Vault    : $VaultPostgresPath with AM_USER_PLATFORM_DB keys"
Write-Host "  Postgres : db=$DbName user=$DbUser"
Write-Host "  Helm injector paths: secret/data/prod/services/am-user-platform and apps/data/prod/infra/postgres"
