param(
    [string]$ModelId = "iic/CosyVoice-300M-SFT",
    [string]$PythonExe = "",
    [string]$UseCurrentEnv = "true",
    [string]$VenvDir = "",
    [string]$UpstreamDir = "",
    [string]$ModelDir = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$UseCurrentEnvEnabled = $true
try {
    if (-not [string]::IsNullOrWhiteSpace($UseCurrentEnv)) {
        $UseCurrentEnvEnabled = [System.Convert]::ToBoolean($UseCurrentEnv)
    }
} catch {
    throw "Invalid -UseCurrentEnv value: $UseCurrentEnv. Use true/false or 1/0."
}

if (-not $VenvDir) {
    $VenvDir = Join-Path $RepoRoot "storage\local_tts\venv"
}
if (-not $UpstreamDir) {
    $UpstreamDir = Join-Path $RepoRoot "storage\local_tts\CosyVoice-upstream"
}
if (-not $ModelDir) {
    $ModelName = $ModelId.Split("/")[-1]
    $ModelDir = Join-Path $RepoRoot "storage\local_tts\models\$ModelName"
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $VenvDir) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ModelDir) | Out-Null

$ModelScopeCache = Join-Path $RepoRoot "storage\local_tts\modelscope_cache"
New-Item -ItemType Directory -Force -Path $ModelScopeCache | Out-Null
$env:MODELSCOPE_CACHE = $ModelScopeCache

if (-not $PythonExe -and $UseCurrentEnvEnabled) {
    if ($env:CONDA_PREFIX) {
        $CondaPython = Join-Path $env:CONDA_PREFIX "python.exe"
        if (Test-Path $CondaPython) {
            $PythonExe = $CondaPython
        }
    }
}

if (-not $PythonExe -and $UseCurrentEnvEnabled) {
    $PyCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($PyCmd -and $PyCmd.Source -and ($PyCmd.Source -notlike "*WindowsApps*")) {
        $PythonExe = $PyCmd.Source
    }
}

if (-not $PythonExe) {
    $PythonExe = Join-Path (Split-Path -Parent $RepoRoot) "lib\python\python.exe"
}

if (-not (Test-Path $PythonExe)) {
    throw "Python not found: $PythonExe"
}

if (-not (Test-Path $UpstreamDir)) {
    git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git $UpstreamDir
} else {
    git -C $UpstreamDir pull --ff-only
    git -C $UpstreamDir submodule update --init --recursive
}

$RuntimePython = $PythonExe
if (-not $UseCurrentEnvEnabled) {
    if (-not (Test-Path (Join-Path $VenvDir "Scripts\python.exe"))) {
        & $PythonExe -m venv $VenvDir
    }
    $RuntimePython = Join-Path $VenvDir "Scripts\python.exe"
}

& $RuntimePython -m pip install --upgrade pip
& $RuntimePython -m pip install "setuptools<81"
& $RuntimePython -m pip install -r (Join-Path $RepoRoot "tools\local_tts\requirements.cosyvoice-runtime.txt")
& $RuntimePython (Join-Path $RepoRoot "tools\local_tts\cosyvoice_download_model.py") --model-id $ModelId --output-dir $ModelDir

Write-Host ""
Write-Host "CosyVoice bootstrap completed."
if ($UseCurrentEnvEnabled) {
    Write-Host "Runtime:   current environment"
} else {
    Write-Host "Venv:      $VenvDir"
}
Write-Host "Python:    $RuntimePython"
Write-Host "Upstream:  $UpstreamDir"
Write-Host "ModelDir:  $ModelDir"
Write-Host "MS Cache:  $ModelScopeCache"
Write-Host ""
Write-Host "Start command:"
Write-Host "powershell -ExecutionPolicy Bypass -File `"$RepoRoot\tools\local_tts\start_cosyvoice.ps1`" -PythonExe `"$RuntimePython`" -ModelDir `"$ModelDir`" -UpstreamDir `"$UpstreamDir`" -VenvDir `"$VenvDir`""
