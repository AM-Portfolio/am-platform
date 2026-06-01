<#
.SYNOPSIS
    Applies Keycloak Terraform configuration for a specific environment.

.DESCRIPTION
    Selects the correct Terraform workspace, initialises if needed, then
    applies the environment-specific var file.  Safe to run multiple times
    (idempotent via terraform apply).

.PARAMETER Env
    Target environment: dev | preprod | prod

.PARAMETER Plan
    Switch — run 'terraform plan' only (no apply).

.PARAMETER Destroy
    Switch — destroy the environment's realm (USE WITH EXTREME CAUTION).

.EXAMPLE
    .\deploy.ps1 -Env dev
    .\deploy.ps1 -Env preprod -Plan
    .\deploy.ps1 -Env prod
#>

param(
    [Parameter(Mandatory)]
    [ValidateSet("dev", "preprod", "prod")]
    [string]$Env,

    [switch]$Plan,
    [switch]$Destroy
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir  = $PSScriptRoot
$VarFile    = Join-Path $ScriptDir "terraform.$Env.tfvars"

if (-not (Test-Path $VarFile)) {
    Write-Error "Var file not found: $VarFile"
    exit 1
}

Write-Host "`n[Keycloak Deploy] Environment : $Env" -ForegroundColor Cyan
Write-Host "[Keycloak Deploy] Var file     : $VarFile" -ForegroundColor Cyan

# ── 1. Init (safe to re-run) ─────────────────────────────────────────────────
Write-Host "`n>> terraform init" -ForegroundColor Yellow
terraform init -reconfigure

# ── 2. Workspace ─────────────────────────────────────────────────────────────
$existing = terraform workspace list 2>&1
if ($existing -notmatch "\b$Env\b") {
    Write-Host "`n>> Creating workspace: $Env" -ForegroundColor Yellow
    terraform workspace new $Env
} else {
    Write-Host "`n>> Selecting workspace: $Env" -ForegroundColor Yellow
    terraform workspace select $Env
}

# ── 3. Plan / Apply / Destroy ────────────────────────────────────────────────
if ($Destroy) {
    if ($Env -eq "prod") {
        Write-Host "`n[ABORT] Refusing to destroy the PROD realm via automation." -ForegroundColor Red
        Write-Host "        If you really need this, run terraform destroy manually." -ForegroundColor Red
        exit 1
    }
    Write-Host "`n>> terraform destroy (env=$Env)" -ForegroundColor Red
    terraform destroy -var-file="$VarFile"
} elseif ($Plan) {
    Write-Host "`n>> terraform plan (env=$Env)" -ForegroundColor Yellow
    terraform plan -var-file="$VarFile"
} else {
    Write-Host "`n>> terraform apply (env=$Env)" -ForegroundColor Green
    terraform apply -var-file="$VarFile" -auto-approve
    Write-Host "`n[Keycloak Deploy] Done — workspace '$Env' applied successfully." -ForegroundColor Green

    # ── 4. Emit OIDC issuer URL for quick sanity-check ────────────────────────
    $RealmName = (terraform output -raw realm_name 2>$null)
    if ($RealmName) {
        $IssuerUrl = "https://auth.munish.org/auth/realms/$RealmName"
        Write-Host "`n[Keycloak Deploy] OIDC Discovery: $IssuerUrl/.well-known/openid-configuration" -ForegroundColor Cyan
    }
}
