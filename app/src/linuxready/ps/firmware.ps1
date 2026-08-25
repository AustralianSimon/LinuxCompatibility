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

$partitions   = @()
$unallocatedGB = $null
$diskTotalGB   = $null

try {
    $disk = Get-Disk -Number 0 -ErrorAction Stop
    $diskTotalGB = [math]::Round($disk.Size / 1GB, 1)

    $diskParts = Get-Partition -DiskNumber 0 -ErrorAction SilentlyContinue |
                 Where-Object { $_.Type -ne 'Unknown' }
    $allocatedBytes = 0
    foreach ($p in $diskParts) {
        $allocatedBytes += $p.Size
        $vol = Get-Volume -Partition $p -ErrorAction SilentlyContinue
        $letter = if ($p.DriveLetter -and $p.DriveLetter -ne [char]0) { $p.DriveLetter.ToString() } else { $null }
        $partitions += @{
            SizeGB      = [math]::Round($p.Size / 1GB, 1)
            Type        = $p.Type
            DriveLetter = $letter
            FreeGB      = if ($vol) { [math]::Round($vol.SizeRemaining / 1GB, 1) } else { $null }
        }
    }
    $unallocatedGB = [math]::Round(($disk.Size - $allocatedBytes) / 1GB, 1)
    if ($unallocatedGB -lt 0) { $unallocatedGB = 0 }
} catch {}

$out = @{
    SecureBoot    = $secureBoot
    BitLocker     = $bitLocker
    StorageMode   = $storageMode
    DiskStyle     = $diskStyle
    FreeGB        = $freeGB
    DiskTotalGB   = $diskTotalGB
    Partitions    = $partitions
    UnallocatedGB = $unallocatedGB
}

ConvertTo-Json -InputObject $out -Compress
