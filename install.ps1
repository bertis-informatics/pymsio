<#
.SYNOPSIS
    Installs pymsio, downloads Thermo DLLs, extracts SCIEX DLLs via temporary ProteoWizard install, and cleans up.
.DESCRIPTION
    1. Displays the dual Thermo & ProteoWizard/SCIEX License Agreement.
    2. Downloads Thermo Fisher RawFileReader DLLs directly from GitHub.
    3. Checks for ProteoWizard. If missing, installs it silently.
    4. Copies the required SCIEX DLLs into the local project folder.
    5. If ProteoWizard was installed by this script, uninstalls it silently to leave no trace.
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
$PWIZ_INSTALLER_URL = "https://teamcity.labkey.org/guestAuth/repository/download/bt83/latest.lastSuccessful/pwiz-setup.exe"
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
Write-Host "This script will download proprietary vendor libraries required for MS data reading."
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


# ── 3. Handle SCIEX DLLs (via ProteoWizard) ──────────────────────────────────
Write-Host ""
Write-Host "[*] Phase 2: Extracting SCIEX DLLs..." -ForegroundColor Green

if (-not (Test-Path $SciexDllDir)) {
    New-Item -ItemType Directory -Path $SciexDllDir -Force | Out-Null
}

$PwizInstalledDir = $null
$InstalledByScript = $false

# Check if ProteoWizard is already installed
if (Test-Path $PWIZ_BASE_DIR) {
    $latestPwiz = Get-ChildItem -Path $PWIZ_BASE_DIR -Directory | Sort-Object CreationTime -Descending | Select-Object -First 1
    if ($latestPwiz) {
        $PwizInstalledDir = $latestPwiz.FullName
        Write-Host "    Found existing ProteoWizard at: $PwizInstalledDir" -ForegroundColor Cyan
    }
}

# If not installed, download and install silently
if (-not $PwizInstalledDir) {
    $InstalledByScript = $true
    $InstallerPath = Join-Path $env:TEMP "pwiz-setup.exe"
    
    Write-Host "    ProteoWizard not found. Downloading installer..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $PWIZ_INSTALLER_URL -OutFile $InstallerPath -UseBasicParsing
    
    Write-Host "    Installing ProteoWizard silently (this may take a minute)..." -ForegroundColor Yellow
    Start-Process -FilePath $InstallerPath -ArgumentList "/S" -Wait -NoNewWindow
    
    # Verify installation
    if (Test-Path $PWIZ_BASE_DIR) {
        $latestPwiz = Get-ChildItem -Path $PWIZ_BASE_DIR -Directory | Sort-Object CreationTime -Descending | Select-Object -First 1
        $PwizInstalledDir = $latestPwiz.FullName
        Write-Host "    ProteoWizard successfully installed at: $PwizInstalledDir" -ForegroundColor Cyan
    } else {
        Write-Host "    FAILED: ProteoWizard installation could not be verified." -ForegroundColor Red
        exit 1
    }
}

# Copy SCIEX DLLs by pattern (Clearcore2*.dll, Sciex*.dll, etc.)
$copiedCount = 0
foreach ($pattern in $SCIEX_PATTERNS) {
    $matches = Get-ChildItem -Path $PwizInstalledDir -Filter $pattern -ErrorAction SilentlyContinue
    foreach ($file in $matches) {
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

# ── 4. Cleanup ProteoWizard (If installed by this script) ────────────────────
if ($InstalledByScript) {
    Write-Host ""
    Write-Host "[*] Phase 3: Cleaning up temporary ProteoWizard installation..." -ForegroundColor Green
    
    # Locate the uninstaller (usually unins000.exe)
    $Uninstaller = Get-ChildItem -Path $PwizInstalledDir -Filter "unins*.exe" | Select-Object -First 1
    
    if ($Uninstaller) {
        Write-Host "    Running uninstaller silently..." -ForegroundColor Yellow
        Start-Process -FilePath $Uninstaller.FullName -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait -NoNewWindow
        
        # Give it a brief moment to finish file deletions
        Start-Sleep -Seconds 3 
        Write-Host "    Uninstallation complete. Temporary files removed." -ForegroundColor Cyan
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