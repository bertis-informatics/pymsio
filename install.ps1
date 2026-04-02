<#
.SYNOPSIS
    Installs pymsio, downloads Thermo DLLs, extracts SCIEX DLLs via temporary ProteoWizard install, and cleans up.
.DESCRIPTION
    1. Displays the Thermo & ProteoWizard/SCIEX License Agreement.
    2. Downloads Thermo Fisher RawFileReader DLLs directly from GitHub.
    3. Checks for ProteoWizard. If missing, downloads and installs it silently.
    4. Copies SCIEX DLLs from ProteoWizard into the project folder.
    5. If ProteoWizard was installed by this script, uninstalls it to leave no trace.
    6. Installs pymsio via pip.
#>
param(
    [switch]$SkipPipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Configuration Variables ──────────────────────────────────────────────────
# Thermo Fisher
$THERMO_REPO = "https://github.com/thermofisherlsms/RawFileReader/raw/main"
$THERMO_LICENSE = "$THERMO_REPO/License.doc"
$THERMO_DLLS = @(
    "ThermoFisher.CommonCore.Data.dll",
    "ThermoFisher.CommonCore.RawFileReader.dll"
)

# SCIEX / ProteoWizard
$PWIZ_LICENSE = "https://proteowizard.sourceforge.io/licenses.html"
$PWIZ_DOWNLOAD_PAGE = "https://proteowizard.sourceforge.io/download.html"
$PWIZ_VERSION = "3.0.25011"
$PWIZ_INSTALLER_URL = "https://downloads.sourceforge.net/project/proteowizard/ProteoWizard/${PWIZ_VERSION}/pwiz-setup-${PWIZ_VERSION}-x86_64.exe"
$PWIZ_BASE_DIR = "C:\Program Files\ProteoWizard"
$SCIEX_REQUIRED = @(
    "Clearcore2.Data.dll",
    "Clearcore2.Data.AnalystDataProvider.dll"
)
$SCIEX_PATTERNS = @("Clearcore2*.dll", "Sciex*.dll", "SciexToolKit.dll", "protobuf-net.dll")

# Project Paths
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ThermoDllDir = Join-Path (Join-Path (Join-Path $ScriptDir "pymsio") "dlls") "thermo_fisher"
$SciexDllDir = Join-Path (Join-Path (Join-Path $ScriptDir "pymsio") "dlls") "sciex"


# ── 1. Dual License Agreement ────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Thermo Fisher & SCIEX/ProteoWizard License Agreement" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "This script will set up proprietary vendor libraries required for MS data reading."
Write-Host "By proceeding, you agree to the following End User License Agreements (EULAs):"
Write-Host ""
Write-Host "  1. Thermo RawFileReader License:" -ForegroundColor Yellow
Write-Host "     $THERMO_LICENSE"
Write-Host "  2. ProteoWizard & SCIEX Vendor License:" -ForegroundColor Yellow
Write-Host "     $PWIZ_LICENSE"
Write-Host ""

$response = Read-Host "Do you agree to all license terms? [y/N]"
if ($response -notin @("y", "Y", "yes", "Yes", "YES")) {
    Write-Host "Licenses not accepted. Aborting installation." -ForegroundColor Red
    exit 1
}


# ── 2. Download Thermo DLLs ──────────────────────────────────────────────────
Write-Host ""
Write-Host "[*] Phase 1: Downloading Thermo Fisher DLLs..." -ForegroundColor Green

if (-not (Test-Path $ThermoDllDir)) {
    New-Item -ItemType Directory -Path $ThermoDllDir -Force | Out-Null
}

foreach ($dll in $THERMO_DLLS) {
    $url = "$THERMO_REPO/Libs/Net471/$dll"
    $dest = Join-Path $ThermoDllDir $dll
    Write-Host "    Downloading $dll ..."
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing

    if (Test-Path $dest) {
        Write-Host "    OK: $dest" -ForegroundColor DarkGreen
    } else {
        Write-Host "    FAILED: Could not download $dll" -ForegroundColor Red
        exit 1
    }
}


# ── 3. Copy SCIEX DLLs from existing ProteoWizard installation ───────────────
Write-Host ""
Write-Host "[*] Phase 2: Copying SCIEX DLLs from ProteoWizard..." -ForegroundColor Green

if (-not (Test-Path $SciexDllDir)) {
    New-Item -ItemType Directory -Path $SciexDllDir -Force | Out-Null
}

# Find or install ProteoWizard
$PwizInstalledDir = $null
$InstalledByScript = $false

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

    # Step A: Try hardcoded URL first
    $downloadSuccess = $false
    Write-Host "    ProteoWizard not found. Trying automatic download (v$PWIZ_VERSION)..." -ForegroundColor Yellow
    try {
        Invoke-WebRequest -Uri $PWIZ_INSTALLER_URL -OutFile $InstallerPath -UseBasicParsing -Headers @{ "User-Agent" = "Mozilla/5.0" }
        # Verify it's a valid Windows executable (PE magic bytes: 4D 5A = "MZ")
        if (Test-Path $InstallerPath) {
            $bytes = [System.IO.File]::ReadAllBytes($InstallerPath)
            if ($bytes.Length -gt 100MB -and $bytes[0] -eq 0x4D -and $bytes[1] -eq 0x5A) {
                $downloadSuccess = $true
            } else {
                Write-Host "    Downloaded file is not a valid executable (may be an HTML redirect page)." -ForegroundColor Yellow
                Remove-Item $InstallerPath -Force
            }
        }
    } catch {
        Write-Host "    Auto-download failed: $_" -ForegroundColor Yellow
    }

    # Step B: Fallback — ask user for local installer path
    if (-not $downloadSuccess) {
        Write-Host ""
        Write-Host "    Automatic download failed. Please download ProteoWizard manually:" -ForegroundColor Yellow
        Write-Host "      $PWIZ_DOWNLOAD_PAGE" -ForegroundColor Cyan
        Write-Host ""
        $userPath = Read-Host "    Enter the full path to the downloaded pwiz-setup.exe (or press Enter to abort)"
        if (-not $userPath -or -not (Test-Path $userPath)) {
            Write-Host "    Aborting: no valid installer path provided." -ForegroundColor Red
            exit 1
        }
        $InstallerPath = $userPath
    }

    Write-Host "    Installing ProteoWizard silently (this may take a minute)..." -ForegroundColor Yellow
    $ext = [System.IO.Path]::GetExtension($InstallerPath).ToLower()
    if ($ext -eq ".msi") {
        Start-Process -FilePath "msiexec.exe" -ArgumentList "/i", "`"$InstallerPath`"", "/quiet", "/norestart" -Wait
    } else {
        Start-Process -FilePath $InstallerPath -ArgumentList "/S" -Wait -NoNewWindow
    }

    if (Test-Path $PWIZ_BASE_DIR) {
        $latestPwiz = Get-ChildItem -Path $PWIZ_BASE_DIR -Directory | Sort-Object CreationTime -Descending | Select-Object -First 1
        $PwizInstalledDir = $latestPwiz.FullName
        Write-Host "    ProteoWizard installed at: $PwizInstalledDir" -ForegroundColor Cyan
    } else {
        Write-Host "    FAILED: ProteoWizard installation could not be verified." -ForegroundColor Red
        exit 1
    }
}

# Copy SCIEX DLLs by pattern
$copiedCount = 0
foreach ($pattern in $SCIEX_PATTERNS) {
    $found = Get-ChildItem -Path $PwizInstalledDir -Filter $pattern -ErrorAction SilentlyContinue
    foreach ($file in $found) {
        Copy-Item -Path $file.FullName -Destination (Join-Path $SciexDllDir $file.Name) -Force
        Write-Host "    Copied: $($file.Name)" -ForegroundColor DarkGreen
        $copiedCount++
    }
}

# Verify required DLLs were copied
foreach ($dll in $SCIEX_REQUIRED) {
    if (-not (Test-Path (Join-Path $SciexDllDir $dll))) {
        Write-Host "    FAILED: Required DLL not found in ProteoWizard: $dll" -ForegroundColor Red
        exit 1
    }
}
Write-Host "    Total SCIEX DLLs copied: $copiedCount" -ForegroundColor Cyan


# ── 4. Cleanup ProteoWizard (if installed by this script) ────────────────────
if ($InstalledByScript) {
    Write-Host ""
    Write-Host "[*] Phase 3: Cleaning up temporary ProteoWizard installation..." -ForegroundColor Green

    $Uninstaller = Get-ChildItem -Path $PwizInstalledDir -Filter "unins*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($Uninstaller) {
        Write-Host "    Running uninstaller silently..." -ForegroundColor Yellow
        Start-Process -FilePath $Uninstaller.FullName -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait -NoNewWindow
        Start-Sleep -Seconds 3
        Write-Host "    Uninstallation complete." -ForegroundColor Cyan
    } else {
        Write-Host "    WARNING: Could not find ProteoWizard uninstaller. Manual cleanup may be required." -ForegroundColor Yellow
    }
}


# ── 5. Install pymsio ────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[*] Phase 4: Package Installation..." -ForegroundColor Green

if (-not $SkipPipInstall) {
    Write-Host "    Installing pymsio via pip..." -ForegroundColor Cyan
    Push-Location $ScriptDir
    pip install .
    Pop-Location
} else {
    Write-Host "    Skipping pip install (use 'pip install .' manually)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Setup complete! Thermo and SCIEX DLLs are ready." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
