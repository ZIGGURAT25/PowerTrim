Param(
    [string]$Python = "python",
    [switch]$InstallDeps,
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'

function Write-Info($msg) { Write-Host "[i] $msg" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "[x] $msg" -ForegroundColor Red }

# Move to script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Info "Working directory: $ScriptDir"

if ($Clean) {
    Write-Info "Cleaning previous build artifacts..."
    foreach ($p in @('build','dist','__pycache__','PowerTrim.spec')) {
        if (Test-Path $p) {
            Remove-Item -Recurse -Force $p -ErrorAction SilentlyContinue
        }
    }
}

if ($InstallDeps) {
    Write-Info "Installing/updating dependencies (PySide6, python-mpv, pyinstaller, smartcut)..."
    & $Python -m pip install --upgrade pip
    & $Python -m pip install PySide6 python-mpv pyinstaller smartcut
}

# Collect --add-binary entries from bin/ (if present)
$BinDir = Join-Path $ScriptDir 'bin'
$addBinaryArgs = @()
if (Test-Path $BinDir) {
    Write-Info "Bundling binaries from: $BinDir"
    Get-ChildItem -Path $BinDir -File -Recurse | ForEach-Object {
        $src = $_.FullName
        # Put all under bin/ in the dist folder
        $dest = 'bin'
        $addBinaryArgs += @('--add-binary', "$src;$dest")
    }
} else {
    Write-Warn "No bin/ folder found. Build will rely on PATH at runtime."
}

# PyInstaller args (onedir recommended for portability)
$pyiArgs = @(
    '--noconfirm',
    '--clean',
    '--name', 'PowerTrim',
    '--noconsole'
) + $addBinaryArgs + @('PowerTrimGUI.py')

Write-Info "Running PyInstaller..."
& $Python -m PyInstaller @pyiArgs

# Post-build: create portable_mode file and ensure output/snapshots exist
$DistDir = Join-Path $ScriptDir 'dist/PowerTrim'
if (Test-Path $DistDir) {
    $portableMarker = Join-Path $DistDir 'portable_mode'
    if (-not (Test-Path $portableMarker)) {
        New-Item -Path $portableMarker -ItemType File -Force | Out-Null
        Write-Ok "Created portable_mode marker"
    }
    foreach ($d in @('output','snapshots')) {
        $dirPath = Join-Path $DistDir $d
        if (-not (Test-Path $dirPath)) { New-Item -ItemType Directory -Path $dirPath | Out-Null }
    }
    Write-Ok "Build complete: $DistDir"
    Write-Info "Next steps: Zip the 'PowerTrim' folder and distribute."
    Write-Info "Ensure you include third-party licenses (FFmpeg/mpv/smartcut) in a 'licenses/' folder."
} else {
    Write-Err "dist/PowerTrim not found. PyInstaller may have failed."
    exit 1
}


