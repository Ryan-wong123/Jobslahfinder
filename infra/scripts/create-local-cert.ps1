$ErrorActionPreference = "Stop"

$certDir = Join-Path $PSScriptRoot "..\nginx\certs"
$keyPath = Join-Path $certDir "localhost.key"
$certPath = Join-Path $certDir "localhost.crt"
$opensslConfigPath = Join-Path $certDir "localhost-openssl.cnf"

New-Item -ItemType Directory -Force -Path $certDir | Out-Null

@"
[req]
default_bits = 2048
prompt = no
default_md = sha256
x509_extensions = v3_req
distinguished_name = dn

[dn]
CN = localhost

[v3_req]
subjectAltName = @alt_names
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
"@ | Set-Content -Encoding ascii -Path $opensslConfigPath

function ConvertTo-Pem {
  param(
    [Parameter(Mandatory = $true)]
    [string] $Label,
    [Parameter(Mandatory = $true)]
    [byte[]] $Bytes
  )

  $base64 = [Convert]::ToBase64String($Bytes)
  $lines = for ($index = 0; $index -lt $base64.Length; $index += 64) {
    $length = [Math]::Min(64, $base64.Length - $index)
    $base64.Substring($index, $length)
  }

  "-----BEGIN $Label-----`n$($lines -join "`n")`n-----END $Label-----`n"
}

function Join-ByteArrays {
  param(
    [Parameter(Mandatory = $true)]
    [byte[][]] $Arrays
  )

  $stream = [System.IO.MemoryStream]::new()
  foreach ($array in $Arrays) {
    if ($null -ne $array -and $array.Length -gt 0) {
      $stream.Write($array, 0, $array.Length)
    }
  }
  $result = $stream.ToArray()
  $stream.Dispose()
  $result
}

function ConvertTo-Asn1Length {
  param(
    [Parameter(Mandatory = $true)]
    [int] $Length
  )

  if ($Length -lt 128) {
    return [byte[]] @($Length)
  }

  $bytes = New-Object System.Collections.Generic.List[byte]
  $remaining = $Length
  while ($remaining -gt 0) {
    $bytes.Insert(0, [byte] ($remaining -band 0xff))
    $remaining = $remaining -shr 8
  }

  [byte[]] @([byte] (0x80 -bor $bytes.Count)) + [byte[]] $bytes.ToArray()
}

function ConvertTo-Asn1 {
  param(
    [Parameter(Mandatory = $true)]
    [byte] $Tag,
    [Parameter(Mandatory = $true)]
    [byte[]] $Value
  )

  Join-ByteArrays @(
    [byte[]] @($Tag),
    (ConvertTo-Asn1Length -Length $Value.Length),
    $Value
  )
}

function ConvertTo-Asn1Integer {
  param(
    [Parameter(Mandatory = $true)]
    [byte[]] $Value
  )

  $start = 0
  while ($start -lt ($Value.Length - 1) -and $Value[$start] -eq 0) {
    $start++
  }

  $length = $Value.Length - $start
  $trimmed = New-Object byte[] $length
  [Array]::Copy($Value, $start, $trimmed, 0, $length)

  if (($trimmed[0] -band 0x80) -ne 0) {
    $trimmed = [byte[]] @(0) + [byte[]] $trimmed
  }

  ConvertTo-Asn1 -Tag 0x02 -Value $trimmed
}

function ConvertTo-RsaPrivateKeyDer {
  param(
    [Parameter(Mandatory = $true)]
    [System.Security.Cryptography.RSAParameters] $Parameters
  )

  $version = ConvertTo-Asn1Integer -Value ([byte[]] @(0))
  $body = Join-ByteArrays @(
    $version,
    (ConvertTo-Asn1Integer -Value $Parameters.Modulus),
    (ConvertTo-Asn1Integer -Value $Parameters.Exponent),
    (ConvertTo-Asn1Integer -Value $Parameters.D),
    (ConvertTo-Asn1Integer -Value $Parameters.P),
    (ConvertTo-Asn1Integer -Value $Parameters.Q),
    (ConvertTo-Asn1Integer -Value $Parameters.DP),
    (ConvertTo-Asn1Integer -Value $Parameters.DQ),
    (ConvertTo-Asn1Integer -Value $Parameters.InverseQ)
  )

  ConvertTo-Asn1 -Tag 0x30 -Value $body
}

$openssl = Get-Command openssl -ErrorAction SilentlyContinue

if ($openssl) {
  & $openssl.Source req -x509 -nodes -days 365 -newkey rsa:2048 `
    -keyout $keyPath `
    -out $certPath `
    -config $opensslConfigPath
} else {
  Write-Host "OpenSSL was not found on Windows PATH. Generating the certificate with Windows/.NET..."

  $rsa = [System.Security.Cryptography.RSA]::Create(2048)
  $request = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
    "CN=localhost",
    $rsa,
    [System.Security.Cryptography.HashAlgorithmName]::SHA256,
    [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
  )

  $request.CertificateExtensions.Add(
    [System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($false, $false, 0, $true)
  )
  $request.CertificateExtensions.Add(
    [System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new(
      [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature -bor
      [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::KeyEncipherment,
      $true
    )
  )

  $enhancedKeyUsage = [System.Security.Cryptography.OidCollection]::new()
  [void] $enhancedKeyUsage.Add([System.Security.Cryptography.Oid]::new("1.3.6.1.5.5.7.3.1"))
  $request.CertificateExtensions.Add(
    [System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new($enhancedKeyUsage, $false)
  )

  $sanBuilder = [System.Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
  $sanBuilder.AddDnsName("localhost")
  $sanBuilder.AddIpAddress([System.Net.IPAddress]::Parse("127.0.0.1"))
  $request.CertificateExtensions.Add($sanBuilder.Build())

  $notBefore = [DateTimeOffset]::UtcNow.AddMinutes(-5)
  $notAfter = $notBefore.AddDays(365)
  $certificate = $request.CreateSelfSigned($notBefore, $notAfter)

  $certPem = ConvertTo-Pem -Label "CERTIFICATE" -Bytes $certificate.Export(
    [System.Security.Cryptography.X509Certificates.X509ContentType]::Cert
  )
  $keyPem = ConvertTo-Pem -Label "RSA PRIVATE KEY" -Bytes (ConvertTo-RsaPrivateKeyDer -Parameters $rsa.ExportParameters($true))

  Set-Content -Encoding ascii -Path $certPath -Value $certPem
  Set-Content -Encoding ascii -Path $keyPath -Value $keyPem

  $rsa.Dispose()
  $certificate.Dispose()
}

if (!(Test-Path $certPath) -or !(Test-Path $keyPath)) {
  throw "Certificate generation did not produce localhost.crt and localhost.key."
}

Write-Host "Created local self-signed certificate:"
Write-Host "  $certPath"
Write-Host "  $keyPath"
