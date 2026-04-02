<#
.SYNOPSIS
    Installs pymsio, downloads Thermo DLLs, extracts SCIEX DLLs via ProteoWizard (.msi), and cleans up.
.DESCRIPTION
    1. Displays the dual Thermo & ProteoWizard/SCIEX License Agreement.
    2. Downloads Thermo Fisher RawFileReader DLLs directly from GitHub.
    3. Handles SCIEX DLLs:
       - Tries to download ProteoWizard from a known static SourceForge mirror URL.
       - If it fails, prompts the user *mid-script* to provide a local installer path.
    4. Copies all required SCIEX DLLs using pattern matching (Clearcore2*.dll, Sciex*.dll).
    5. Uninstalls ProteoWizard silently by reading the Registry (avoiding slow Win32_Product).
    6. Installs pymsio via pip.
#>
param(
    [switch]$SkipPipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Configuration ───────────────────────────────────────────────────────────
$THERMO_REPO = "https://github.com/thermofisherlsms/RawFileReader/raw/main"
$THERMO_DLLS = @("ThermoFisher.CommonCore.Data.dll", "ThermoFisher.CommonCore.RawFileReader.dll")

$PWIZ_VERSION = "3.0.25011"
$PWIZ_KNOWN_URL = "https://downloads.sourceforge.net/project/proteowizard/ProteoWizard/${PWIZ_VERSION}/pwiz-setup-${PWIZ_VERSION}-x86_64.exe"
$PWIZ_DOWNLOAD_PAGE = "https://proteowizard.sourceforge.io/download.html"
$PWIZ_BASE_DIR = "C:\Program Files\ProteoWizard"
$SCIEX_REQUIRED = @("Clearcore2.Data.dll", "Clearcore2.Data.AnalystDataProvider.dll")
$DLL_PATTERNS = @("Clearcore2*.dll", "Sciex*.dll", "SciexToolKit.dll", "protobuf-net.dll")

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ThermoDllDir = Join-Path (Join-Path (Join-Path $ScriptDir "pymsio") "dlls") "thermo_fisher"
$SciexDllDir = Join-Path (Join-Path (Join-Path $ScriptDir "pymsio") "dlls") "sciex"

# ── 1. License Agreement ────────────────────────────────────────────────────
Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  Thermo Fisher & SCIEX/ProteoWizard License Agreement" -ForegroundColor Cyan
Write-Host "============================================================`n"
Write-Host "By proceeding, you agree to the following licenses:"
Write-Host "  1. Thermo RawFileReader: $THERMO_REPO/License.doc" -ForegroundColor Yellow
Write-Host "  2. ProteoWizard & SCIEX: https://proteowizard.sourceforge.io/licenses.html" -ForegroundColor Yellow
Write-Host ""
$response = Read-Host "Do you agree to all license terms? [y/N]"
if ($response -notin @("y", "Y", "yes", "Yes", "YES")) {
    Write-Host "Licenses not accepted. Aborting." -ForegroundColor Red
    exit 1
}

# ── 2. Phase 1: Thermo DLLs ─────────────────────────────────────────────────
Write-Host "`n[*] Phase 1: Downloading Thermo Fisher DLLs..." -ForegroundColor Green
if (-not (Test-Path $ThermoDllDir)) { New-Item -ItemType Directory -Path $ThermoDllDir -Force | Out-Null }
foreach ($dll in $THERMO_DLLS) {
    $dest = Join-Path $ThermoDllDir $dll
    if (-not (Test-Path $dest)) {
        Invoke-WebRequest -Uri "$THERMO_REPO/Libs/Net471/$dll" -OutFile $dest -UseBasicParsing
        Write-Host "    Downloaded: $dll" -ForegroundColor DarkGreen
    } else {
        Write-Host "    Already exists: $dll" -ForegroundColor DarkGray
    }
}

# ── 3. Phase 2: SCIEX DLLs (via ProteoWizard) ───────────────────────────────
Write-Host "`n[*] Phase 2: Extracting SCIEX DLLs..." -ForegroundColor Green
if (-not (Test-Path $SciexDllDir)) { New-Item -ItemType Directory -Path $SciexDllDir -Force | Out-Null }

$PwizInstalledDir = $null
$InstalledByScript = $false

# Search for existing installation
if (Test-Path $PWIZ_BASE_DIR) {
    $latestPwiz = Get-ChildItem -Path $PWIZ_BASE_DIR -Directory | Sort-Object CreationTime -Descending | Select-Object -First 1
    if ($latestPwiz) {
        $PwizInstalledDir = $latestPwiz.FullName
        Write-Host "    Found existing ProteoWizard at: $PwizInstalledDir" -ForegroundColor Cyan
    }
}

if (-not $PwizInstalledDir) {
    $InstalledByScript = $true
    $InstallerPath = Join-Path $env:TEMP "pwiz-setup.exe"
    $DownloadSuccess = $false

    # Step A: Try known static URL
    Write-Host "    Attempting automatic download (v$PWIZ_VERSION)..." -ForegroundColor Yellow
    try {
        Invoke-WebRequest -Uri $PWIZ_KNOWN_URL -OutFile $InstallerPath -UseBasicParsing -Headers @{ "User-Agent" = "Mozilla/5.0" }
        # Validate: must be a real executable (MZ magic bytes) and large enough
        if (Test-Path $InstallerPath) {
            $bytes = [System.IO.File]::ReadAllBytes($InstallerPath)
            if ($bytes[0] -eq 0x4D -and $bytes[1] -eq 0x5A -and (Get-Item $InstallerPath).Length -gt 100MB) {
                $DownloadSuccess = $true
                Write-Host "    Download succeeded." -ForegroundColor DarkGreen
            } else {
                Remove-Item $InstallerPath -Force
            }
        }
    } catch { }

    # Step B: Prompt user if auto-download failed (loop until valid path given)
    while (-not $DownloadSuccess) {
        Write-Host "`n    [!] Automatic download failed or blocked by SourceForge." -ForegroundColor Red
        Write-Host "    Please download the 64-bit installer (.msi or .exe) manually from:" -ForegroundColor Yellow
        Write-Host "      $PWIZ_DOWNLOAD_PAGE" -ForegroundColor Cyan
        Write-Host ""
        $ManualPath = Read-Host "    Enter the full path to the downloaded file (or press Enter to abort)"
        $ManualPath = $ManualPath.Trim('"').Trim("'")

        if ([string]::IsNullOrWhiteSpace($ManualPath)) {
            Write-Host "    Aborting." -ForegroundColor Red
            exit 1
        } elseif (Test-Path $ManualPath -PathType Leaf) {
            $InstallerPath = $ManualPath
            $DownloadSuccess = $true
        } else {
            Write-Host "    File not found: '$ManualPath'. Please try again." -ForegroundColor Red
        }
    }

    # Install based on extension
    Write-Host "    Installing ProteoWizard silently (this may take a minute)..." -ForegroundColor Yellow
    if ($InstallerPath.EndsWith(".msi", $true, $null)) {
        Start-Process msiexec.exe -ArgumentList "/i", "`"$InstallerPath`"", "/qn", "/norestart" -Wait
    } else {
        Start-Process -FilePath $InstallerPath -ArgumentList "/S" -Wait -NoNewWindow
    }

    if (Test-Path $PWIZ_BASE_DIR) {
        $latestPwiz = Get-ChildItem -Path $PWIZ_BASE_DIR -Directory | Sort-Object CreationTime -Descending | Select-Object -First 1
        $PwizInstalledDir = $latestPwiz.FullName
        Write-Host "    ProteoWizard installed at: $PwizInstalledDir" -ForegroundColor Cyan
    } else {
        Write-Host "    FAILED: Installation could not be verified." -ForegroundColor Red
        exit 1
    }
}

# Copy DLLs using pattern matching
$copiedCount = 0
foreach ($pattern in $DLL_PATTERNS) {
    Get-ChildItem -Path $PwizInstalledDir -Filter $pattern -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item -Path $_.FullName -Destination (Join-Path $SciexDllDir $_.Name) -Force
        Write-Host "    Copied: $($_.Name)" -ForegroundColor DarkGreen
        $copiedCount++
    }
}

# Verify required DLLs
foreach ($dll in $SCIEX_REQUIRED) {
    if (-not (Test-Path (Join-Path $SciexDllDir $dll))) {
        Write-Host "    FAILED: Required DLL not found: $dll" -ForegroundColor Red
        exit 1
    }
}
Write-Host "    Total SCIEX DLLs copied: $copiedCount" -ForegroundColor Cyan

# ── 4. Phase 3: Cleanup via Registry ────────────────────────────────────────
if ($InstalledByScript) {
    Write-Host "`n[*] Phase 3: Cleaning up temporary ProteoWizard installation..." -ForegroundColor Green

    $RegPaths = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )
    $PwizReg = Get-ItemProperty $RegPaths -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -match "ProteoWizard" } |
        Select-Object -First 1

    if ($PwizReg) {
        if ($PwizReg.PSChildName -match "^\{.*\}$") {
            Start-Process msiexec.exe -ArgumentList "/x", $PwizReg.PSChildName, "/qn", "/norestart" -Wait
        } elseif ($PwizReg.QuietUninstallString) {
            Start-Process cmd.exe -ArgumentList "/c", $PwizReg.QuietUninstallString -Wait -WindowStyle Hidden
        }
        Write-Host "    Temporary ProteoWizard removed." -ForegroundColor Cyan
    } else {
        Write-Host "    Could not find uninstaller in Registry. Cleanup skipped." -ForegroundColor Yellow
    }
}

# ── 5. Phase 4: pip install ─────────────────────────────────────────────────
if (-not $SkipPipInstall) {
    Write-Host "`n[*] Phase 4: Installing pymsio..." -ForegroundColor Green
    Push-Location $ScriptDir
    pip install .
    Pop-Location
} else {
    Write-Host "`n[*] Phase 4: Skipping pip install (use 'pip install .' manually)." -ForegroundColor Yellow
}

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  Setup complete! Thermo and SCIEX DLLs are ready." -ForegroundColor Cyan
Write-Host "============================================================`n" -ForegroundColor Cyan
