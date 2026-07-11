# Wrapper — prefer Playwright: npm run e2e:preprod:api (from am-platform/)
param(
  [string]$BaseUrl = "http://localhost:8113",
  [string]$IdToken = "",
  [string]$IdTokenFile = "",
  [ValidateSet("local", "preprod", "dev", "prod")]
  [string]$Env = ""
)

$platformRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if ($Env -eq "preprod") { $BaseUrl = "https://am.asrax.in/identity" }
elseif ($Env -eq "local") { $BaseUrl = "http://localhost:8113" }

if ($IdTokenFile) { $IdToken = (Get-Content -Raw $IdTokenFile).Trim() }
if (-not $IdToken) {
  Write-Error "Provide -IdToken or -IdTokenFile. Or run: npm run e2e:preprod:api"
  exit 1
}

$env:GOOGLE_ID_TOKEN = $IdToken
if ($Env) { $env:E2E_ENV = $Env } elseif ($BaseUrl -match "asrax") { $env:E2E_ENV = "preprod" } else { $env:E2E_ENV = "local" }

Push-Location $platformRoot
try {
  $script = switch ($env:E2E_ENV) {
    "preprod" { "test:preprod:api" }
    "dev"     { "cross-env E2E_ENV=dev playwright test --project=api" }
    "prod"    { "cross-env E2E_ENV=prod playwright test --project=api" }
    default   { "test:local:api" }
  }
  npm run $script -w @am-platform/e2e
} finally {
  Pop-Location
}
