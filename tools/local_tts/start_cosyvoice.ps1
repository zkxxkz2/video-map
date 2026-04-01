param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 9880,
    [string]$PythonExe = "",
    [string]$VenvDir = "",
    [string]$UpstreamDir = "",
    [string]$ModelDir = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $VenvDir) {
    $VenvDir = Join-Path $RepoRoot "storage\local_tts\venv"
}
if (-not $UpstreamDir) {
    $UpstreamDir = Join-Path $RepoRoot "storage\local_tts\CosyVoice-upstream"
}
if (-not $ModelDir) {
    $ModelDir = Join-Path $RepoRoot "storage\local_tts\models\CosyVoice-300M-SFT"
}

if (-not $PythonExe) {
    if ($env:CONDA_PREFIX) {
        $CondaPython = Join-Path $env:CONDA_PREFIX "python.exe"
        if (Test-Path $CondaPython) {
            $PythonExe = $CondaPython
        }
    }
}

if (-not $PythonExe) {
    $PyCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($PyCmd -and $PyCmd.Source -and ($PyCmd.Source -notlike "*WindowsApps*")) {
        $PythonExe = $PyCmd.Source
    }
}

if (-not $PythonExe) {
    $VenvPython = Join-Path $VenvDir "Scripts\python.exe"
    if (Test-Path $VenvPython) {
        $PythonExe = $VenvPython
    }
}

if (-not $PythonExe -or -not (Test-Path $PythonExe)) {
    throw "Python not found. Provide -PythonExe, activate conda env, or prepare local venv."
}
if (-not (Test-Path $UpstreamDir)) {
    throw "CosyVoice upstream repo not found: $UpstreamDir"
}
if (-not (Test-Path $ModelDir)) {
    throw "CosyVoice model directory not found: $ModelDir"
}

$ExistingConn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
if ($ExistingConn) {
    $OwnerProc = Get-Process -Id $ExistingConn.OwningProcess -ErrorAction SilentlyContinue
    if ($OwnerProc) {
        throw "Port $Port is already in use by $($OwnerProc.ProcessName) (PID $($OwnerProc.Id))."
    }
    throw "Port $Port is already in use."
}

$ModelScopeCache = Join-Path $RepoRoot "storage\local_tts\modelscope_cache"
New-Item -ItemType Directory -Force -Path $ModelScopeCache | Out-Null
$env:MODELSCOPE_CACHE = $ModelScopeCache

& $PythonExe (Join-Path $RepoRoot "tools\local_tts\cosyvoice_server.py") `
    --cosyvoice-root $UpstreamDir `
    --model-dir $ModelDir `
    --host $BindHost `
    --port $Port
