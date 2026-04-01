@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

set "CONDA_ENV=video"
if not "%~1"=="" set "CONDA_ENV=%~1"
set "TTS_PORT=9880"
set "WEBUI_PORT=8501"
set "AUTO_PAUSE=0"
echo %CMDCMDLINE% | findstr /I " /c " >nul && set "AUTO_PAUSE=1"

echo [INFO] Project root: %ROOT_DIR%
echo [INFO] Target conda env: %CONDA_ENV%

call :check_port %TTS_PORT% Local CosyVoice
if errorlevel 1 call :fail "Port %TTS_PORT% conflict"

call :check_port %WEBUI_PORT% Streamlit WebUI
if errorlevel 1 call :fail "Port %WEBUI_PORT% conflict"

set "CONDA_BAT="
if defined CONDA_EXE (
  for %%I in ("%CONDA_EXE%") do set "CONDA_BASE=%%~dpI.."
  if exist "%CONDA_BASE%\condabin\conda.bat" set "CONDA_BAT=%CONDA_BASE%\condabin\conda.bat"
)
if not defined CONDA_BAT if exist "D:\anaconda3\condabin\conda.bat" set "CONDA_BAT=D:\anaconda3\condabin\conda.bat"
if not defined CONDA_BAT if exist "%USERPROFILE%\anaconda3\condabin\conda.bat" set "CONDA_BAT=%USERPROFILE%\anaconda3\condabin\conda.bat"
if not defined CONDA_BAT if exist "%USERPROFILE%\miniconda3\condabin\conda.bat" set "CONDA_BAT=%USERPROFILE%\miniconda3\condabin\conda.bat"

if not defined CONDA_BAT (
  echo [ERROR] conda.bat not found. Please edit this script and set CONDA_BAT manually.
  call :fail "conda.bat not found"
)

call "%CONDA_BAT%" activate "%CONDA_ENV%"
if errorlevel 1 (
  echo [ERROR] Failed to activate conda env: %CONDA_ENV%
  call :fail "conda activate failed"
)

set "PYTHON_EXE="
for /f "delims=" %%P in ('where python') do (
  set "PYTHON_EXE=%%P"
  goto :python_found
)

:python_found
if not defined PYTHON_EXE (
  echo [ERROR] python not found after activating conda env.
  call :fail "python not found"
)

echo [INFO] Python: %PYTHON_EXE%

set "MODELSCOPE_CACHE=%ROOT_DIR%storage\local_tts\modelscope_cache"
if not exist "%MODELSCOPE_CACHE%" mkdir "%MODELSCOPE_CACHE%"
set "TTS_LOG=%ROOT_DIR%storage\temp\cosyvoice-server.log"
if not exist "%ROOT_DIR%storage\temp" mkdir "%ROOT_DIR%storage\temp"

echo [INFO] Starting Local CosyVoice service...
start "Local CosyVoice TTS" cmd /k "cd /d "%ROOT_DIR%" && powershell -ExecutionPolicy Bypass -File ".\tools\local_tts\start_cosyvoice.ps1" -PythonExe "%PYTHON_EXE%""

echo [INFO] Waiting for TTS health check (http://127.0.0.1:9880/health)...
powershell -NoProfile -Command "$ok=$false; for($i=0;$i -lt 45;$i++){ try{ $r=Invoke-RestMethod -Uri 'http://127.0.0.1:9880/health' -TimeoutSec 2; if($r.status -eq 'ok'){ $ok=$true; break } }catch{}; Start-Sleep -Seconds 2 }; if($ok){ exit 0 } else { exit 1 }"
if errorlevel 1 (
  echo [ERROR] Local TTS service is not ready. Check log/window: %TTS_LOG%
  call :fail "Local TTS health check failed"
)

echo [INFO] Local TTS is ready.
echo [INFO] Launching WebUI...
call :check_port %WEBUI_PORT% Streamlit WebUI
if errorlevel 1 call :fail "Port %WEBUI_PORT% conflict"
python -m streamlit run .\webui\Main.py --browser.gatherUsageStats=False --server.enableCORS=True

goto :eof

:check_port
set "PORT=%~1"
set "LABEL=%~2 %~3"
powershell -NoProfile -Command "$conn=Get-NetTCPConnection -State Listen -LocalPort %PORT% -ErrorAction SilentlyContinue | Select-Object -First 1; if($conn){$p=Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue; if($p){Write-Host ('[ERROR] Port %PORT% already in use by ' + $p.ProcessName + ' (PID ' + $p.Id + ') for %LABEL%.')} else {Write-Host '[ERROR] Port %PORT% already in use for %LABEL%.'}; exit 1} else {Write-Host '[INFO] Port %PORT% is available for %LABEL%.'; exit 0}"
exit /b %ERRORLEVEL%

:fail
echo [ERROR] %~1
if "%AUTO_PAUSE%"=="1" (
  echo.
  echo [INFO] Press any key to close this window...
  pause >nul
)
exit /b 1
