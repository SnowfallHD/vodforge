param(
  [Parameter(Mandatory = $true)]
  [string[]]$Files
)

$ErrorActionPreference = "Stop"

if (-not $Files) {
  throw "At least one file is required for Authenticode verification."
}

foreach ($file in $Files) {
  if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
    throw "Signed file was not found: $file"
  }
  $signature = Get-AuthenticodeSignature -LiteralPath $file
  if ($signature.Status -ne "Valid") {
    throw "Authenticode verification failed for $file`: $($signature.Status) $($signature.StatusMessage)"
  }
  if ($signature.SignerCertificate.Subject -notlike '*O="Kryden Ventures, LLC"*') {
    throw "Unexpected Authenticode publisher for $file`: $($signature.SignerCertificate.Subject)"
  }
  if (-not $signature.TimeStamperCertificate) {
    throw "The Authenticode signature is missing a trusted timestamp: $file"
  }
  Write-Host "Verified Authenticode signature: $file"
}
