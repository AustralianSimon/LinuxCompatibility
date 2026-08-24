#Requires -Version 5.1
Set-StrictMode -Off

$results = [System.Collections.Generic.List[hashtable]]::new()

Get-AppxPackage -ErrorAction SilentlyContinue | Where-Object {
    -not $_.IsFramework -and
    ($_.SignatureKind -eq 1 -or $_.SignatureKind -eq 3) -and
    $_.Name -notmatch '^[0-9a-fA-F]{8}-[0-9a-fA-F]'
} | ForEach-Object {
    $displayName   = $null
    $publisherName = $null

    $manifest = Join-Path $_.InstallLocation "AppxManifest.xml"
    if (Test-Path $manifest -ErrorAction SilentlyContinue) {
        try {
            [xml]$xml = Get-Content $manifest -ErrorAction Stop
            $dn = $xml.Package.Properties.DisplayName
            $pn = $xml.Package.Properties.PublisherDisplayName
            if ($dn -and $dn -notmatch '^ms-resource:') { $displayName   = $dn }
            if ($pn -and $pn -notmatch '^ms-resource:') { $publisherName = $pn }
        } catch {}
    }

    $results.Add(@{
        PackageName       = $_.Name
        PackageFamilyName = $_.PackageFamilyName
        DisplayName       = $displayName
        Publisher         = if ($publisherName) { $publisherName } else { $_.PublisherDisplayName }
        Version           = [string]$_.Version
        SignatureKind     = [int]$_.SignatureKind
    })
}

if ($results.Count -eq 0) {
    Write-Output "[]"
} else {
    $results | ConvertTo-Json -Compress
}
