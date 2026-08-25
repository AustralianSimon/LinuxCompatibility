#Requires -Version 5.1
Set-StrictMode -Off

$gpus = @(
    Get-WmiObject Win32_VideoController -ErrorAction SilentlyContinue | ForEach-Object {
        @{ Name = $_.Name; PNPDeviceID = $_.PNPDeviceID; AdapterRAM = $_.AdapterRAM }
    }
)

$pnpDevices = @(
    Get-WmiObject Win32_PnPEntity -ErrorAction SilentlyContinue |
    Where-Object { $_.PNPDeviceID -match '^(PCI|USB)\\' } |
    ForEach-Object {
        @{ Name = $_.Name; PNPDeviceID = $_.PNPDeviceID; Class = $_.PNPClass }
    }
)

$networkAdapters = @(
    Get-WmiObject Win32_NetworkAdapter -Filter "PhysicalAdapter = TRUE" -ErrorAction SilentlyContinue |
    ForEach-Object {
        @{ Name = $_.Name; MACAddress = $_.MACAddress; PNPDeviceID = $_.PNPDeviceID }
    }
)

$cs  = Get-WmiObject Win32_ComputerSystem -ErrorAction SilentlyContinue
$cpu = Get-WmiObject Win32_Processor       -ErrorAction SilentlyContinue | Select-Object -First 1
$ram = if ($cs) { [math]::Round($cs.TotalPhysicalMemory / 1GB, 1) } else { $null }

$system = @{
    Manufacturer = if ($cs)  { $cs.Manufacturer }  else { $null }
    Model        = if ($cs)  { $cs.Model }          else { $null }
    CPU          = if ($cpu) { $cpu.Name }          else { $null }
    RamGB        = $ram
}

$printers = @(
    Get-WmiObject Win32_Printer -ErrorAction SilentlyContinue | ForEach-Object {
        @{ Name = $_.Name; PortName = $_.PortName; DriverName = $_.DriverName }
    }
)

$out = @{
    GPUs           = $gpus
    PnPDevices     = $pnpDevices
    NetworkAdapters= $networkAdapters
    System         = $system
    Printers       = $printers
}

ConvertTo-Json -InputObject $out -Depth 4 -Compress
