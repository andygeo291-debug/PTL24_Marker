param(
    [string]$Serial = "21601161",
    [string]$Name = "StaticCam",
    [int]$Width = 960,
    [int]$Height = 720,
    [int]$Fps = 15,
    [string]$PixelFormat = "Mono8",
    [int]$ExposureUs = 15000,
    [int]$Gain = 0,
    [int]$OffsetX = 320,
    [int]$OffsetY = 200,
    [int]$InterpacketDelay = 3500,
    [int]$TimeoutMs = 1000,
    [int]$PacketSize = 8192,
    [int]$StreamBufferCount = 32,
    [int]$GrabFrames = 200
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoCandidates = @(
    "D:\Electryone\PTL24_Marker",
    "C:\Users\$env:USERNAME\Desktop\ptl24_marker"
)
$repo = $repoCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $repo) {
    Write-Host "ERROR: repo path not found in expected locations."
    exit 1
}

Set-Location $repo

$venvPath = Join-Path $repo ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Host "Creating .venv..."
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $pythonCandidates = @()

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $pythonCandidates += @{ Command = "py"; Args = @("-3.11") }
        $pythonCandidates += @{ Command = "py"; Args = @("-3") }
    }

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd -and $pythonCmd.Source -notmatch "WindowsApps") {
        $pythonCandidates += @{ Command = $pythonCmd.Source; Args = @() }
    }

    $known = @(
        "C:\Python311\python.exe",
        "C:\Python310\python.exe",
        "C:\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe"
    )
    foreach ($path in $known) {
        if (Test-Path $path) {
            $pythonCandidates += @{ Command = $path; Args = @() }
        }
    }

    foreach ($candidate in $pythonCandidates) {
        & $candidate.Command @($candidate.Args) -m venv $venvPath 2>$null | Out-Null
        if (Test-Path $pythonExe) {
            break
        }
    }
    $ErrorActionPreference = $oldEap

    if (-not (Test-Path $pythonExe)) {
        Write-Host "ERROR: Python 3.10+ not found. Install Python and re-run."
        exit 1
    }
}

& $pythonExe -m pip install --upgrade pip setuptools wheel | Out-Host
& $pythonExe -m pip install -r requirements.txt | Out-Host

$activate = Join-Path $venvPath "Scripts\Activate.ps1"
if (Test-Path $activate) {
    . $activate
}

Write-Host "Enumerating Basler devices..."
& $pythonExe tools\basler_enum.py | Out-Host

Write-Host "Running grab smoke test ($GrabFrames frames)..."
$grabArgs = @(
    "-m", "common.camera.test_basler_grab",
    "--serial", $Serial,
    "--name", $Name,
    "--pixel-format", $PixelFormat,
    "--width", $Width,
    "--height", $Height,
    "--offset-x", $OffsetX,
    "--offset-y", $OffsetY,
    "--fps", $Fps,
    "--exposure-us", $ExposureUs,
    "--gain", $Gain,
    "--packet-size", $PacketSize,
    "--interpacket-delay", $InterpacketDelay,
    "--stream-buffer-count", $StreamBufferCount,
    "--timeout-ms", $TimeoutMs,
    "--frames", $GrabFrames
)
$grabOutput = & $pythonExe @grabArgs 2>&1 | Tee-Object -Variable grabLog
$failCount = 0
$grabText = ($grabOutput -join "`n")
$match = [regex]::Match($grabText, "failed=(\d+)")
if ($match.Success) {
    $failCount = [int]$match.Groups[1].Value
}

