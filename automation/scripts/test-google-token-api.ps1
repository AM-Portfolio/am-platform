# Test POST /auth/google/token against local am-identity (port 8113).
# Usage:
#   .\test-google-token-api.ps1 -IdToken "<google-jwt>"
#   .\test-google-token-api.ps1 -IdTokenFile .\id-token.txt
param(
  [string]$BaseUrl = "http://localhost:8113",
  [string]$IdToken = "",
  [string]$IdTokenFile = ""
)

if ($IdTokenFile) {
  $IdToken = Get-Content -Raw -Path $IdTokenFile
}
$IdToken = $IdToken.Trim()
if (-not $IdToken) {
  Write-Error "Provide -IdToken or -IdTokenFile. Get a token via automation/scripts/google-id-token.html"
  exit 1
}

$body = @{ id_token = $IdToken } | ConvertTo-Json -Compress
try {
  $response = Invoke-RestMethod -Method Post -Uri "$BaseUrl/auth/google/token" `
    -ContentType "application/json" -Body $body
  $response | ConvertTo-Json -Depth 5
  Write-Host "`nOK — access_token length: $($response.access_token.Length)" -ForegroundColor Green
} catch {
  Write-Host "HTTP error:" -ForegroundColor Red
  if ($_.Exception.Response) {
    $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
    Write-Host $reader.ReadToEnd()
  } else {
    Write-Host $_.Exception.Message
  }
  exit 1
}
