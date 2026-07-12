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
    Switch - run 'terraform plan' only (no apply).

.PARAMETER Destroy
    Switch - destroy the environment's realm (USE WITH EXTREME CAUTION).

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

Write-Host ""
Write-Host "[Keycloak Deploy] Environment : $Env" -ForegroundColor Cyan
Write-Host "[Keycloak Deploy] Var file     : $VarFile" -ForegroundColor Cyan

# Load SMTP + Keycloak admin from .secrets.{env}.env as TF_VAR_* (overrides tfvars).
$PlatformRoot = (Resolve-Path (Join-Path $ScriptDir "..\..\..")).Path
$SecretsFile  = Join-Path $PlatformRoot ".secrets.$Env.env"
if (Test-Path $SecretsFile) {
    Write-Host "[Keycloak Deploy] Loading secrets: $SecretsFile" -ForegroundColor Cyan
    Get-Content $SecretsFile | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
        $i = $_.IndexOf('=')
        if ($i -lt 1) { return }
        $name = $_.Substring(0, $i).Trim()
        $value = $_.Substring($i + 1)
        $map = @{
            KEYCLOAK_URL                    = "TF_VAR_keycloak_url"
            KEYCLOAK_ADMIN_USER             = "TF_VAR_keycloak_admin_username"
            KEYCLOAK_ADMIN_PASSWORD         = "TF_VAR_keycloak_admin_password"
            KEYCLOAK_SMTP_HOST              = "TF_VAR_smtp_host"
            KEYCLOAK_SMTP_PORT              = "TF_VAR_smtp_port"
            KEYCLOAK_SMTP_FROM              = "TF_VAR_smtp_from"
            KEYCLOAK_SMTP_FROM_DISPLAY_NAME = "TF_VAR_smtp_from_display_name"
            KEYCLOAK_SMTP_USER              = "TF_VAR_smtp_user"
            KEYCLOAK_SMTP_PASSWORD          = "TF_VAR_smtp_password"
        }
        if ($map.ContainsKey($name)) {
            Set-Item -Path ("Env:" + $map[$name]) -Value $value
        }
        if ($name -eq "KEYCLOAK_SMTP_SSL") {
            Set-Item -Path Env:TF_VAR_smtp_ssl -Value ($(if ($value -eq "true") { "true" } else { "false" }))
        }
        if ($name -eq "KEYCLOAK_SMTP_STARTTLS") {
            Set-Item -Path Env:TF_VAR_smtp_starttls -Value ($(if ($value -eq "true") { "true" } else { "false" }))
        }
    }
}

Write-Host ""
Write-Host ">> terraform init" -ForegroundColor Yellow
terraform init -reconfigure

$existing = terraform workspace list 2>&1 | Out-String
if ($existing -notmatch "\b$Env\b") {
    Write-Host ""
    Write-Host ">> Creating workspace: $Env" -ForegroundColor Yellow
    terraform workspace new $Env
} else {
    Write-Host ""
    Write-Host ">> Selecting workspace: $Env" -ForegroundColor Yellow
    terraform workspace select $Env
}

if ($Destroy) {
    if ($Env -eq "prod") {
        Write-Host ""
        Write-Host "[ABORT] Refusing to destroy the PROD realm via automation." -ForegroundColor Red
        Write-Host "        If you really need this, run terraform destroy manually." -ForegroundColor Red
        exit 1
    }
    Write-Host ""
    Write-Host ">> terraform destroy (env=$Env)" -ForegroundColor Red
    terraform destroy -var-file="$VarFile"
} elseif ($Plan) {
    Write-Host ""
    Write-Host ">> terraform plan (env=$Env)" -ForegroundColor Yellow
    terraform plan -var-file="$VarFile"
} else {
    Write-Host ""
    Write-Host ">> terraform apply (env=$Env)" -ForegroundColor Green
    terraform apply -var-file="$VarFile" -auto-approve
    Write-Host ""
    Write-Host "[Keycloak Deploy] Done - workspace '$Env' applied successfully." -ForegroundColor Green

    $RealmName = (terraform output -raw realm_name 2>$null)
    if ($RealmName) {
        $IssuerUrl = "https://auth.munish.org/auth/realms/$RealmName"
        $Discovery = "$IssuerUrl/.well-known/openid-configuration"
        Write-Host ""
        Write-Host "[Keycloak Deploy] OIDC Discovery: $Discovery" -ForegroundColor Cyan
    }
}