if ($failCount -gt 0) {
    Write-Host "Grab failures detected ($failCount). Running diagnostics..."
    Write-Host "Firewall profiles:"
    $fwProfiles = Get-NetFirewallProfile
    $fwProfiles | Format-Table Name, Enabled, DefaultInboundAction, DefaultOutboundAction

    $pythonPath = $pythonExe
    Write-Host "Firewall rules for python:"
    $pyRules = Get-NetFirewallRule -Program $pythonPath -ErrorAction SilentlyContinue
    $pyRules | Format-Table DisplayName, Enabled, Action, Direction
    $allowRule = $pyRules | Where-Object { $_.Enabled -eq "True" -and $_.Action -eq "Allow" } | Select-Object -First 1
    $blockInbound = $fwProfiles | Where-Object { $_.Enabled -eq "True" -and $_.DefaultInboundAction -eq "Block" }
    if (-not $allowRule -and $blockInbound) {
        Write-Host "Warning: inbound firewall default is Block and no explicit Allow rule for python was found."
    }

    Write-Host "NIC status:"
    Get-NetAdapter | Format-Table Name, Status, LinkSpeed, MacAddress, ifIndex

    $adapters = Get-NetAdapter | Where-Object { $_.Status -eq "Up" }
    foreach ($adapter in $adapters) {
        try {
            $eee = Get-NetAdapterAdvancedProperty -Name $adapter.Name |
                Where-Object { $_.DisplayName -match "Energy Efficient Ethernet" }
            foreach ($prop in $eee) {
                if ($prop.DisplayValue -ne "Disabled") {
                    Write-Host "Disabling Energy Efficient Ethernet on $($adapter.Name)"
                    Set-NetAdapterAdvancedProperty -Name $adapter.Name -DisplayName $prop.DisplayName -DisplayValue "Disabled" -NoRestart
                }
            }
        } catch {
            Write-Host "EEE setting not available or failed for $($adapter.Name)"
        }

        try {
            $pm = Get-NetAdapterPowerManagement -Name $adapter.Name
            if ($pm.AllowComputerToTurnOffDevice -eq "Enabled") {
                Write-Host "Disabling power saving on $($adapter.Name)"
                Set-NetAdapterPowerManagement -Name $adapter.Name -AllowComputerToTurnOffDevice Disabled
            }
        } catch {
            Write-Host "Power management setting not available or failed for $($adapter.Name)"
        }

        try {
            $jumbo = Get-NetAdapterAdvancedProperty -Name $adapter.Name |
                Where-Object { $_.DisplayName -match "Jumbo (Packet|Frame)" }
            foreach ($prop in $jumbo) {
                if ($prop.DisplayValue -match "9|Jumbo") {
                    Write-Host "Disabling Jumbo Frames on $($adapter.Name)"
                    Set-NetAdapterAdvancedProperty -Name $adapter.Name -DisplayName $prop.DisplayName -DisplayValue "Disabled" -NoRestart
                }
            }
        } catch {
            Write-Host "Jumbo frame setting not available or failed for $($adapter.Name)"
        }
    }

    Write-Host "Re-running grab smoke test after diagnostics..."
    & $pythonExe @grabArgs | Out-Host
}

Write-Host "Running Basler pose test suite..."
& $pythonExe tools\run_basler_pose_tests.py `
    --serial $Serial `
    --name $Name `
    --width $Width `
    --height $Height `
    --fps $Fps `
    --pixel-format $PixelFormat `
    --exposure-us $ExposureUs `
    --gain $Gain `
    --offset-x $OffsetX `
    --offset-y $OffsetY `
    --interpacket-delay $InterpacketDelay `
    --timeout-ms $TimeoutMs `
    --packet-size $PacketSize `
    --stream-buffer-count $StreamBufferCount | Out-Host

$runsDir = Join-Path $repo "basler_test_runs"
$latest = Get-ChildItem $runsDir -Directory |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if ($latest) {
    $summary = Join-Path $latest.FullName "summary\MEETING_SUMMARY.md"
    $table = Join-Path $latest.FullName "summary\meeting_table.csv"
    Write-Host "Latest run: $($latest.FullName)"
    Write-Host "Summary: $summary"
    Write-Host "Table: $table"
}
