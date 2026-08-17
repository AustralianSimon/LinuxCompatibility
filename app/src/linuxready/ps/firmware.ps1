#Requires -Version 5.1
Set-StrictMode -Off

$secureBoot = $null
try { $secureBoot = Confirm-SecureBootUEFI } catch {}

$bitLocker = $null
try {
    $bl = Get-BitLockerVolume -MountPoint $env:SystemDrive -ErrorAction Stop
    $bitLocker = $bl.ProtectionStatus.ToString()
} catch {}

$storageMode = $null
$diskStyle   = $null
$freeGB      = $null

try {
    $disk = Get-Disk -Number 0 -ErrorAction Stop
    $diskStyle = $disk.PartitionStyle

    $driveLetter = $env:SystemDrive[0]
    $vol = Get-Volume -DriveLetter $driveLetter -ErrorAction SilentlyContinue
    if ($vol) {
        $freeGB = [math]::Round($vol.SizeRemaining / 1GB, 1)
    }

    $rstControllers = Get-WmiObject Win32_PnPEntity -ErrorAction SilentlyContinue |
        Where-Object { $_.PNPClass -eq 'SCSIAdapter' -and $_.Name -match 'Intel.*(RST|RAID)' }
    $storageMode = if ($rstControllers) { 'RST/RAID' } else { 'AHCI' }
} catch {}

$out = @{
    SecureBoot  = $secureBoot
    BitLocker   = $bitLocker
    StorageMode = $storageMode
    DiskStyle   = $diskStyle
    FreeGB      = $freeGB
}

ConvertTo-Json -InputObject $out -Compress
